# PRD — Python Evaluation Sandbox: Isolation, Reuse & Performance

| | |
|---|---|
| **Status** | 🟡 Proposed (Draft) |
| **Date** | 2026-07-13 |
| **Scope** | SkillAegis-Dashboard backend sandbox subsystem — `backend/sandboxAgent.py`, `backend/sandboxClient.py`, the agent lifecycle in `backend/server.py:588-598,742`, the vendored `backend/epicbox/*`, and the `eval_python` choke point (`backend/utils.py:92-93`). The same code is consumed **unchanged** by SkillAegis-Editor through the `tools/SkillAegis-Dashboard` git submodule, so every change here is observed by both apps. Packaging/deploy touches `backend/requirements.txt`, `Dockerfile`, `docker-compose.yml`. |
| **Non-goals** | No change to **evaluation semantics** — same `evaluate(data, context) -> bool` contract, same `__validation_true__/__validation_false__` sentinel protocol (`sandboxClient.py:11-12,30-43`), same pass/fail results, same scoring, same CEXF format. No change to the non-python strategies (`data_filtering`, `query_search`, `query_mirror`) except where they share the agent. **We keep epicbox/Docker as the engine** — no nsjail / gVisor / firecracker migration in this PRD (noted as a future option only). |

## Instructions
Whenever you have a doubt, ask me. Build one phase at a time, each independently demoable and committed on its own; mark each phase ✅ Done with its commit ref **in the same commit** as that phase's code (house convention). Phase 1 is the only *required* correctness fix; Phases 2–5 are improvements that can be scheduled independently.

## Background

### What the python strategy is
`python` is one of four `evaluation_strategy` values (`data_filtering`, `query_mirror`, `query_search`, `python`). For `python`, the **scenario author** supplies the *body* of an `evaluate(data, context) -> bool` function. At evaluation time that body is wrapped into a complete script (`sandboxClient.run`, `sandboxClient.py:16-55`) that defines `evaluate`, injects `data`/`context` as JSON, calls the function, and prints a sentinel (`__validation_true__` / `__validation_false__`). The script is executed inside a **Docker container** and the verdict is read back from stdout (`sandboxClient.py:45`).

This is *by design* arbitrary code execution — hence the sandbox. The code is author-trusted but not user-trusted, and on the Dashboard multiple exercises/scenarios can be live at once against the **same** agent.

### The request flow (both apps)
```
Dashboard live eval          Editor "Test inject" (InjectTester.vue)
  exercise.py router            main.py:/injects/test → testInject()  (main.py:409-431)
        │                                 │
        └────────► backend.utils.eval_python (utils.py:92-93) ◄────────┘
                              │
                   sandboxClient.run() (sandboxClient.py:16-55)   ── builds wrapped script
                              │  HTTP POST localhost:9573
                              ▼
                   sandboxAgent.py  (long-lived HTTP server)      ── one Docker container
                              │  _write_files(main.py) + epicbox.start()
                              ▼
                   python:3.13-alpine container (epicbox)
```

- **The agent.** `sandboxAgent.py` creates **one** container at process start — `with epicbox.create('python', command="python3 main.py", limits=sandbox_limits)` (`sandboxAgent.py:60`) — stores it in a module global, then `serve_forever()` on port `9573`. Each POST rewrites `main.py` into *that same* container (`_write_files`, `sandboxAgent.py:48`) and calls `epicbox.start(sandbox)` (`sandboxAgent.py:49`), which **restarts the exited container** and waits for it to finish (`epicbox/sandboxes.py:145-192` → `utils.docker_communicate` → `container.start()`). On agent shutdown the `with` block's `__exit__` destroys the container (`epicbox/sandboxes.py:35-36,195-209`).
- **Lifecycle wiring.** The Dashboard auto-starts the agent as a child process group and kills it on exit (`server.py:588-598` `start_sandbox_agent()`, called at `server.py:742`). **The Editor does not start the agent** — it only catches the `ConnectionRefusedError` and returns a 503 with manual start instructions (`main.py:419-430`).
- **Limits today.** `sandbox_limits = {"cputime": 1, "memory": 64}` (`sandboxAgent.py:13`); merged with epicbox defaults this yields cputime 1s, realtime 5s, memory 64MB, `memswap_limit == mem_limit` (no swap), and `processes = -1` **(pids unlimited)** because the agent does not set it (`epicbox/config.py:20-30`, `epicbox/sandboxes.py:129`). Container runs as **`user='root'`** with **`read_only=False`** (epicbox `Profile` defaults, `epicbox/config.py:31,37`) and `network_disabled=True`.

## Problem

The agent already *reuses* a container — the intuition that "a new sandbox is spun up per validation" is **not** what happens. But the way it reuses it is wrong in two concrete, measured ways, and the surrounding lifecycle/packaging is fragile. Evidence below was captured against the running agent on 2026-07-13 (reproduction in the Appendix).

### P1 — State leaks between validations *(correctness / isolation — the important bug)*
The container's writable filesystem is **never reset** between runs (`read_only=False`, same container restarted). Only `main.py` is overwritten; everything else persists. Verified:

