# PRD — Player Drill-Down Panel

| | |
|---|---|
| **Status** | In progress — Phase 0 done (2026-07-03); Phase 1 next |
| **Date** | 2026-07-03 |
| **Scope** | SkillAegis-Dashboard frontend (`src/components/dashboard/*`, `src/socket.js`) **and** a backend addition for per-user event history (`backend/db.py`, `backend/notification.py`, `backend/server.py`) plus matching mock support (`backend/dev_mock_server.py`). |
| **Non-goals** | No change to the evaluation engine, scoring math, or scenario format. The Socket.IO contract gains exactly **one** request/ack event (`get_user_events`); no new server-push event — live event updates ride the existing `notification` push. No change to any existing event. |

## Instructions
Whenever you have a doubt, ask me.

## Background

The live dashboard (`src/components/dashboard/*` — `DashboardHeader`, `LiveLeaderboard`,
`HallOfFame`, `ChampionsSlot`, `LiveFeed`) is a pure view over whole-state Socket.IO snapshots,
shaped by `socket.js` → `dashboardState.js`. It serves two audiences at once: **trainees**
(real-time feedback on their own progress + gamification) and **trainers** (situational
awareness — who is where, what is hard, is the data live).

It is a strong **scoreboard**, but not yet a **monitoring tool**. This PRD was split out of the
"Dashboard Enhancements" PRD (item 3.1); its other items are complete and merged into `develop`.
The player drill-down is the sole remaining feature and is large enough to warrant its own document.

**Goal served.** Trainer situational awareness — "what's going on live", per participant.

## Problem

A trainer cannot inspect a single participant: which task they are on, how long each task took,
when they were last active, and what they have been doing. Today, clicking a leaderboard row does
nothing for a viewer, and for an admin it only toggles a task square. The board aggregates; it
does not profile.

## Proposed change

Clicking a participant (outside the task squares, for admins) opens a **right-edge slide-over
drawer** that profiles that one participant for the **selected exercise**. Available to **all
viewers** (read-only monitoring); admins additionally keep the existing per-task toggle controls
on the row. The drawer overlays the right rail with a dimming backdrop. Because the drawer +
backdrop hide most of the board, the leaderboard's **auto-paginate rotation pauses while the drawer
is open** and resumes on close — the board should not silently cycle through pages nobody can see.

### Drawer contents

1. **Header** — name, org, rank, score / max_score, and the live status chips already present in
   `progresses[user_id].status` (`is_on_fire`, `is_speed_runner`, `is_on_all_house_fame`,
   `trophies`).
2. **Task list with timing** — each task's state (done / available / locked-by-prerequisite) and,
   for completed tasks, the completion time and the **gap to the previous completion**
   (time-per-task). Source: `tasks_completion[inject_uuid].timestamp`; compute gaps from the
   sorted timestamps exactly as `leaderboard.py:get_sorted_timestamps_for_completed_tasks` does,
   with the first task's gap measured from the exercise-start anchor (`exerciseStart`, the same
   anchor `elapsed`/`finishers` already use). "Currently on" = the available task(s) whose
   prerequisites are met but not yet done (`taskRequirementMet` already exists in
   `dashboardState.js`).
3. **Last seen / activity** — derive from `userActivity[user_id]` (the per-bucket activity buffer)
   and `userActivityConfig` (bucket resolution): last non-zero bucket → "active Ns ago", plus a
   small sparkline reusing the heatmap/timeline bar treatment.
4. **Recent events** — this participant's recent request/webhook events, served by a **new backend
   `get_user_events` endpoint** backed by a per-user retention buffer (deeper than the global
   `NOTIFICATION_BUFFER_SIZE = 30` ring). Seeded on open, then live-appended from the existing
   `notification` push filtered to this player's `user_id`.

### Interaction & accessibility (cross-phase)

- **Row click** opens the drawer. A **task square** must still toggle completion for an admin, so
  square clicks stop propagation **only when authenticated** — a viewer clicking anywhere on the
  row (squares included) opens the drawer; an admin clicking a square toggles without opening.
- Clicking a different row while the drawer is open **switches** it to that player (the drawer's
  contents are derived reactively from `selectedPlayerId`, so no teardown is needed).
