# PRD — Pluggable Target Tools (Dashboard foundation)

**Product:** SkillAegis Dashboard (runtime / evaluation engine)
**Area:** Inject evaluation — target-tool registry, tool manifests, generic evaluation core
**Status:** Proposed — foundation PRD. **Ships first; unblocks the Editor.**
**Companion:** `SkillAegis-Editor/docs/PRD-pluggable-target-tools.md` — the consumer/authoring PRD, which is **locked** until this one's Definition of Done (§9) is met.
**Author:** Sami Mokaddem (with Claude)
**Last updated:** 2026-07-16

---

## 1. Summary

SkillAegis evaluates injects for exactly three tools — **MISP, Suricata,
webhook** — wired in by hand through an `if/elif` dispatch ladder and a hardcoded
allow-list. This PRD makes the **runtime** tool-pluggable: a target tool becomes
a self-contained folder under `backend/target_tools/<tool>/`, described by one
declarative **`manifest.json`** and served by a small handler whose only real job
is *"fetch the data to validate."* A **registry** auto-discovers those folders;
the generic evaluation core (`data_filtering`, `python`) runs on any tool's data.

This is the **foundation half** of a two-repo effort. The **Editor** consumes the
manifests defined here (through its `tools/SkillAegis-Dashboard` submodule) to
render its authoring UI. **This PRD must ship first** — the Editor PRD is
explicitly blocked until the Definition of Done in §9 is met.

**Acceptance test:** adding a new produce→check tool costs **one folder** and
**zero** edits to `backend/exercise.py`, `backend/server.py`, or dispatch code.

---

## 2. Goals & non-goals

### Goals

- **G1 — Registry.** Auto-discover `backend/target_tools/*/`; no `if/elif`, no
  per-tool imports in `exercise.py`, no hardcoded allow-list in `server.py`.
- **G2 — Manifest = contract.** Define and **version** the `manifest.json` format
  (this PRD is authoritative for it). It is the single source of truth both the
  Dashboard runtime and the Editor read.
- **G3 — Generic evaluation core.** `data_filtering` + `python` operate on any
  JSON; tool-specific strategies (`query_search`, `query_mirror`, `simulate_ips`,
  `misp_query_search`) become **generic strategy × a tool-declared data-source**.
- **G4 — Decoupled tools.** No tool imports another tool (today `webhook` imports
  `misp`).
- **G5 — No regressions.** Every scenario in the shipped library evaluates to the
  **same verdict** before and after. No CEXF migration.

### Non-goals

- New exercise paradigms (quizzes, tabletop, manual grading) — out of scope.
- The Editor's UI, the `main.py` endpoint, and the `schema_cexf.json` enum change
  — those live in the **Editor PRD**. (`schema_cexf.json` exists only in the
  Editor repo; the Dashboard has no CEXF schema of its own.)
- Rewriting evaluation semantics (operators, jq, condition model unchanged).
- Dynamic/remote plugin loading — tools are folders versioned with this repo.

---

## 3. Current architecture

- **Dispatch is hand-wired.** `backend/exercise.py` imports each tool's router
  explicitly (lines 18–20) and branches on `inject['target_tool']` with an
  `if/elif` ladder (≈ lines 377–415).
- **Allow-list is hardcoded.** `backend/server.py:48` →
  `ALLOWED_TARGET_TOOLS = ["MISP", "suricata", "webhook"]`, plus a
  `if target_tool == 'webhook'` branch.
- **Tools already share an interface.** All three expose
  `inject_checker_router(user_id, inject_evaluation, data, context) -> bool`;
  `misp` and `suricata` expose `get_data_to_validate(...)` (webhook does it
  inline). Each tool's real responsibility is **data acquisition**.
- **The generic core already exists.** `backend/target_tools/suricata/exercise.py`
  fetches rules, runs sample traffic, then calls **`eval_data_filtering(...)`** —
  the same generic evaluator MISP uses — for `simulate_ips`. So `simulate_ips` is
  *already* `data_filtering` over a suricata-acquired data-source. This is the
  proof behind G3.
- **Cross-tool coupling.** `backend/target_tools/webhook/exercise.py` imports
  `fetch_data_for_query_search` from `misp`.

---

## 4. The model: a target tool is a folder

```
backend/target_tools/<tool>/
├── manifest.json      ← declarative metadata — the versioned contract (§5)
├── exercise.py        ← handler: get_data_to_validate() [+ optional overrides]
├── inject_eval.py     ← (optional) tool-specific eval helpers
└── samples/           ← sample payload(s) the Editor shows in its live test
```