```
write-run:  open('/tmp/leak_probe.txt','w').write('SECRET_FROM_PREVIOUS_RUN')   → "wrote"
read-run :  open('/tmp/leak_probe.txt').read()                                  → "LEAKED:SECRET_FROM_PREVIOUS_RUN"
```

Consequences:
- **Non-deterministic validations.** A validation's pass/fail can depend on residue from a previous, unrelated validation (files in `/tmp`, cwd artifacts, on-disk caches). Two identical runs can disagree.
- **Cross-scenario/cross-tenant bleed.** On the Dashboard many exercises share the single agent; one scenario's evaluation code can read/observe files left by another's. Author-trusted, but this is exactly the isolation the sandbox is supposed to give.
- **Unbounded disk growth.** The writable layer accumulates across the agent's entire lifetime; a long-running Dashboard leaks disk until the container layer fills.

### P2 — "Reuse" saves creation, not start — most of the latency is still paid per call *(performance)*
Because `epicbox.start()` does a cold `container.start()` on every call, each validation re-boots the container and the Python interpreter from scratch. The reuse only avoids the one-time `containers.create`, not the per-call start/attach/interpreter-boot. Measured over 8 sequential runs of a trivial script:

| Metric | Value |
|---|---|
| End-to-end wall-clock / validation | **~0.198 s** (min 0.185, max 0.216) |
| Container-internal `duration` (StartedAt→FinishedAt) | ~0.088 s |
| **Docker start + attach + teardown overhead** | **~0.11 s (≈55%) paid on every call** |

So ~55% of every python validation is pure orchestration overhead, and it does not shrink with reuse. Under real evaluation code (imports, jq, etc.) the absolute numbers rise but the fixed overhead stays. Because the agent is a **single-threaded `HTTPServer`** over **one shared container**, validations are also fully **serialized** — a 5-second (realtime-limit) script blocks every other test/eval behind it, and concurrent Editor + Dashboard use contends on one container.

### P3 — Fragile lifecycle / no health management *(robustness)*
- The agent captures the container handle **once** and holds it for its whole life. If the container dies or is removed out-of-band (dockerd restart, `docker system prune`, OOM of the daemon, manual cleanup), every subsequent call fails and there is **no re-create and no health check** — the agent must be restarted by hand.
- If Docker is unavailable at agent startup, `epicbox.create` throws and the agent **crashes at boot** rather than degrading to a clear "sandbox unavailable" response.
- The reuse relies on the off-label "restart an exited container" pattern; epicbox's supported entry point is one-shot `run()` (create→start→destroy, `epicbox/sandboxes.py:212-227`), which the agent deliberately bypasses.

### P4 — Packaging & deployment gaps *(the sandbox can't actually run in the shipped container)*
- **Undeclared dependencies.** `sandboxAgent.py` does `import epicbox`, and epicbox imports `docker`, `structlog`, `requests`. None of `epicbox` / `docker` / `structlog` are in `backend/requirements.txt`. epicbox is vendored under `backend/epicbox/` but its transitive deps are not installed by the image build.
- **No Docker access in the composed container.** `docker-compose.yml` does not mount `/var/run/docker.sock` and is not privileged; the `Dockerfile` is a plain `python:3.12-slim` venv. epicbox needs a Docker daemon, so **the python strategy silently cannot work inside the shipped Dashboard container** — it only works when the process runs on a host with Docker access.
- **Dead artifact.** `sandbox_agent.log` contains a `Starting agent on port 9573...` line that the current `sandboxAgent.py` never prints (leftover from a previous version); it and the empty `backend/sandbox_agent.log` are misleading.

### P5 — Security posture *(defense-in-depth)*
Good today: `network_disabled=True`, no swap, cputime 1s + realtime 5s. Weak today:
- Runs as **root** inside the container (`DEFAULT_USER='root'`).
- **`read_only=False`** + reused container (see P1).
- **pids limit unset** → an in-namespace fork bomb is possible (mitigated but not prevented by cputime/realtime).
- The agent binds `("", 9573)` = **all interfaces**, **unauthenticated** — any local (or, absent a firewall, remote) process can submit arbitrary python for execution.

## Proposed change

Five phases. **Phase 1 is the required correctness fix**; the rest are independent improvements, ordered by value/effort.

### Phase 1 — Reset isolation between runs *(required; fixes P1)*
Guarantee every validation starts from clean state. Two viable implementations — pick per the perf decision in Phase 2:
- **(a) Fresh container per call** — switch the agent to epicbox's one-shot `run()` (`create → start → destroy`). Simplest correct isolation; costs an extra `create`+`destroy` per call (measure the delta — likely tens of ms on top of the existing ~0.11 s). Aligns with epicbox's intended API.
- **(b) Wipe-and-reuse** — keep one container but reset its writable state before/after each run (recreate the container, or run each script in a fresh tmpfs workdir with nothing writable outside it). Keeps the create cost amortized but needs care to actually erase `/tmp` and any writable path.

**Acceptance:** the P1 leak reproduction returns `CLEAN:file-not-present` on the read-run. Add a regression test that writes a file in run A and asserts run B cannot see it.

