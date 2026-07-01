# PRD — Dashboard Enhancements

| | |
|---|---|
| **Status** | In progress — item 1 done (verified via mock), 5 remaining |
| **Date** | 2026-07-01 |
| **Scope** | Six additive improvements to the live dashboard: (1) restore the per-task "being validated" indicator, (2) turn the Live Feed diode into a connection / data-freshness light, (3) a task-completion bar chart, (4) a first-blood badge, (5) theme consistency, (6) performance at scale. |
| **Non-goals** | No change to the evaluation engine, scoring math, scenario format, or the Socket.IO event contract. Items 1, 2 and 4 restore/surface data the backend **already emits** — no new backend events. |

## Background

The dashboard (`src/components/dashboard/*`) is a pure view over whole-state Socket.IO
snapshots, shaped by `src/socket.js` → `src/components/dashboard/dashboardState.js`. It serves
two audiences at once: **trainers** (situational awareness — who is where, what is hard, is the
data live) and **trainees** (real-time feedback on their own actions + competition).

Three of these items restore signals that existed in the legacy view tree (removed in `22a1b7a`,
"Remove dead legacy view tree") but whose **backend plumbing is still live**:

- **Task-being-validated** — `backend/server.py::sendUserInjectCheckInProgress` still emits
  `user_task_check_in_progress {user_id, inject_uuid}`; `socket.js` still records it into
  `userTaskCheckInProgress` (true for 3s, keyed `${user_id}_${inject_uuid}`). The old
  `scoreViews/TheScoreTable.vue` rendered it as a spinning `faHourglassHalf` on the available
  task cell. The new `LiveLeaderboard.vue` never consumes it.
- **Connection / data-freshness** — `backend/server.py` emits `keep_alive {zmq_last_time}` every
  5s; `ZMQ_LAST_TIME` is refreshed whenever a ZeroMQ message arrives. `socket.js` exposes
  `socketConnected` and `zmqLastTime`. The old `TheSocketConnectionState.vue` showed a
  green/red circle + "Last ZMQ message: Ns ago". The new dashboard shows a *hardcoded* mint
  blinking dot in the Live Feed header that reflects nothing.
- **First blood** — `backend/exercise.py::mark_task_completed` maintains a `first_completion`
  boolean on the earliest completer of every task; it rides along in
  `progresses[uid].exercises[ex].tasks_completion[task_uuid].first_completion`. Nothing renders it.

Items 3 (task-completion chart) and 4 (first blood) are derivable **entirely client-side** from
data already in `progresses`. Item 5 is a design-consistency decision. Item 6 is a reactivity /
rendering refactor and is the only large, higher-risk item.

## Summary table

| # | Item | Effort | Risk | Status |
|---|------|--------|------|--------|
| 1 | Restore per-task "being validated" spinner | Small | Low | ✅ Done |
| 2 | Connection / data-freshness diode (Live Feed) | Small–Med | Low | ☐ Planned |
| 3 | Task-completion bar chart | Medium | Low | ☐ Planned |
| 4 | First-blood badge | Small–Med | Low | ☐ Planned |
| 5 | Theme consistency — retire light-mode toggle (dark-only) | Small | Low | ☐ Planned |
| 6 | Performance at scale | Large | Med | ☐ Planned — see discussion |

**Recommended sequencing:** ship 1 → 2 → 4 → 3 first (small, self-contained, high signal, each
independently useful). Do **item 6 before, or interleaved with, item 3** — item 3 adds another
per-tick view-model, so it should land on top of item 6's "split time-driven from data-driven"
refactor rather than adding to the pre-refactor load. Item 5's direction is decided (retire the
light-mode toggle; dark-only) and can land at any time.

**Testing:** every visual item must be demonstrable through the mock server
(`backend/dev_mock_server.py`) with **no** MISP/ZMQ. Items 1, 2 and 4 need small mock additions
because the mock does not currently emit `user_task_check_in_progress`, always sends a *fresh*
`zmq_last_time`, and hardcodes `first_completion: False`. These mock additions are part of each
item's acceptance.

