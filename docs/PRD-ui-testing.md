# PRD — Dashboard UI Testing Harness (mock socket server)

| | |
|---|---|
| **Status** | Draft |
| **Date** | 2026-06-30 |
| **Scope** | A standalone mock Socket.IO server + the wiring/docs to develop & test the dashboard UI without MISP, Docker, scenarios, or ZeroMQ |
| **Non-goals** | Not a test of the evaluation engine, scoring math, or scenario format (that needs the real backend / ZMQ replay). Not an automated/CI test suite — this is a manual, interactive harness. |

## Background

The dashboard (`src/components/dashboard/*`) renders entirely from a small, fixed set of
Socket.IO events that carry **whole-state snapshots** (`update_progress`, `update_statistics`,
`notification`, `update_users_activity`, `update_notification_history`, `keep_alive`) plus a
handful of ack-callback fetches the client issues on connect (`get_exercises`, `get_progress`,
`get_users_stats`, `get_notifications`, `get_users_activity`, `check_user_authenticated`).

Because of that, the cheapest faithful way to exercise the UI — leaderboard, champions, hall of
fame, live feed, all the gamification states — is a **mock server that speaks this exact
contract** with synthetic, scriptable data. It runs the *real* client code path
(`socket.js` listeners → `dashboardState.js` view-models → components) with **zero app-code
changes**, while giving deterministic control over states a live exercise can't produce on
demand (a player clearing everything *now*, a 12-key nested JSON payload, an on-fire streak).

This was chosen over (a) replaying a recorded ZeroMQ `.live` file through the real backend —
no recording exists, it needs MISP for `query_*` injects to ever complete, and it can't force
specific UI states; and (b) mutating `socket.js` state directly — which bypasses the real
`socket.on` handlers and leaks test code into the bundle.

### What already exists (started)

**`backend/dev_mock_server.py`** — the mock server core, **built and verified end-to-end**
(2026-06-30). It boots on `:4001`, answers every `get_*` ack, and runs a simulation loop that:
emits a synthetic animated roster (default 20 players, scores ticking up, rows re-sorting),
drives players to clear all tasks, marks on-fire streaks, maintains per-user activity heat
buffers + a feed timeline, and emits a Live Feed of varied payloads (small / large / nested /
raw-string / webhook). It starts in **admin** mode (`--unauth` for viewer); `/login` (any
credentials) and `/logout` toggle auth live, and the admin events (`mark_task_completed`,
`mark_task_incomplete`, `change_exercise_selection`, `reset_*`) mutate the in-memory model and
re-emit. Dev CORS for `http://localhost:5173` is handled unconditionally.

Verification done: socket handshake, `/login` CORS headers, and a Python Socket.IO client
probe confirming well-formed payloads (2 finishers + 7 on-fire on first paint, correct
`{user_id, timestamp, first_completion}` completion entries, full stats with
`speedrunner_score_ceiling` so a clean run = Speed Index 10.0, live `notification` +
`update_progress` every tick, seeded feed with mixed dict/string payloads). No errors.

This PRD captures **the remaining steps** to turn that core into a complete, discoverable,
fully-covering testing harness.

---

## Summary table

| # | Item | Effort | Risk | Status |
|---|------|--------|------|--------|
| 1 | Mock server core (`dev_mock_server.py`) — contract + simulation loop | Large | Low | ✅ Done |
| 2 | One-command launcher (`start-mock.sh`) + dependency note | Trivial | None | ✅ Done |
| 3 | Documentation — CLAUDE.md "Commands" + README run section | Quick | None | ✅ Done |
| 4 | Surface-coverage matrix + gap-fill (every component & recent change) | Medium | Low | ✅ Done |
| 5 | On-demand scenario controls (pause / force-clear / empty / reset) | Medium | Low | ✅ Done |
| 6 | Dev CORS / Vite-port mismatch — investigate for mock **and** real server | Medium | Low | ⬜ Investigate |

