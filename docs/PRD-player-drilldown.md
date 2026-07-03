# PRD — Player Drill-Down Panel

| | |
|---|---|
| **Status** | Draft |
| **Date** | 2026-07-03 |
| **Scope** | SkillAegis-Dashboard frontend (`src/components/dashboard/*`), with one optional backend note (per-user event history). |
| **Non-goals** | No change to the evaluation engine, scenario format, or scoring math. No change to the Socket.IO event contract for v1 — unless the optional richer per-user event history is chosen (see Open questions). |

## Background

The live dashboard (`src/components/dashboard/*` — `DashboardHeader`, `LiveLeaderboard`,
`HallOfFame`, `ChampionsSlot`, `LiveFeed`) is a pure view over whole-state Socket.IO snapshots,
shaped by `socket.js` → `dashboardState.js`. It serves two audiences at once: **trainees**
(real-time feedback on their own progress + gamification) and **trainers** (situational
awareness — who is where, what is hard, is the data live).

It is a strong **scoreboard**, but not yet a **monitoring tool**. This PRD was split out of the
"Dashboard Improvements" PRD (item 3.1); its other items are complete and merged into `develop`.
The player drill-down is the sole remaining feature and is large enough to warrant its own document.

**Goal served.** Trainer situational awareness — "what's going on live", per participant.

## Problem

A trainer cannot inspect a single participant: which task they are on, how long each task took,
when they were last active, and what they have been doing. Today, clicking a leaderboard row does
nothing for a viewer, and for an admin it only toggles a task square. The board aggregates; it
does not profile.

## Proposed change

Clicking a participant (outside the task squares) opens a **side drawer** that profiles that one
participant for the selected exercise. Available to **all viewers** (read-only monitoring); admins
additionally get the existing per-task toggle controls inside the drawer.

### Drawer contents

1. **Header** — name, org, rank, score / max_score, and live status chips already present in
   `progresses[user_id].status` (`is_on_fire`, `is_speed_runner`, `is_on_all_house_fame`,
   `trophies`).
2. **Task list with timing** — each task's state (done / available / locked-by-prerequisite) and,
   for completed tasks, the completion time and the **gap to the previous completion**
   (time-per-task). Source: `tasks_completion[inject_uuid].timestamp`; compute gaps from the
   sorted timestamps exactly as `leaderboard.py:get_sorted_timestamps_for_completed_tasks` does.
   "Currently on" = the available task(s) whose prerequisites are met but not yet done
   (`taskRequirementMet` already exists in `dashboardState.js`).
3. **Last seen / activity** — derive from `userActivity[user_id]` (the per-bucket activity buffer)
   and `userActivityConfig` (bucket size): last non-zero bucket → "active Ns ago", plus a small
   sparkline reusing the heatmap data.
4. **Recent events** — this participant's recent entries from the live feed
   (`notifications` filtered by `e.user` matching the participant's email).
   ⚠️ **Limitation / decision point:** `socket.js` keeps only `MAX_LIVE_LOG = 30` global events,
   so per-user history will be sparse. Options: (a) ship with "recent (last 30 global)" and label
   it as such; (b) add a backend `get_user_events` endpoint / per-user retention. **Recommend (a)**
   for v1, (b) as a fast-follow if trainers ask for more depth.

### Interaction & accessibility

- Row click opens the drawer; clicking a **task square** must still toggle (admin) — stop
  propagation on the square so the two interactions don't conflict.
- Drawer is dismissible via close button, `Esc`, and backdrop click; trap focus while open;
  return focus to the originating row on close (pairs naturally with the existing reduced-motion
  handling).
- Live-updating: while open, the drawer reflects incoming `update_progress` / `update_statistics`
  for that user.
- Does not block the board — overlays the right rail or slides over the feed; the leaderboard
  stays visible behind/beside it.

### Open questions

- **Exercise scope:** profile the `selectedExercise` only (simplest, matches the board) or
  aggregate across all `active_exercises`? Recommend selected-exercise for v1.
- **Placement:** reuse/extend the existing right rail vs. a dedicated overlay drawer.
- **Backend dependency:** confirm whether richer per-user event history (option b above) is in
  scope for v1.

### Affected files (anticipated)

- New `components/dashboard/PlayerDrawer.vue`.
- Wiring in `LiveLeaderboard.vue` (row click + selected-player state).
- New view-model selectors in `dashboardState.js` (per-task timing, last-seen, per-user feed).
- Possibly a new socket action + backend endpoint if option (b) is chosen.

### Acceptance criteria

- Clicking a participant opens a drawer showing: identity + status chips, per-task state with
  completion times and per-task gaps, current/available task, last-seen, and recent events.
- Admin task-toggle still works from both the row and the drawer without conflict.
- Drawer is keyboard-accessible (open focus, `Esc` to close, focus return) and updates live.
- No regression to leaderboard rendering or the auto-paginate rotation while the drawer is open.

### Testing

Demonstrable through the mock server (`backend/dev_mock_server.py`) with **no** MISP/ZMQ: open the
drawer on a synthetic player and confirm per-task timing/gaps, "currently on", last-seen, status
chips, live updates, and that admin task-toggle + the auto-paginate rotation are unaffected.

### Effort / Risk

Large / Medium — new interaction surface, possible backend touch, accessibility.