---

## 1. Restore per-task "being validated" indicator

**Problem.** When a trainee performs an action, the backend re-checks their available tasks and
emits `user_task_check_in_progress` for each inject it evaluates. This is the trainee's
real-time "the system saw what I did and is checking it" feedback — the moment the board feels
*live and responsive* to their own actions. The new leaderboard drops it: an available task is
just a static square with a blinking dot, whether or not it is being evaluated right now.

**Proposed change.**
- **Consume the existing state, in the component (not the big view-model).** In
  `LiveLeaderboard.vue`, look up `userTaskCheckInProgress[`${p.id}_${t.uuid}`]` per task square.
  Import `userTaskCheckInProgress` from `@/socket`. Deliberately do **not** fold `checking` into
  the `players` computed in `dashboardState.js` — that computed is the hot path (item 6), and
  check events fire in bursts and self-reset after 3s; reading them in the component keeps the
  leaderboard rebuild off the validation cadence.
- **Render a rotating indicator** on the *available* task square while checking. Keep the design
  language of the current squares: overlay a small spinning ring/arc (reuse a keyframe like the
  existing `sa-*` rotations; add an `@keyframes sa-spin { to { transform: rotate(360deg) } }`
  honoring `prefers-reduced-motion`, which the project already respects globally). While
  `checking` is true, show the spinner in place of (or layered over) the `sa-blink` availability
  dot. Completed and locked squares are unaffected.
- Optional polish: a brief settle pulse on the square if it flips to `done` right after a check
  (reinforces "your action counted").

**Mock impact (required for test).** Add `user_task_check_in_progress` emission to
`backend/dev_mock_server.py`: on each sim tick, for a small random subset of players' *available*
tasks, emit the event (mirroring the real 3s window). Add a `POST /mock/checking/<user_id>` poke
that fires the event for that player's current available task, so the spinner can be forced for a
screenshot.

**Affected files.** `src/components/dashboard/LiveLeaderboard.vue`,
`src/TheDahboard.vue` (only if the `sa-spin` keyframe goes in the global block),
`backend/dev_mock_server.py`, `CLAUDE.md` / `README.md` (document the new mock poke).

**Acceptance.**
- Performing/forcing a check makes the corresponding available task square spin for ~3s, then
  settle back to the blinking-available state (or to done if it completed).
- No spinner on completed or locked squares.
- With `prefers-reduced-motion`, the indicator degrades to a static/opacity cue, not a spin.
- Visible via the mock (`/mock/checking/<id>`), no real backend.

**Status: ✅ Done (verified via mock, commit pending).** `LiveLeaderboard.vue` reads
`userTaskCheckInProgress[`${p.id}_${t.uuid}`]` per available square via a `checkingTask()` helper
(kept out of the `players` view-model, as specified) and renders a `.sa-task-spin` cyan arc
(`@keyframes sa-spin`) in place of the `sa-blink` availability dot while checking. Completed/locked
squares are untouched. Under `prefers-reduced-motion` the global `main.css` rule freezes the spin to
a static ring. Mock: `dev_mock_server.py` emits `user_task_check_in_progress` for a few movers'
next available task each tick, plus a `POST /mock/checking/<user_id>` poke; documented in
`CLAUDE.md` + `README.md`. The optional "settle pulse" polish was skipped (kept the change tight).

---

## 2. Connection / data-freshness diode (Live Feed)

**Problem.** The Live Feed header has a mint blinking dot that is purely decorative. Meanwhile
the app already knows whether the socket is connected (`socketConnected`) and how long since the
last ZeroMQ message (`zmqLastTime`, refreshed via `keep_alive` every 5s). If the socket drops or
MISP/ZMQ goes quiet, the board **silently freezes** and the trainer keeps trusting stale numbers.

