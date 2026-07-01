# SkillAegis-Dashboard

Vue 3 + Vite frontend that renders a live training-session leaderboard from a small set of
Socket.IO whole-state events. The Python backend (`backend/`) subscribes to MISP over ZeroMQ, runs
the evaluation engine, and emits those events; the dashboard (`src/components/dashboard/*`) is a
pure view over them via `src/socket.js` → `src/dashboardState.js`.

## Commands

### Frontend (Vite, port 5173)
- `npm install` — install deps
- `npm run dev` — hot-reload dev server. In DEV `src/socket.js` hardcodes the backend to
  `http://localhost:4001` (real server or mock); in a production build it uses a relative URL.
- `npm run build` — production build to `dist/`
- `npm run lint` — ESLint (`--fix`)
- `npm run format` — Prettier over `src/`

### Backend (real server, port 4001)
Needs a Python ≥3.10 venv under `backend/` and a MISP / ZeroMQ source.
- Setup: `cd backend && python3 -m venv venv && source venv/bin/activate && pip3 install -r requirements.txt && cp config.py.sample config.py`
- `./start.sh --exercise_folder scenarios/` — run the real evaluation backend
- `python3 backend/main.py --exercise_folder <dir> --zmq_log_file <file>` — replay a recorded
  ZeroMQ session instead of subscribing live

### Testing the dashboard (mock server)
Develop and test the UI with **no MISP / Docker / scenarios / ZeroMQ**.
`backend/dev_mock_server.py` speaks the exact same Socket.IO event/ack contract as the real
server, but with synthetic, animated data so the board is alive the moment you load it.

- `./start-mock.sh` — serve synthetic data on `:4001` **instead of** the real backend; then
  `npm run dev` and open the Vite URL. Because DEV `socket.js` is pinned to `:4001`, run the
  mock **or** the real backend, not both.
- Flags pass through `start-mock.sh`: `--players N` (default 20), `--tick S` (default 2.5),
  `--port P` (default 4001), `--unauth` (start as viewer; default starts authenticated as admin),
  `--no-sim` (start frozen), `--seed N` (reproducible world; default 1).
  Log in/out from the admin panel toggles auth live — any credentials are accepted.
- On-demand scenario controls (force a headline state without the admin panel) —
  `curl -X POST http://localhost:4001/mock/<cmd>` where `<cmd>` is
  `pause` / `resume` (freeze for screenshots), `clear` (everyone clears),
  `clear/<user_id>` (one player clears — drives the all-clear burst),
  `checking/<user_id>` (fire a "being validated" pulse on a player's next available
  task — drives the per-task spinner), `empty` (wipe the board),
  `reset` (rebuild the world), or `zmq-stale` / `zmq-fresh` (freeze / resume the reported
  ZMQ time — drives the Live Feed freshness light amber "NO LIVE DATA"; stopping the mock
  drops the socket → red "OFFLINE"). `GET /` reports the paused flag and lists the controls.
- It does **not** run the evaluation engine, scoring math, or scenario format — for that use the
  real backend (`--zmq_log_file` replays a recorded session). See `docs/PRD-ui-testing.md`.