### Phase 2 — Cut per-call latency *(P2)*
Decide with a measurement gate, then implement:
- **Warm-worker model (biggest win).** Keep a **long-lived python process** inside the container that reads `{script}` messages over stdin/a pipe and executes each in an **isolated child** (subprocess/fork with per-child rlimits + a fresh temp cwd, discarded after). This amortizes container *and* interpreter startup; per-call cost drops toward fork+exec of an already-warm interpreter. Must combine with Phase 1 isolation (fresh child + wiped workdir per run) and enforce cputime per child, not per container.
- **Pre-warmed pool + concurrency.** Maintain N ready containers and a `ThreadingHTTPServer`; hand one out per request, recycle (recreate) after use. Unblocks parallel Editor+Dashboard validations and bounds blast radius; more Docker churn than the warm-worker model but a simpler isolation story (one container per run).
- If neither is justified, at minimum switch to `ThreadingHTTPServer` with a small pool so a slow script stops head-of-line-blocking all others.

**Acceptance:** median wall-clock/validation reduced meaningfully vs. the ~0.198 s baseline (target set after the spike), and two concurrent validations no longer serialize. Record before/after numbers in the PR.

### Phase 3 — Health-managed, config-driven agent *(P3)*
- **Health check + lazy (re)create.** Before each run, verify the container exists/usable; re-create it if missing instead of failing for the agent's lifetime. Add a `GET /health` (or `/status`) endpoint reporting `{docker_available, container_ready, image}`.
- **Graceful docker-down.** If Docker is unavailable, don't crash at boot — serve a clear `503 {sandbox_unavailable, reason}` so callers (and the Editor UI) can surface it.
- **Config-drive** image, limits, host, and port via env/`config.py` instead of hardcoding `9573` in two files and the image/limits in the agent.

### Phase 4 — Security hardening *(P5)*
- Run as a **non-root** user; set **`read_only=True`** with a small writable **tmpfs** workdir (dovetails with Phase 1).
- Set a **pids limit** (add `processes` to `sandbox_limits`) to prevent fork bombs.
- Bind the agent to **127.0.0.1** only and require a **shared-secret header** (or a unix socket) so arbitrary local processes can't submit code. Keep `network_disabled=True`.

### Phase 5 — Packaging & cross-app integration *(P4 + Editor DX)*
- **Declare deps** (`epicbox` or its transitive `docker`/`structlog`/`requests`) in `backend/requirements.txt` and install them in the image.
- **Decide the in-container story:** either document that the python strategy requires host Docker (and don't imply otherwise), or mount `/var/run/docker.sock` into the compose service (with the security caveats), or run the agent as its own compose service. Whichever we choose, make it explicit.
- **Remove the dead `sandbox_agent.log`** artifacts (or make the agent actually log a startup line + per-run timings to a real logfile).
- **Editor integration (cross-repo, low-risk):** have the Editor auto-start / health-check the agent so python testing works out-of-the-box instead of requiring the manual `cd tools/SkillAegis-Dashboard/backend && python sandboxAgent.py` step, and show a readiness indicator in the Inject Designer. *(A minimal version of this can land in the Editor independently — see the companion note; it only depends on the Phase 3 `/health` endpoint if we want the richer status.)*

## Future options (out of scope)
- Replace/augment epicbox with a stronger isolation layer (nsjail, gVisor, firecracker, or Wasm/Pyodide for pure-python evaluators with no syscalls) if the threat model tightens.
- A shared managed "sandbox service" both apps depend on, versioned independently of the submodule.

## Appendix — measured evidence & reproduction
Captured 2026-07-13 against the live agent (`localhost:9573`, `python:3.13-alpine`, Docker 29.6.1). Reproduce:

```python
import json, http.client, time
def call(script):
    c = http.client.HTTPConnection("localhost", 9573)
    t0 = time.perf_counter()
    c.request("POST", "/", body=json.dumps({"script": script}),
              headers={"Content-Type": "application/json"})
    out = json.loads(c.getresponse().read().decode()); c.close()
    return time.perf_counter() - t0, out

# P2 — latency: ~0.198s wall-clock, ~0.088s container-internal → ~55% overhead
walls = [call("print('hi')")[0] for _ in range(8)]   # ['0.204','0.190',...] avg 0.198

# P1 — leak: read-run returns LEAKED:SECRET_FROM_PREVIOUS_RUN (should be CLEAN)
call("open('/tmp/leak_probe.txt','w').write('SECRET_FROM_PREVIOUS_RUN'); print('wrote')")
call("import os,glob; p='/tmp/leak_probe.txt';"
     "print('LEAKED:'+open(p).read() if os.path.exists(p) else 'CLEAN:file-not-present')")
```

Findings: wall-clock ≈ 0.198 s/validation (internal 0.088 s); the leak read-run returned `LEAKED:SECRET_FROM_PREVIOUS_RUN`; a workdir listing showed cwd `/sandbox` containing only the overwritten `main.py` (confirming state hides outside the workdir, e.g. `/tmp`).