**Proposed change.** Promote the existing dot to a real status light driven by a new
`connectionHealth` view-model, with three states:

| State | Condition | Colour | Label | Motion |
|---|---|---|---|---|
| **LIVE** | `socketConnected` && `now - zmqLastTime < STALE_SEC` | mint (current) | `LIVE` | blink (current) |
| **IDLE / no data** | `socketConnected` && (`zmqLastTime` null or `≥ STALE_SEC`) | amber | `NO LIVE DATA` | slow blink |
| **OFFLINE** | `!socketConnected` | red | `OFFLINE` | solid / slow pulse |

- **New view-model** in `dashboardState.js`: `connectionHealth` computed from `socketConnected`,
  `zmqLastTime`, and the shared `now` clock (import `socketConnected`, `zmqLastTime` from
  `@/socket`). It is O(1), so ticking every second is free.
- **Threshold discussion.** `keep_alive` is every 5s, so socket-liveness is known within ~5–10s.
  ZMQ silence is *not* itself an error — a calm room legitimately produces no MISP traffic — so
  amber is a soft "no live data" warning, not a failure. Recommend `STALE_SEC = 30` (tunable
  constant). Red (socket down) is the only hard-error state.
- **Presentation.** Keep it compact in the Live Feed header where the dot lives; add a short
  text label beside it and a hover tooltip with detail ("Connected · last data 8s ago" /
  "Reconnecting…"), echoing the old `TheSocketConnectionState` "Last ZMQ message: Ns ago".
- Colours come from existing tokens (`--sa-mint`, a gold/amber token, `--sa-danger`).

**Mock impact (required for test).** The mock always sends a fresh `zmq_last_time`, so only LIVE
is reachable today. Add controls to exercise the other two:
- `POST /mock/zmq-stale` — freeze/age `zmq_last_time` (stop advancing it) → drives **amber**.
- **OFFLINE** is testable by stopping the mock (socket drops) — document that; optionally add
  `POST /mock/zmq-fresh` to resume.

**Affected files.** `src/components/dashboard/dashboardState.js`,
`src/components/dashboard/LiveFeed.vue`, `backend/dev_mock_server.py`, `CLAUDE.md`/`README.md`.

**Acceptance.**
- Normal operation → mint "LIVE" blinking dot (unchanged look).
- `/mock/zmq-stale` → dot turns amber "NO LIVE DATA" within ~`STALE_SEC`; tooltip shows the age.
- Stopping the mock → dot turns red "OFFLINE"; reconnecting restores mint.
- No new backend events; reads only `socketConnected` + `zmqLastTime`.

---

## 3. Task-completion bar chart

**Problem.** The board shows each *player's* progress, but not the class-wide shape: *which task
is the wall?* A trainer currently has to scan the whole grid column-by-column to infer that only
2/20 cleared task 5. This is the single most useful "what should I explain next" signal and it is
missing.

**Proposed change.** A compact **per-task completion** mini-chart for the selected exercise: one
bar per task, height = fraction of participants who have cleared it, coloured by difficulty
(low completion → amber/red, high → mint), tooltip = task name + "X / N cleared (Y%)".

- **View-model** in `dashboardState.js`: `taskCompletion` computed — for the selected exercise,
  for each task, count players with a truthy `tasks_completion[task.uuid]` over the number of
  participants in that exercise. Derived from `progresses` only (no `now` dependency), so it
  recomputes on data change, not per tick. Reuse `taskLabels` / task numbering already present.
- **Rendering:** hand-rolled `<div>` bars, matching the existing activity-timeline / heat visual
  language (the project imports `vue3-apexcharts` but never uses it — no reason to add a chart
  lib and its per-tick overhead here; optionally drop the unused import as cleanup). Bars scale
  down for many-task scenarios, consistent with the numbered-header threshold (>12 tasks) already
  in `LiveLeaderboard.vue`.
