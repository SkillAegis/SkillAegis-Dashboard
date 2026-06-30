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
| 2 | One-command launcher (`start-mock.sh`) + dependency note | Trivial | None | ⬜ Todo |
| 3 | Documentation — CLAUDE.md "Commands" + README run section | Quick | None | ⬜ Todo |
| 4 | Surface-coverage matrix + gap-fill (every component & recent change) | Medium | Low | ⬜ Todo |
| 5 | On-demand scenario controls (pause / force-clear / prereq chain / select-both) | Medium | Low | ⬜ Todo (partly optional) |

Ship easiest-first (2 → 3 unblock everyone; 4 → 5 firm up coverage). Item 5 is partly optional.

---

## 1. Mock server core — ✅ Done

`backend/dev_mock_server.py` as described above. Remaining items build on it; no further core
work is required for basic use. Source-only (no `dist/` impact); reuses `python-socketio` +
`aiohttp` already pinned in `backend/requirements.txt` (no new dependency).

---

## 2. One-command launcher + dependency note

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
through.

---

## 3. Documentation

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
| `DashboardHeader` — exercise switcher | 2 exercises defined, **1 selected** by default | ⚠️ needs ≥2 selected (see gap-fill) |
| `LiveLeaderboard` — rows, ranks, top-3 medals, +N pops, live re-sort | 20 players, live score churn | ✅ |
| `LiveLeaderboard` — auto-pagination | 20 players > rows-per-page | ✅ |
| `LiveLeaderboard` — fused clear bar + **admin hover-reveal** (recent change) | ≥1 finisher + admin mode | ✅ |
| `LiveLeaderboard` — activity heatmap strip | per-user activity buffers | ✅ |
| `LiveLeaderboard` — task square states: done / available | `tasks_completion` + `requirements` | ⚠️ "locked" (unmet prereq) never shown (see gap-fill) |
| `CompletionBurst` — all-clear burst | a player completing their **last** task live | ✅ |
| `HallOfFame` — podium (2nd·1st·3rd) | `userStats.hall_of_fame` top 3 | ✅ |
| `ChampionsSlot` — On Fire / Speed / Trophies / Finishers + scene dots + pin | `time_on_fire`, `speed_runner`+ceiling, 4 trophy ids, finishers | ✅ |
| `LiveFeed` — timeline bars, MESSAGES/API counters, search | history buffer, `is_api_request`, client refs | ✅ |
| `LiveFeed` — JSON payload expand/collapse (2.5) | small / large / nested / raw-string payloads | ✅ |
| `LiveFeed` — "Just Cleared" strip | completion timestamps | ✅ |
| `LoginForm` / admin path — login, logout, toggles, reset, task-toggle | `/login`, `/logout`, mock admin events | ✅ |

**Gap-fill (the two ⚠️ rows):**
- Default-select **both** exercises (or expose `--exercises N`) so the header switcher is
  testable without first toggling the 2nd in the admin panel.
- Add an optional **prerequisite chain** for one exercise's tasks (populate `requirements`),
  so the leaderboard's locked-task (dim, non-blink) square styling is actually rendered. Keep
  the default chain-free so the common case stays simple.

**Affected files.** `backend/dev_mock_server.py`.

**Acceptance.** Every row above is ✅ — visually confirmed in the running dashboard.

---

## 5. On-demand scenario controls (partly optional)

**Problem.** The simulation is autonomous; targeted testing and clean screenshots want
deterministic control ("freeze here", "make player 7 clear now").

**Proposed change.** Lightweight, dev-only controls (pick the subset that earns its keep):

- `--no-sim` / a pause toggle — freeze the board for inspection/screenshots (state still served).
- A tiny HTTP poke route, e.g. `POST /mock/clear/<user_id>` and `POST /mock/reset` — force a
  specific player to clear, or reset the world, without the admin panel. (The admin panel's
  reset / task-toggle / exercise-selection already work through the mock for interactive use.)
- Already present and worth documenting: `--players N`, `--tick S`, `--unauth`, fixed
  `random.seed` for reproducible runs.

**Affected files.** `backend/dev_mock_server.py` (+ a line in the docs from item 3).

**Acceptance.** A tester can force the headline states (full clear, empty board, frozen frame)
without waiting on the simulation.

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