Ship easiest-first (2 → 3 unblock everyone; 4 → 5 firm up coverage). Item 5 is partly optional.
Item 6 is an investigation surfaced during item 2 verification — schedule independently.

---

## 1. Mock server core — ✅ Done

`backend/dev_mock_server.py` as described above. Remaining items build on it; no further core
work is required for basic use. Source-only (no `dist/` impact); reuses `python-socketio` +
`aiohttp` already pinned in `backend/requirements.txt` (no new dependency).

---

## 2. One-command launcher + dependency note — ✅ Done

**Problem.** Running the mock today is `cd backend && ./venv/bin/python dev_mock_server.py …`,
which assumes a venv and isn't discoverable. `start.sh` already gives the real backend a
one-liner; the mock should match.

**Proposed change.** Add **`start-mock.sh`** at the repo root, mirroring `start.sh`'s venv
handling and argument passthrough:

```bash
#!/bin/bash
# Dev-only: serve synthetic dashboard data on :4001 (no MISP/ZMQ/scenarios).
# Run this INSTEAD of ./start.sh, then `npm run dev` and open :5173.
[ -f "backend/venv/bin/activate" ] && source backend/venv/bin/activate
[ -f "venv/bin/activate" ] && source venv/bin/activate
exec python3 backend/dev_mock_server.py "$@"   # --players N --tick S --unauth --port P
```

The deps are already in `requirements.txt`, so the only setup is the standard backend venv
(`cd backend && python3 -m venv venv && pip install -r requirements.txt`).

**Affected files.** New `start-mock.sh` (chmod +x).

**Acceptance.** `./start-mock.sh` boots the mock on :4001 with a venv if present; flags pass
through. ✅ Verified: launcher sources the co-located venv and binds :4001 (Socket.IO handshake
`HTTP 200`); `--port/--players/--tick/--unauth` pass through (banner reflects them).

---

## 3. Documentation — ✅ Done

**Problem.** Nothing tells a developer the harness exists or how the dev ports wire together.

**Proposed change.** Add a short **"Testing the dashboard (mock server)"** subsection to
`CLAUDE.md` (under *Commands*) and a matching note in `README.md`:

- Run `./start-mock.sh` (serves :4001) **instead of** the real backend, then `npm run dev`
  (:5173) and open the Vite URL. In DEV, `socket.js` hardcodes `http://localhost:4001`, so the
  mock **must** be on :4001 — you run the mock *or* the real backend, not both.
- Admin vs viewer: starts admin; log in from the panel (any credentials) or start with
  `--unauth`; `/logout` drops to viewer.
- One-line statement of what it is **not**: it does not run the evaluation engine — use the real
  backend with `--zmq_log_file` for that.

**Affected files.** `CLAUDE.md`, `README.md`.

**Acceptance.** A newcomer can go from clone to a live, populated dashboard using only the docs.
✅ Done: no `CLAUDE.md` existed, so it was created with a *Commands* section (frontend / real
backend / mock-server subsection) plus a one-line orientation; `README.md` gained a matching
"Testing the dashboard (mock server)" subsection under *Development*. Both state the :4001
mock-or-real rule, the pass-through flags, admin-vs-`--unauth` auth, and that the harness does not
run the evaluation engine (link to this PRD).

---

## 4. Surface-coverage matrix + gap-fill

**Problem.** We should be able to assert that *every* dashboard surface is exercised by the
mock, and fix anything that isn't. The probe confirmed the data shapes; this item confirms the
**rendered** result and closes gaps.

**Coverage matrix** (component/feature → mock data that drives it → state):