- **Placement (recommendation):** in the **left/leaderboard column**, as a slim band (e.g. above
  the global-progress footer or directly under the column header), so it is **always visible** —
  the trainer signal must not disappear when gamification is hidden (`shouldHideGamification`
  removes Hall of Fame + Champions from the rail). Alignment with the task columns above is a
  nice-to-have but not required; a standalone labelled strip ("TASK COMPLETION") is sufficient.
- Respects the selected exercise (switches with the scenario tabs).

**Mock impact.** None required — the mock already produces a spread of per-task completion across
players. The prerequisite chain on exercise 2 gives a naturally decaying completion curve to look
at. (`/mock/empty` and `/mock/clear` bracket the 0% and 100% extremes.)

**Affected files.** `src/components/dashboard/dashboardState.js`, one new small component (e.g.
`TaskCompletionChart.vue`) + wiring in `LiveLeaderboard.vue` (or `TheDahboard.vue`),
optional `src/main.js` cleanup (drop unused apexcharts).

**Acceptance.**
- One bar per task of the selected exercise; height/colour reflect the cleared fraction; tooltip
  shows task name + count + %.
- Updates live as players complete tasks; switches with the exercise tabs.
- Remains visible when gamification is hidden.
- Legible for both small (≤12) and large (>12) task counts.

---

## 4. First-blood badge

**Problem.** Being *first* to solve a specific task is a distinct, high-energy achievement that
the data already records (`first_completion`) but the UI throws away. Surfacing it rewards speed
per-task (not just totals) and gives trainees another axis to compete on.

**Proposed change.** Two surfaces, both client-side from `tasks_completion[...].first_completion`:

1. **Leaderboard row badge (primary).** Count each player's first-bloods across the selected
   exercise's tasks; show a small `🩸×N` (or 🥇) marker among the row's name-line icons
   (beside the existing 🏅 cleared / 🔥 fire icons in `LiveLeaderboard.vue`), tooltip listing
   which task numbers. Extend the `players` view-model row with `firstBloods` (count) + the task
   list — cheap, derived from the same `tc` already being iterated per row, **no extra passes**.
2. **"Just Cleared" tag (secondary).** In the Live Feed "Just Cleared" strip
   (`justCleared` in `dashboardState.js` + `LiveFeed.vue`), flag entries whose completion was a
   first_completion with a small "1st" tag, so first-bloods stand out in the live stream.

- **Optional stretch:** a one-shot toast ("First blood — alice on Task 5") via the existing
  Toaster, and/or a first-blood pop analogous to the `justScored` "+N" (needs transition
  detection like the existing `completions` watcher). Gate behind the same reduced-motion rules.
- **Semantics note:** `first_completion` is recomputed by the backend if a task is un-marked and
  re-completed (it re-selects the earliest), so the badge self-corrects. Admin-marked completions
  count — acceptable and consistent with scoring.

**Mock impact (required for test).** The mock hardcodes `first_completion: False`. Update
`backend/dev_mock_server.py` to stamp `first_completion: True` on the earliest completer of each
task (mirroring `mark_task_completed`), so at least a few players hold first-bloods on first paint.

**Affected files.** `src/components/dashboard/dashboardState.js`,
`src/components/dashboard/LiveLeaderboard.vue`, `src/components/dashboard/LiveFeed.vue`,
`backend/dev_mock_server.py`.

**Acceptance.**
- Players who were first to clear ≥1 task show a first-blood badge with the correct count +
  task list in the tooltip.
- The "Just Cleared" strip flags first-completions.
- Marking a first-blood task incomplete then re-completing moves the badge correctly.
- Visible via the mock with no real backend.

---

## 5. Theme consistency — retire the light-mode toggle (dark-only)

**Decision (2026-07-01): Option A — commit to dark-only and remove the light-mode toggle.** The
live dashboard is a projected command-center wall; a light theme adds little, and a real light
palette would mean re-authoring the entire neon-on-dark token system plus auditing the many
hardcoded color literals in the dashboard components. Going dark-only guarantees no surface can
drift onto the wrong theme.