- Dismiss via close button, `Esc`, and backdrop click; **trap focus** while open; **return focus**
  to the originating row on close.
- Enter/leave transition honours the admin reduce-motion toggle (`reduceMotionOn`, from
  Enhancements item 7): a plain fade / no slide when reduced motion is on.
- **Live-updating:** while open, the drawer reflects incoming `update_progress` /
  `update_statistics` / `update_users_activity` / `notification` for that user.
- Independent of the gamification rail — the drawer is a monitoring tool and is available even when
  `shouldHideGamification` hides HallOfFame/Champions.
- Two-column layout ~920px wide (profile column + full-height events rail), responsive
  (`min(920px, 96vw)` clamp on narrow viewports); does not block the board.

## Decisions (2026-07-03)

Resolving the prior "Open questions":

- **Placement** → **right-edge slide-over overlay** with a dimming backdrop. Independent of the
  2-col grid, doesn't disturb the board, easiest to make accessibility-correct.
- **Exercise scope** → **selected exercise only** (`selectedExercise`), matching the board.
- **Recent-events depth** → **new backend `get_user_events` endpoint** + per-user retention buffer
  + mock support (not the last-30-global stopgap). This is the only reason the Socket.IO contract
  changes; the change is a single request/ack event.
- **Phasing** → a **design-and-validate phase first** (mockup → refine → sign-off), then
  **vertical, independently shippable build slices**, each reviewed running (mock) and committed on
  its own before the next begins (see [One task at a time] working style). Per the progress-tracking
  convention, mark each phase ✅ Done with its commit ref **in the same commit** as that phase's code.
- **Auto-paginate while open** → **pause** the board rotation while the drawer is open (it hides most
  of the board), resuming on close.
- **Drawer layout** (validated in Phase 0 — **Variant B**) → **two columns at ~2× width (≈920px)**: a
  scrolling **main column** (header + status chips, per-task timing, last-seen + activity sparkline)
  beside a **full-height, independently-scrollable events rail** on the right, so a trainer can browse
  a participant's recent request/webhook history without disturbing the profile next to it. Mockup:
  `docs/mockups/player-drilldown.html` (self-contained; embeds the app's Space Grotesk / JetBrains
  Mono faces and the `.sa-root` tokens).

## Implementation phases

### Summary table

| # | Phase | Layer | Effort | Risk | Status |
|---|---|---|---|---|---|
| 0 | Design proposal & validation | Design | Small | — | ✅ Done (d4d7074) |
| 1 | Drawer shell + header | Frontend | Medium | Med | ⬜ Not started |
| 2 | Per-task timing & gaps | Frontend | Medium | Low | ⬜ Not started |
| 3 | Last-seen & activity sparkline | Frontend | Small | Low | ⬜ Not started |
| 4 | Recent events (backend per-user history + frontend) | Full-stack | Large | Med | ⬜ Not started |

Phase 0 is a pre-build gate — no production code until the look is signed off. Phases 1–4 are each a
working, demonstrable increment on the mock server; 1–3 are frontend-only, and phase 4 is the only
one that touches the backend and the event contract.

---

### Phase 0 — Design proposal & validation

Before any code, agree on the target look. **Gate for everything that follows.**

**Build.**
- A visual mockup of the drawer in the SkillAegis dark theme (the `.sa-root` tokens), showing all
  four content sections at realistic data density — header + status chips, per-task timing list,
  last-seen + sparkline, recent events — plus the open state, the dimming backdrop, and how it sits
  over the board.
- Delivered as a self-contained static mockup (HTML artifact, no wiring) so we can iterate quickly
  on layout, spacing, chip treatment, and exactly what each row shows.
- Iterate on your feedback until the look is agreed.

**Deliverable.** A validated design that phases 1–4 implement against. No production code, no backend
changes.

**Acceptance.** You have signed off on the drawer's look and section layout.

**Status: ✅ Done — d4d7074.** Signed off 2026-07-03 on **Variant B** (two-column: profile column +
full-height events rail). Mockup at `docs/mockups/player-drilldown.html`. Timing/gap chips carry
explanatory tooltips.