The registry (§6) discovers every such folder at startup and indexes it by
`manifest.id`. Adding a tool = adding a folder.

---

## 5. The manifest format (authoritative contract)

`manifest.json` is the single source of truth consumed by **both** repos. It is
**versioned** via `manifest_version`; the Editor codes against a frozen shape.

```jsonc
{
  "manifest_version": 1,                  // bump on breaking shape changes
  "id": "MISP",                           // must match injects[].target_tool
  "label": "MISP",
  "enabled": true,

  // --- Live-test panel (consumed by the Editor) ---
  "sample": "samples/event.json",         // default payload for the live test
  "connection": [                         // fields the author supplies to run a live test
    { "key": "url",    "label": "MISP URL", "type": "url" },
    { "key": "apikey", "label": "API key",  "type": "string", "secret": true }
  ],

  // --- Evaluation ---
  "strategies": ["data_filtering", "query_search", "query_mirror", "python"],
  "triggers": {                           // trigger/timing eligibility per strategy
    "periodic":     ["query_search", "python"],
    "triggered_at": ["query_search", "python"]
  },

  // --- Query builder "FROM" menu (consumed by the Editor) ---
  "sources": [
    { "id": "all-attr", "label": "any attribute",
      "base": "[.Event.Object[].Attribute[], .Event.Attribute[]] | .[]",
      "fields": ["value", "type", "category", "to_ids"] },
    { "id": "event-field", "label": "an event field", "base": ".Event", "kind": "scalar" }
    // …the remaining MISP sources, declared instead of coded
  ],

  "builder": "misp"                       // OPTIONAL: opt into a per-tool builder
                                          // module for complex nesting; omit for the
                                          // generic single-level builder
}
```

**Field ownership.** The Dashboard runtime reads `id`, `enabled`, `strategies`,
`triggers` (validation + dispatch). The Editor reads everything (UI). A
**meta-schema** (`backend/target_tools/manifest.schema.json`) validates every
manifest at load; a malformed manifest fails loudly on the Dashboard and fails
soft (bundled snapshot) on the Editor.

**Stable read path:** `backend/target_tools/*/manifest.json` — documented so the
Editor's submodule read is a fixed contract.

---

## 6. Registry & tool interface

- **Discovery:** on startup, scan `backend/target_tools/*/manifest.json`, validate
  against the meta-schema, and build `REGISTRY: dict[str, ToolPlugin]` keyed by
  `id`.
- **`exercise.py`:** replace explicit imports + the `if/elif` ladder with
  `REGISTRY[inject['target_tool']].inject_checker_router(...)`. Unknown tool →
  logged error + `False` (no crash).
- **`server.py`:** derive the allow-list from `REGISTRY.keys()`; the
  `if target_tool == 'webhook'` branch becomes a registry/capability lookup.