**Problem.** There is a dark/light toggle (`TheThemeButton` → `settings.js::darkModeOn` → adds
`.dark` to `<body>`; default dark). The admin panel + app shell use Tailwind `dark:` variants and
switch. **The live dashboard does not:** `.sa-root` defines a single dark token layer and every
component uses those tokens (plus many hardcoded hex/rgba literals). So toggling to light flips
the app shell and the admin modal to light while the dashboard behind them stays dark — a visible
inconsistency, and the toggle itself lives inside the admin modal that covers the dashboard.

**Proposed change.**
- **Remove the toggle UI:** delete `src/components/TheThemeButton.vue` and its row in
  `src/components/adminPanel/ControlButtons.vue`.
- **Force dark permanently:** ensure `.dark` is applied to `<body>` at startup (`App.vue`) so the
  admin panel's Tailwind `dark:` variants always resolve. Retire the now-dead toggle path in
  `src/settings.js` — either remove `darkModeOn`/`darkModeEnabled`, or pin `darkModeOn` to a
  constant `true` (with a note) if anything else still reads it.
- **Verify the admin panel** (modal + Control Panel / Exercises / Diagnostic tabs) renders
  correctly in the now-always-on dark treatment; fix any element that only carried light styling.
- **No change** to the dashboard `.sa-root` tokens — they are already the single dark layer.

**Affected files.** `src/components/TheThemeButton.vue` (removed),
`src/components/adminPanel/ControlButtons.vue`, `src/settings.js`, `src/App.vue`, and any
admin-panel component needing a dark fix.

**Acceptance.**
- No dark/light toggle is presented anywhere in the app.
- Dashboard and admin panel are consistently dark; no surface renders light.
- No dead theme-switching code left behind (or `darkModeOn` pinned `true` with a note explaining
  why it stays).

---

## 6. Performance at scale — discussion

Item 6 is deliberately a discussion + phased plan, not a fixed spec. It is the largest and
highest-risk item because it touches the reactivity that drives every animation.

### Current architecture

Whole-state snapshots arrive over Socket.IO; `dashboardState.js` turns them into `computed`
view-models the components render. A single shared clock `now = ref(Date.now())` ticks **every
1000ms** and several view-models read it.

### Hot paths (measured by reading the code)

1. **`players` recomputes every second.** It reads `now.value` (for `justScored`, on-fire
   countdown/`fireBarPct`, `justCompleted`), so it rebuilds **even with no data change**. Each
   rebuild is O(P×T): for every player it maps every task into an object with several inline
   style strings, then sorts the rows twice (a score-rank pass + the display sort). At 20×13 this
   is nothing; at 100×25 or 200×30 it is thousands of objects + string builds + two sorts **per
   second**.
2. **`elapsed` is O(P×T) every second** — it scans every player's every completion timestamp to
   find the minimum, purely to render a clock.
3. **`champions` recomputes every second** — it reads `now` (page-rotation index) and re-derives
   all fire/speed/trophy decoration each time.
4. **Deep watch on `progresses`.** `watch(() => progresses.value, …, { deep: true })` walks the
   whole progress object — but `state.progresses` is **reassigned wholesale** on every
   `update_progress`/`getProgress`, so its identity already changes; the deep flag is unnecessary
   overhead proportional to roster size on every update.
5. **DOM holds all P rows always.** Auto-pagination sets off-page rows to `opacity:0` /
   `pointer-events:none` but leaves them mounted, so the DOM carries O(P×T) task squares + heat
   bars + per-row transitions regardless of page. This is the dominant browser cost at large P.
6. **`updateTaskCheckInProgress` iterates P×E×T** on every progress update to seed booleans.
7. **Additive load:** item 1 (checking) and item 3 (task-completion chart) each add per-tick or
   per-update work; they must be designed to *not* pile onto the `players` recompute (see items 1
   and 3 above).