---

### Phase 1 — Drawer shell + header

The interaction surface and a shippable drawer that identifies the clicked player.

**Build.**
- New `components/dashboard/PlayerDrawer.vue`, mounted once at the root in `TheDahboard.vue` so the
  overlay + backdrop cover the viewport above the grid.
- Selected-player state in `dashboardState.js`: `selectedPlayerId = ref(null)`, `openPlayer(id)`,
  `closePlayer()`, and a `selectedPlayer` computed that finds the row for `selectedPlayerId` in the
  existing `players` view-model (so the header updates live and returns `null` when closed or the
  player disappears).
- Wiring in `LiveLeaderboard.vue`: row card `@click` → `openPlayer(p.id)`, `cursor:pointer`; task
  squares get `@click.stop` **guarded by `userAuthenticated`** so admin toggling doesn't also open
  the drawer (viewers fall through to the row handler).
- Overlay: slide-over from the right (~920px, clamped to `96vw`), dimming backdrop; enter/leave
  transition gated on `reduceMotionOn`.
- Two-column drawer body (Phase 0 Variant B): a scrolling **main column** holding the profile
  sections beside a **full-height, independently-scrollable events rail** on the right. Phase 1 builds
  the rail's shell + header; its list stays an empty-state placeholder until Phase 4 populates it.
- Pause auto-paginate while the drawer is open: guard `rotatePage` on `selectedPlayerId` so it holds
  the current page, resuming rotation on close.
- Accessibility: `Esc` + backdrop + close-button dismiss; focus trap while open; focus returned to
  the originating row on close.
- Header render: name, org, rank, `score / max_score`, and the status chips from
  `selectedPlayer.status`.

**Data sources.** `players` / `progresses[user_id]` (identity, rank, score, `status`). No new data.

**Files.** new `PlayerDrawer.vue`; edit `LiveLeaderboard.vue`, `dashboardState.js`, `TheDahboard.vue`.

**Acceptance.**
- Clicking a row opens the drawer with correct identity, rank, score/max, and status chips.
- Admin square-toggle still works and does **not** open the drawer; a viewer clicking a square
  opens it.
- `Esc` / backdrop / close all dismiss; focus is trapped while open and returned on close.
- Header updates live when that player scores; auto-paginate rotation pauses while open and resumes
  cleanly on close.

**Status: ⬜ Not started.**

---

### Phase 2 — Per-task timing & gaps

Turn the drawer into a timing profile for the selected exercise.

**Build.**
- New selector in `dashboardState.js` (e.g. `selectedPlayerTasks`) producing, per task in order:
  state (`done` / `available` / `locked`), completion timestamp, and **gap to the previous
  completion** — collect the completed-task timestamps, sort ascending (mirroring
  `get_sorted_timestamps_for_completed_tasks`), gap[i] = t[i] − t[i−1]; the first completion's gap
  is measured from `exerciseStart`.