- **Tool interface** (already de-facto satisfied):
  - `async def get_data_to_validate(user_id, inject_evaluation, data, context) -> dict|list|str|None` — **required** (the tool-specific part).
  - `async def inject_checker_router(...) -> bool` — **optional override**; the
    registry provides a generic default: `get_data_to_validate` → dispatch to the
    generic strategy engine (§7).
  - Optional `is_valid_evaluation_context(...)`, capability probes
    (e.g. Suricata's "engine installed?").

---

## 7. Generic evaluation core

A small set of **generic strategies** operate on any JSON returned by a tool's
`get_data_to_validate`:

| Strategy | Behaviour | Tool-specific? |
|----------|-----------|----------------|
| `data_filtering` | run the author's conditions over the data | no |
| `python` | run the author's function over the data | no |
| `equality` | compare two datasets for equality (generalises `query_mirror`) | no |

Everything else is **generic strategy × a tool-declared data-source**:

- `query_search` = `data_filtering` over the response of an author-defined REST
  query (query in `evaluation_context`, unchanged).
- `misp_query_search` = `query_search` whose query is templated from the incoming
  payload (`{{placeholders}}`).
- `simulate_ips` = `data_filtering` over the fired-alert list — **already
  implemented this way** (§3).
- `query_mirror` = `equality` between the trainee's result and the author's
  reference result.

**Decision (D1):** implement the unification *internally* — data acquisition
becomes a declared/parameterised step feeding the generic engine — while
**keeping the six existing strategy names** in CEXF and the manifests. Result:
clean core, **zero scenario migration** (G5). A new produce→check tool that
declares only `data_filtering`/`python` writes **no** strategy code (G3).

---

## 8. Backward compatibility & regression gate

- **No CEXF migration.** All six strategy names and all three tool ids stay valid.
- **MISP/Suricata/webhook are re-expressed as manifests, not rewritten** — their
  handlers stay; only registration + the metadata source move.
- **Regression gate (G5):** a fixture replays every scenario in the shipped
  library through `check_inject` and asserts **identical verdicts** pre/post. Run
  it in CI for every phase.
- **Decoupling check:** no module under `backend/target_tools/<a>/` imports
  `backend/target_tools/<b>/` — the shared REST helper moves to `backend/utils`
  (or a `backend/data_sources` module).

---

## 9. Definition of Done — 🔓 unlocks the Editor PRD

This list is the Editor PRD's §0 unlock checklist. When all are true, tag a
Dashboard release and notify the Editor track.

- [ ] `manifest.schema.json` exists; `manifest_version` defined and documented.
- [ ] MISP, Suricata, webhook each ship a `manifest.json` that **reproduces
      today's metadata** — parity test green (manifest ≡ current behaviour).
- [ ] Registry replaces the `if/elif` dispatch; `server.py` allow-list derived
      from the registry; no tool imports another tool.
- [ ] `backend/target_tools/*/manifest.json` documented as the stable read path.
- [ ] Regression fixture: 0 verdict diffs across the shipped scenario library.
- [ ] Generic-core contract stable (strategy × data-source, six names preserved).
- [ ] A **tagged commit** the Editor can pin its submodule to.

---

## 10. Phased delivery (Dashboard-owned phases)

Shared phase numbering with the Editor PRD. Phases 1–2 and the generic core are
Dashboard-side; they are the gate for the Editor's Phase 3.

1. **Phase 1 — Manifests describe today's tools.** Add `manifest.json` +
   `manifest.schema.json`; capture current metadata exactly. **No behaviour
   change** — the runtime still uses its existing paths. Add the parity test.
2. **Phase 2 — Registry.** Auto-discovery replaces `if/elif`; `server.py`
   allow-list from the registry; decouple webhook↔misp (shared REST helper →
   `backend/utils`).
4. **Phase 4 (core half) — Generic evaluation core.** Land strategy × data-source
   internally behind the existing names (§7). *(The Editor half of Phase 4 — opening
   `schema_cexf.json` — is in the Editor PRD.)*
5. **Phase 5 (tool) — Prove it.** Add a real fourth tool (e.g. TheHive) as the
   living acceptance test + reference example; write "how to add a target tool."

---

## 11. Risks & mitigations

- **Silent behaviour drift when moving metadata into manifests.** → parity test
  (§9) asserts manifest ≡ current tables; regression fixture asserts verdicts.
- **Registry masks a tool that fails to load.** → validate at startup; fail loudly
  with the offending path; never silently drop a tool.
- **Suricata/webhook quirks** (Suricata needs its engine; webhook reused MISP
  query logic). → capability probes stay in handlers; shared logic moves to a
  common module, not a cross-tool import.
- **Editor coupling to an unstable manifest shape.** → freeze via
  `manifest_version` + meta-schema **before** lifting the Editor lock.

---

## 12. Success metrics

- **M1** New produce→check tool = one folder, zero core-file edits. *(= G1/G2.)*
- **M2** `backend/exercise.py` dispatch ladder and `server.py` hardcoded
  allow-list both gone (registry-derived).
- **M3** 0 verdict diffs across the shipped scenario library.
- **M4** No `target_tools/<a>/ → <b>/` imports remain.

---

## 13. Appendix — current-state file map (Dashboard)

- `backend/exercise.py` — `if/elif` dispatch (≈377–415); explicit tool imports
  (18–20). → registry.
- `backend/server.py:48` — `ALLOWED_TARGET_TOOLS`; `if target_tool == 'webhook'`.
  → registry-derived.
- `backend/target_tools/{misp,suricata,webhook}/exercise.py` — handlers; shared
  `inject_checker_router(...)`; `misp`+`suricata` expose `get_data_to_validate`.
- `backend/target_tools/misp/inject_eval.py` — `eval_data_filtering`,
  `eval_query_mirror`, `eval_query_search`, `eval_python` (the generic engine core
  lives here today; extract the tool-neutral parts).
- `backend/target_tools/webhook/exercise.py` — imports MISP's
  `fetch_data_for_query_search` → decouple.
- `backend/target_tools/suricata/exercise.py` — `simulate_ips` already calls
  `eval_data_filtering` (proof of §7).
- **New:** `backend/target_tools/manifest.schema.json`,
  `backend/target_tools/*/manifest.json`, `backend/registry.py` (or similar).