| Surface | Driven by | State |
|---|---|---|
| `DashboardHeader` — clock, collective score, user count, global progress | `now`, `globalProgress`, `userCount` | ✅ |
| `DashboardHeader` — sort / hide-inactive / auto-paginate toggles | client-side refs | ✅ |
| `DashboardHeader` — exercise switcher | 2 exercises defined, **both selected** by default | ✅ |
| `LiveLeaderboard` — rows, ranks, top-3 medals, +N pops, live re-sort | 20 players, live score churn | ✅ |
| `LiveLeaderboard` — auto-pagination | 20 players > rows-per-page | ✅ |
| `LiveLeaderboard` — fused clear bar + **admin hover-reveal** (recent change) | ≥1 finisher + admin mode | ✅ |
| `LiveLeaderboard` — activity heatmap strip | per-user activity buffers | ✅ |
| `LiveLeaderboard` — task square states: done / available / **locked** | `tasks_completion` + `requirements` chain on exercise 2 | ✅ |
| `CompletionBurst` — all-clear burst | a player completing their **last** task live | ✅ |
| `HallOfFame` — podium (2nd·1st·3rd) | `userStats.hall_of_fame` top 3 | ✅ |
| `ChampionsSlot` — On Fire / Speed / Trophies / Finishers + scene dots + pin | `time_on_fire`, `speed_runner`+ceiling, 4 trophy ids, finishers | ✅ |
| `LiveFeed` — timeline bars, MESSAGES/API counters, search | history buffer, `is_api_request`, client refs | ✅ |
| `LiveFeed` — JSON payload expand/collapse (2.5) | small / large / nested / raw-string payloads | ✅ |
| `LiveFeed` — "Just Cleared" strip | completion timestamps | ✅ |
| `LoginForm` / admin path — login, logout, toggles, reset, task-toggle | `/login`, `/logout`, mock admin events | ✅ |

**Gap-fill (the two ⚠️ rows) — ✅ Done:**
- **Both** exercises are now selected by default, so the header's scenario switcher
  (`active_exercises.length > 1`) renders without first toggling the 2nd in the admin panel.