### Target (to agree on)

Propose: **smooth (no dropped frames; leaderboard recompute < ~16ms) at 100 players × 25 tasks,
and functional (usable, no crash, graceful) at 200 × 30**, on a typical laptop driving a
projector. The mock's `--players N` / `--tick S` flags are the benchmark harness (already
supports 100–200). *Confirm the real-world ceiling: what is the largest session you actually run?*

### Proposed optimizations (ranked by impact / effort)

1. **Split time-driven from data-driven state (highest impact).** Build the heavy leaderboard
   (scores, ranks, order, the O(P×T) task grid) from `progresses`/stats **only**, so it recomputes
   on data change — not every second. Overlay the transient per-row effects (on-fire countdown %,
   `justScored` +N, `justCompleted` burst) either as a thin second computed that maps the stable
   base rows and only touches time fields, or in the component. This removes the per-second O(P×T)
   rebuild, the biggest CPU win.
2. **Render only the visible page (windowing).** Mount just the current page's rows (~14) instead
   of all P with `opacity:0`. Cuts DOM from O(P×T) to O(rowsPerPage×T) — the biggest DOM/browser
   win at large P. *Tradeoff:* lose cross-page move animations (invisible anyway); keep the
   within-page re-sort transitions.
3. **Cache `elapsed` start.** Recompute the earliest-timestamp anchor only on progress change;
   format it against `now` cheaply each tick (O(1)/sec instead of O(P×T)/sec).
4. **Split `champions`.** Separate the `now`-based rotation index from the stats-based decoration
   so decoration recomputes on stats change, not every second.
5. **Drop the deep watch** on `progresses` → a normal watch on identity (it's replaced wholesale).
6. **Throttle inbound `update_progress` application** (batch a burst into one apply via rAF /
   short debounce) so a flurry of backend emits under load causes one re-render, not N. (A
   `debouncedGetProgress` already exists for `new_user`/`refresh_score`; extend the spirit to the
   push path if bursts are observed.)
7. **(Optional, larger) Move inline computed style strings to CSS classes / data-attributes** so
   recomputes stop building thousands of strings + GC. Mostly moot once (1) slashes recompute
   frequency; revisit only if profiling still shows string/GC cost.

### Plan & risk

Phase in order 1 → 2 → 3 → 4 → 5, profiling after each with the mock at 100 and 200 players
(browser Performance panel / FPS; optionally a tiny dev-only perf overlay). The main risk is
regressing the transient animations (fire bar, +N pop, all-clear burst) while decoupling them
from the clock — the mock's scenario controls (`/mock/clear/<id>`, `/mock/clear`, on-fire seeding)
are the regression harness. Land item 6 (at least steps 1–2) **before** item 3 so the new chart
sits on the optimized base.

### Open questions

- Real maximum session size (sets the target ceiling)?
- Is losing cross-page row animations (windowing, step 2) acceptable? (Recommended yes.)
- Acceptable to reduce some effects' update rate (e.g. fire bar) if needed for headroom?

---

## Feature-level acceptance

- Items 1–4 are each demonstrable end-to-end through the mock server with no MISP/ZMQ, including
  the mock additions called out per item.
- Item 5 reaches a single, consistent theme story across dashboard + admin (per the chosen option).
- Item 6 hits the agreed target on the mock at the agreed player count, with the transient
  animations intact.
- No changes to the evaluation engine, scoring, scenario format, or the Socket.IO event contract;
  no new backend events (mock-only additions are dev-only).

## Effort / Risk

Items 1, 2, 4 are small and low-risk (surface existing data). Item 3 is medium, low-risk
(additive view-model + component). Item 5 is decision-gated (low–medium once chosen). Item 6 is
large and medium-risk (reactivity/rendering refactor) — phase it and profile against the mock.