- "Currently on" = available tasks (`taskRequirementMet` true, not done), highlighted.
- A total clear-time line for players who have finished.
- Render the task list in the drawer, reusing `fmtDur` / `fmtAgo`. Each timing/gap chip carries an
  explanatory `title` tooltip (e.g. `+1:46` → "time on this task — gap since the previous
  completion"; the first task's gap → "measured from the exercise start"), plus the "on now" / "idle"
  / locked chips.

**Data sources.** `tasks_completion[uuid].{timestamp,first_completion}`, `exerciseStart`,
`taskRequirementMet`. No new data.

**Files.** edit `dashboardState.js`, `PlayerDrawer.vue`.

**Acceptance.**
- Per-task states are correct, including locked-by-prerequisite.
- Completion times and per-task gaps match the backend timestamps; "currently on" reflects the
  available task(s).
- The list updates live as the player completes tasks.

**Status: ⬜ Not started.**

---

### Phase 3 — Last-seen & activity sparkline

**Build.**
- Selector deriving from `userActivity[selectedPlayerId]` + `userActivityConfig`: bucket duration =
  `60 / buffer_resolution_per_minute` seconds; last non-zero bucket → "active Ns ago" (via
  `fmtAgo`), or "no activity" when the buffer is empty.
- A mini sparkline over the player's activity buckets, reusing the row heat / timeline bar
  treatment.
- Render a "last seen" line + sparkline in the drawer.

**Data sources.** `userActivity`, `userActivityConfig`. No new data.

**Files.** edit `dashboardState.js`, `PlayerDrawer.vue`.

**Acceptance.**
- Last-seen matches the activity buffer; the sparkline reflects the buckets.
- Both update live on `update_users_activity`.

**Status: ⬜ Not started.**

---

### Phase 4 — Recent events (backend per-user history + frontend)

The only full-stack phase; adds real per-user event depth. Commit backend+mock first (verifiable
by emitting `get_user_events` against the mock), then the frontend section — or together, at the
implementer's discretion.

**Backend.**
- `db.py`: `PER_USER_NOTIFICATION_BUFFER_SIZE` (≈50) and `USER_NOTIFICATION_MESSAGES = {}`
  (`user_id → deque(maxlen=…)`); an `addUserNotification(user_id, notification)` helper; extend the
  notification reset to clear it.
- `notification.py`: `record_notification` also records into the per-user buffer (keyed by the
  notification's `user_id`); new `get_user_events(user_id) -> list`.
- `server.py`: `@sio.event get_user_events(sid, data)` → `notification_model.get_user_events(int(data['user_id']))`.
  **Ungated**, matching the existing `get_notifications` access (the drawer is for all viewers).
- `dev_mock_server.py`: retain per-user history as notifications are generated (each already
  carries `user_id`) and add a matching `get_user_events` handler.

**Frontend.**
- `socket.js`: `getUserEvents(user_id, cb)` emitting `get_user_events`; hold the current player's
  events in reactive state, seed on drawer open, and append-left on the live `notification` push
  when `message.user_id` matches the selected player.
- `dashboardState.js`: `selectedPlayerEvents` selector shaping events for display (reuse the
  `feed` row shaping — method chip, url/target_tool, payload preview).
- `PlayerDrawer.vue`: populate the full-height **events rail** (the shell built in Phase 1), newest
  first, live-appending.

**Contract.** Adds the `get_user_events` request/ack event only; live updates reuse the existing
`notification` push.

**Files.** edit `db.py`, `notification.py`, `server.py`, `dev_mock_server.py`, `socket.js`,
`dashboardState.js`, `PlayerDrawer.vue`.

**Acceptance.**
- Opening the drawer shows that player's recent events, deeper than the global 30-event ring.
- New events for that player appear live; other players' events never leak in.
- The mock serves per-user history; reset clears the per-user buffers.

**Status: ⬜ Not started.**

---

## Feature-level acceptance

- Clicking a participant opens a right-edge drawer showing: identity + status chips, per-task state
  with completion times and per-task gaps, current/available task, last-seen + sparkline, and
  recent events from the per-user backend history.
- Admin task-toggle still works from the row without conflicting with drawer-open.
- Drawer is keyboard-accessible (open focus trap, `Esc` to close, focus return), honours reduced
  motion, and updates live.
- Auto-paginate rotation pauses while the drawer is open and resumes on close; no regression to
  leaderboard rendering.

## Testing

Every phase is demonstrable through the mock server (`backend/dev_mock_server.py`) with **no**
MISP/ZMQ. Open the drawer on a synthetic player and confirm, per phase: identity + status chips
(1); per-task timing/gaps and "currently on" (2); last-seen + sparkline (3); per-user recent events
seeding + live-append (4). Throughout, confirm admin task-toggle still works and that the
auto-paginate rotation pauses while the drawer is open and resumes on close. Phase 4 additionally
requires the mock's new `get_user_events` handler; the on-demand
`/mock/*` controls (`checking/<id>`, `clear/<id>`, `zmq-stale`, …) remain useful for driving live
transitions while the drawer is open.

## Effort / Risk

Large / Medium overall — new interaction surface, one backend endpoint + contract addition, and
accessibility. De-risked by a design gate up front (phase 0) and then four independently reviewable
build slices, with the backend touched only in phase 4.

[One task at a time]: work one phase, report, wait for approval before the next.