- The **second** exercise (`Threat-Actor Attribution`) carries a linear **prerequisite chain**
  (each task's `requirements.inject_uuid` points at the previous task), so the leaderboard's
  locked-task (dim, non-blink) square styling is rendered. The default-shown exercise
  (`MISP Triage Drill`) stays chain-free, keeping the common case simple. It is seeded last (so
  exercise 1's verified seed sequence is unchanged) with a spread of in-order progress, and the
  two exercise-1 finishers clear it too — a full clean run still spans **both** selected
  exercises, keeping the Speed Index at 10.0 despite the larger combined ceiling.

**Affected files.** `backend/dev_mock_server.py`.

**Acceptance.** Every row above is ✅. ✅ Verified by a Socket.IO probe against the running mock:
2 exercises defined and both selected; exercise 1 chain-free, exercise 2 a clean linear chain;
the exercise-2 board shows 63 done / 14 available / 23 locked squares (10 players with a locked
square, 8 showing all three states at once); exactly 2 players clear both exercises; speedrunner
ceiling 320 with a top speedrunner score of 320 → Speed Index 10.0.

---

## 5. On-demand scenario controls — ✅ Done

**Problem.** The simulation is autonomous; targeted testing and clean screenshots want
deterministic control ("freeze here", "make player 7 clear now").

**Implemented** — lightweight, dev-only controls (`backend/dev_mock_server.py`):

- **Pause/freeze.** `--no-sim` starts the board frozen; `POST /mock/pause` and `POST /mock/resume`
  toggle it live. While paused the sim stops mutating scores / feed / buffers but still emits
  `keep_alive`, so the connection stays fresh for an inspection/screenshot frame.
- **HTTP poke routes** (no admin panel / curl-friendly), each mutates the in-memory model and
  re-emits the whole-state events:
  - `POST /mock/clear/<user_id>` — one player clears every selected task (keeps existing
    timestamps so the *last* task lands now → drives the all-clear `CompletionBurst`).
  - `POST /mock/clear` — every player clears (full finished board).
  - `POST /mock/empty` — wipe all progress + on-fire to a fresh, zeroed board.
  - `POST /mock/reset` — rebuild the synthetic world from scratch.
- **Reproducibility / already present, now documented.** `--seed N` (default 1) makes the world
  deterministic; `--players N`, `--tick S`, `--unauth` documented in item 3 / the docstring.
  `GET /` reports the `paused` flag and lists the control routes for discoverability.

The admin panel's reset / task-toggle / exercise-selection still work through the mock for
interactive use; these routes add a no-UI path for scripted/curl-driven state forcing.

**Affected files.** `backend/dev_mock_server.py`, `CLAUDE.md`, `README.md`.

**Acceptance.** ✅ A tester can force the headline states without waiting on the simulation.
Verified by a Socket.IO probe against the running mock: `/mock/clear/1` → user 1 at 13/13 done;
`/mock/empty` → all-zero board; `/mock/clear` → every player at the max; `/mock/pause` → `paused`
flag flips, no movement over a full tick window, `keep_alive` still flowing; `/mock/resume` +
`/mock/reset` → fresh mid-session board; `--no-sim` boots with `paused: true`; an unknown
`user_id` returns HTTP 404.

---

## 6. Dev CORS / Vite-port mismatch (mock + real server) — ⬜ Investigate

**Problem.** During item 2 verification, the server logged:

```
http://localhost:5174 is not an accepted origin.
```

Vite came up on **:5174**, not :5173, because `vite.config.js` pins no port (`server.port` /
`strictPort` unset) — Vite auto-increments when :5173 is occupied (a second `npm run dev`, or
another process on the port). Both servers hardcode the dev frontend origin to **:5173**, so the
Socket.IO connection and the credentialed `/login` · `/logout` requests get rejected. The same
mismatch would hit the **real** server, so investigate both together.

**Where the :5173 assumption is baked in:**
- **Mock** (`backend/dev_mock_server.py`): Socket.IO `cors_allowed_origins=[…:5173]` (line 49)
  **and** HTTP `DEV_ORIGINS = {…:5173}` (line 545).
- **Real** (`backend/server.py`): HTTP `cors_middleware` `ALLOWED_ORIGINS = {"http://localhost:5173"}`
  under `DEBUG` (line 104). Its Socket.IO server uses `cors_allowed_origins='*'` (line 98) —
  wildcard, so the handshake itself isn't origin-rejected, but a wildcard `*` is incompatible with
  `withCredentials: true` (which `src/socket.js` sets in DEV), so that path needs its own check.
- **Client** (`src/socket.js`): hardcodes the *backend* URL to `http://localhost:4001` in DEV and
  sends credentials; the value the servers reject is the *frontend* origin, which is what drifts.

**To investigate / options (not yet decided):**
1. Pin Vite to a fixed port — `server: { port: 5173, strictPort: true }` in `vite.config.js` — so
   it fails loudly instead of silently drifting. Simplest, single source of truth; downside: can't
   run two frontends at once.
2. Widen the dev allowlist on both servers (accept any `http://localhost:<port>` /
   `127.0.0.1:<port>` in DEV), or make it configurable (`--origin` flag / env var).
3. Reconcile the real server's Socket.IO `'*'` + credentials combo with the explicit-origin echo it
   already does for its HTTP routes.

**Affected files.** `vite.config.js`, `backend/dev_mock_server.py`, `backend/server.py`.

**Acceptance.** `npm run dev` + either server connect cleanly (Socket.IO handshake + `/login` /
`/logout`) regardless of whether Vite lands on :5173 or an incremented port, with a documented,
intentional rule for which origins are allowed in DEV.

---

## Acceptance criteria (feature-level)

- `./start-mock.sh` + `npm run dev` brings up a fully populated, live, animated dashboard with
  no MISP / Docker / scenarios / ZeroMQ.
- The coverage matrix (item 4) is entirely ✅ in the rendered UI, including the two gap-fills.
- Documented well enough that a newcomer can do all of the above from CLAUDE.md / README.
- No production app-code changes required to use the harness; mock + launcher live under
  `backend/` and the repo root and are dev-only.

## Effort / Risk

Medium overall (core already done) / Low — additive, dev-only, no impact on the shipped app or
the real backend.
