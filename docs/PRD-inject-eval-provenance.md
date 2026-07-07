# PRD — Inject-Evaluation Provenance & Debugging

| | |
|---|---|
| **Status** | Phases 0–4 ✅ (Phase 4: drawer completed-task "cleared by" provenance + View evaluation opening EvaluationDebug, verified on the mock) — building phases 5–6 |
| **Date** | 2026-07-06 |
| **Scope** | SkillAegis-Dashboard, full-stack. **Backend** eval path + retention (`backend/exercise.py`, `backend/target_tools/{misp,webhook}/*`, `backend/utils.py`, `backend/db.py`, `backend/server.py`), **frontend** (`src/socket.js`, `src/components/dashboard/*`, new `EvaluationDebug.vue`), and **mock** parity (`backend/dev_mock_server.py`, `CLAUDE.md`). |
| **Non-goals** | No change to scoring math, the scenario/CEXF format, or which actions are *accepted* for evaluation. No change to the evaluation **semantics** (same engine, same pass/fail) — we only stop discarding the debug trace it already produces and record where a completion came from. **suricata** target tool is out of scope (its shell-out/pcap result has a different shape). The dashboard debug tool is a **read-only inspector of a captured attempt**, not a live re-runner like the Editor. |

## Instructions
Whenever you have a doubt, ask me. Build one phase at a time, each demoable on the mock server and committed on its own; mark each phase ✅ Done with its commit ref **in the same commit** as that phase's code (house convention).

## Background

The live dashboard (`src/components/dashboard/*`) is a pure view over whole-state Socket.IO
snapshots via `socket.js` → `dashboardState.js`. The Python backend subscribes to MISP over ZeroMQ
(and accepts webhook posts), runs the evaluation engine, and emits the state the board renders.

Two facts about today's system drive this PRD:

1. **The evaluation engine already produces a rich, structured "why" trace — and throws it away
   live.** `eval_data_filtering` / `eval_python` (`backend/utils.py:35-62,92-93`) accept a `debug`
   flag and, when set, return `(eval_state, debug_steps)` where each step is
   `{message, data, style}` (`style` ∈ `primary` / `success` / `fail` / `error` / `''`). This is
   exactly the trace the **SkillAegis-Editor** "Inject Tester" renders. But the live routers
   (`backend/target_tools/misp/inject_eval.py`, `.../misp/exercise.py:44-54`) call the evaluators
   **without** `debug`, so only a boolean survives; the webhook router even computes the tuple and
   discards the trace (`.../webhook/exercise.py:23`). The engine the Editor imports to power its
   tester is *the same module the Dashboard already runs* — the capability is present, unused.

2. **A completion has no provenance, and the feed has no outcome.** `mark_task_completed`
   (`backend/exercise.py:299-315`) records only `{user_id, timestamp, first_completion}` — no link
   to the action that triggered it. Meanwhile each Live Feed `notification` carries a unique `id`
   (`backend/notification.py:166-191`) but is emitted on a **separate code path** from evaluation
   (`server.py:361-381` records/emits the notification, then `check_active_tasks` runs
   independently) — the two share no identifier. On the client this leaves two disconnected worlds:
   raw traffic (`notifications` / `userEvents`, rich payloads, no task link) and completion state
   (`progresses[].tasks_completion` = only `{timestamp, first_completion}`, no event/eval link).

**Reference — the Editor's model (what we mirror).** `SkillAegis-Editor/src/Views/InjectTester.vue`
POSTs `{strategy, params, test_data, context}` and renders the response
`{outcome: 1|2, debug: [[step,…],…]}` as: an **Outcome** pill (Successful / Failed / Pending /
Waiting; green / red / purple / amber), then a **Debug** panel — a numbered, colour-grouped vertical
timeline (one group per evaluation parameter), each step showing a `success` / `fail` / `error`
pill + message and a `<pre>` dump of the extracted `data`; for the `python` strategy a
Status / Exit code / Duration table plus STDOUT / STDERR blocks. Backend contract:
`SkillAegis-Editor/main.py:345-401` (`outcome = 1|2`, `debug` = list-of-groups). We reuse this
data shape and visual language verbatim so the two apps stay consistent.

## Problem

When a trainee's action does **not** complete the task they expected — or a trainer is asked "why
didn't that count?" — the dashboard offers nothing. You can see *that* a task is (in)complete and
you can see raw traffic, but you cannot see **which action cleared a task**, **which tasks an action
was checked against**, or **why a check failed** (which condition, expected vs. actual). The
Editor can answer this for a *hypothetical* payload; the live training run cannot answer it for what
*actually happened*.

## Proposed change

Capture, at evaluation time, the outcome and debug trace of every check, tie completions to the
action that caused them, and surface all of it in four places — reusing the Editor's
`{outcome, debug}` shape and outcome/debug visual language throughout.

### The four surfaces

1. **Live Feed — completion pip (completed-only).** A small ✓ marker + cleared-task name on the
   feed row for an action that completed a task. Nothing is shown for actions that were evaluated
   and completed nothing, nor for un-evaluated traffic — the feed stays quiet; the diagnostics live
   in the drawer.

2. **Player drawer, completed tasks — provenance ("cleared by").** Each done task row gains a
   "cleared by `<method> <url>` @ `<time>`" line and a **View evaluation** affordance that opens the
   passing trace in the Debug view. Sourced from durable provenance carried on the completion record
   (below), so it survives even after the attempt buffer has rolled over.

3. **Player drawer, event history — per-event outcome.** Each event row in the existing RECENT
   EVENTS rail gains an outcome badge: **✓ completed `<task>`**, or **checked N task(s)** when the
   action was evaluated but cleared nothing. Expanding a "checked" row lists each task that was
   checked with its pass/fail and the inject's `result` label; a **Debug** control opens the full
   trace. Events that were not evaluated (or were debounced) carry no badge.

4. **Debug view — the debugging tool (`EvaluationDebug.vue`).** A shared, read-only renderer of a
   captured attempt's `{outcome, debug}`, styled like the Editor's Inject Tester (Outcome pill +
   numbered colour-grouped step timeline; per-step success/fail/error pills; extracted-data dumps;
   python Status/Exit/Duration/STDOUT/STDERR). It shows the trace **as captured at the moment of the
   action** — deliberately not re-run — because app/MISP state changes between the attempt and now
   would make a re-run misleading.

### Data model (backend)

**A. Evaluation attempt — the new record, retained per user (bounded).** Each incoming action that
triggers `check_active_tasks` for a user produces **one** attempt aggregating every *available* task
it was checked against, each check carrying the debug trace:

```
EvaluationAttempt = {
  id, user_id, timestamp,
  target_tool: 'MISP' | 'webhook',
  trigger: {                       # the Live Feed row that caused this evaluation
    notification_id, origin,       # 'zmq' | 'webhook'  — links to the feed
    time, http_method, url,
    payload,                       # snapshot of the evaluated data, truncated (see risks)
  },
  completed_any: bool,
  checks: [                        # one per available task evaluated on this action
    {
      inject_uuid, inject_name, result_label, join_type,   # 'AND' | 'OR'
      outcome: 1 | 2,              # task-level (after join)  — SUCCESS | FAIL
      completed_now: bool,
      evaluations: [               # one per inject_evaluation entry
        { evaluation_strategy, result_label, outcome: 1|2, score_range,
          debug: [[{message,data,style}, …], …] }   # the trace, or synthesized for query_mirror
      ],
    }
  ],
}
```

Stored in `db.USER_EVALUATION_ATTEMPTS[user_id]` = `deque(maxlen = ATTEMPT_BUFFER_SIZE)` (config,
default ~20). Ephemeral — **not** persisted to `backup.json`. This is the "check what went wrong on
my last tries" store, per your decision to capture live and keep the last X per user.

**B. Completion provenance — session-durable (in-memory), compact, on the completion entry.**
`mark_task_completed` attaches to the entry the origin of the clear so surface (2) works even after A
rolls over:

```
tasks_completion[uuid] entry = {
  user_id, timestamp, first_completion,        # existing
  provenance: {
    notification_id, attempt_id,               # attempt_id may later evict from A
    trigger: { origin, time, http_method, url },
    passing: [ {evaluation_strategy, result_label} ],   # compact; full trace lives in A while retained
  }
}
```

This rides the **existing** `update_progress` snapshot — `get_completion_for_users` already ships
the whole entry (`backend/exercise.py:294`), so extending the entry needs **no new event** for
surface (2)'s basic "cleared by" line. `provenance` is session-durable in memory (it survives
buffer A rolling over) but is **stripped before `backup.json` is written** — all evaluation data is
memory-only. After a restore-from-backup, completed tasks simply carry no `provenance` (the "cleared
by" line is blank), an acceptable degradation on that recovery path. The full trace stays in buffer A
while retained.

### Socket.IO contract (additions only; no existing event changes)

- **Extend** `update_progress` completion entries with `provenance` (B) — no new event.
- **New request/ack** `get_user_evaluations` → `[EvaluationAttempt]` for a `user_id` (seed the drawer
  on open, mirroring `get_user_events`).
- **New push** `user_evaluation_recorded` → `{user_id, attempt}` (the client appends when the drawer
  is open for that user — mirrors how `notification` feeds `userEvents`).
- **New push** `notification_outcome` → `{notification_id, user_id, completed_tasks:[{uuid,name,first_completion}]}`,
  emitted **after** evaluation so the client can light the feed pip on the row it already rendered.
  Emitted only when something was completed (feed is completed-only).

### Frontend

- `socket.js`: new reactive `userEvaluations` (+ ack/seed + `user_evaluation_recorded` append), and
  merge `notification_outcome` onto the matching feed/user-event rows by `notification_id`.
- `dashboardState.js`: selectors joining `userEvents` ↔ `userEvaluations` by `notification_id` for
  the event-history badges; read `tasks_completion[uuid].provenance` for the completed-task line.
- `LiveFeed.vue`: completed-only pip.
- `PlayerDrawer.vue`: completed-task "cleared by" + View evaluation; event-row outcome badges +
  expand + Debug.
- New `EvaluationDebug.vue`: the shared Editor-style outcome+debug renderer (dark `.sa-root` theme).

### Mock parity (`dev_mock_server.py`)

The mock speaks the exact same contract with synthetic data (per `CLAUDE.md`, the UI is developed
against it with no MISP/ZeroMQ). It must: synthesize `EvaluationAttempt`s (both passing and failing,
with realistic `data_filtering`- and `python`-style traces), attach `provenance` to completed tasks
in the progress snapshot, answer `get_user_evaluations`, push `user_evaluation_recorded`, and emit
`notification_outcome` when a mock action clears a task. New on-demand controls (documented in
`CLAUDE.md`): `eval-pass/<user_id>` and `eval-fail/<user_id>` to inject an inspectable attempt.

## Decisions (2026-07-06)

- **Capture model → live capture, bounded retention** (not on-demand). Every evaluation records its
  outcome + debug trace; keep the last X attempts **per user**. Rationale: the trainer/trainee wants
  to see what went wrong on *their last try*, and on-demand re-run is unfaithful because app/MISP
  state changes between the attempt and the check. Cost is bounded by the per-user cap; note
  `debug=True` adds **no** extra MISP/sandbox fetches — the data is fetched once regardless — so the
  marginal cost is retained memory + serialization, not extra I/O.
- **Audience → everyone sees everything.** No admin gating on provenance, failure detail, or the
  Debug view. (Acknowledged: raw payloads/traces become visible on the public/projector view; this
  is consistent with the feed already exposing request payloads.)
- **Target tools → MISP + webhook.** They share the jq/python debug-trace format. suricata is out of
  scope (different result shape); revisit later if needed.
- **Feed indicator → completed-only.** The feed marks completions; failure diagnostics live in the
  drawer, not the feed.
- **Debug tool → read-only captured inspector**, not a live re-runner (unlike the Editor). Follows
  from the capture-model decision.
- **Reuse the Editor contract & visuals** (`{outcome:1|2, debug:[[{message,data,style}]]}`, outcome
  pill + numbered colour-grouped timeline) so the two apps stay consistent.
- **`query_mirror` → synthesize a small trace.** It has no native step trace (pure equality,
  `misp/inject_eval.py:18-19`); emit a minimal group (e.g. a `primary` "Comparing query result
  against expected" step + a `success`/`fail` step carrying expected vs. actual `data`) so its
  outcome renders in the Debug view like every other strategy.
- **Evaluation data → memory-only, `backup.json` untouched.** Buffer A and completion `provenance`
  live only in memory; nothing eval-related is persisted to disk (provenance is stripped from the
  backup). Not worth persisting — after a restart it's simply absent.

## Open questions / risks

- **Debounce.** `check_active_tasks_debounced` (2s per user, `exercise.py:353`) means some actions
  aren't evaluated — so the very action a user asks about may have no attempt. Options: leave as-is
  (attempts reflect evaluated actions only, documented), or record a lightweight "skipped
  (debounced)" marker. Lean: leave as-is for Phase 1; reconsider if it confuses in practice.
- **Payload size.** MISP events can be large. Truncate `trigger.payload` and per-step `data` dumps
  (the Editor caps dumps at 15000 chars) and rely on buffer A's cap. Confirm a sensible truncation.
- **Timed injects.** `check_inject_for_timed_inject` (`exercise.py:407-471`) is a separate path with
  no incoming feed action — attribute its provenance to the timed trigger, not a `notification_id`.

## Implementation phases

### Summary table

| # | Phase | Layer | Effort | Risk | Status |
|---|---|---|---|---|---|
| 0 | Design proposal & validation (mockup) | Design | Small | — | ✅ Done (05f7887) |
| 1 | Contract + mock (synthetic attempts, provenance, outcomes) | Mock/backend | Medium | Med | ✅ Done (7d67420) |
| 2 | `EvaluationDebug.vue` — shared outcome+debug renderer | Frontend | Medium | Low | ✅ Done (a42ec9b) |
| 3 | Live Feed completion pip | Frontend | Small | Low | ✅ Done (e8515f5) |
| 4 | Drawer — completed-task provenance + View evaluation | Frontend | Medium | Low | ✅ Done (cfc340b) |
| 5 | Drawer — event-history outcomes (badges + expand + Debug) | Frontend | Medium | Med | ☐ |
| 6 | Real backend capture (MISP + webhook) | Backend | Large | Med | ☐ |

Phase 0 gates the rest. Phases 1–5 build and ship against the **mock**, so the whole UI is
demoable before the live engine is touched; the contract is frozen in Phase 1 (kept faithful to the
real backend's known constraints). Phase 6 is the only phase that touches the evaluation path.

---

### Phase 0 — Design proposal & validation

**Status: ✅ Done — 05f7887.** Signed off 2026-07-07. Mockup
`docs/mockups/inject-eval-provenance.html` renders all four surfaces + the EvaluationDebug traces
(passing/failing `data_filtering`, `python`, synthesized `query_mirror`). Feedback applied: dropped the
feed pip's first-blood flag; added size-aware handling for large data dumps — every dump carries a
size/shape header, small values show in full, and anything over a configurable cap is stored as a
**bounded preview at capture time** (so the per-user buffer never holds multi-MB events). Phases 1–6
build against it.

**Gate for everything that follows.** A self-contained dark-theme (`.sa-root`) mockup showing all
four surfaces at realistic density: the feed completion pip; the drawer's completed-task "cleared
by" line + View evaluation; the event-history outcome badges (both **✓ completed** and **checked N**
expanded); and the `EvaluationDebug` timeline for a passing *and* a failing `data_filtering` trace
plus a `python` trace (Status/Exit/Duration/STDOUT/STDERR). Iterate on feedback until signed off.

**Deliverable.** A validated design phases 1–6 implement against. No production code.
**Acceptance.** You sign off on the four surfaces' look, especially the Debug timeline's fidelity to
the Editor.

---

### Phase 1 — Contract + mock

**Status: ✅ Done — 7d67420.** The additive Socket.IO contract is frozen and implemented in
`dev_mock_server.py` only (no `src/`, no real backend). Delivered exactly as specified below;
verified over the socket, no UI yet.

Freeze the additive Socket.IO contract and implement it in `dev_mock_server.py` **only**, so every
UI phase can be built and verified on the mock.

**Build.** Synthetic `EvaluationAttempt`s per player (passing + failing; `data_filtering` and
`python` traces in the `{message,data,style}` shape); `provenance` on completed tasks in the progress
snapshot; `get_user_evaluations` ack; `user_evaluation_recorded` push; `notification_outcome` push
tied to mock completions; new `eval-pass/<user_id>` & `eval-fail/<user_id>` controls. Document
controls in `CLAUDE.md`. Keep shapes faithful to what Phase 6's real engine can emit.

**Acceptance.** With the mock: `get_user_evaluations` returns well-formed attempts; completing a mock
task emits `notification_outcome` and stamps `provenance`; failing controls produce inspectable
failing attempts. Verified over the socket (payload shape), no UI yet.

**As built (frozen contract).** Additions only — no existing event changed:
- **`get_user_evaluations`** ack → buffer A for a user (newest-first, capped `ATTEMPT_BUFFER_SIZE=20`),
  ungated request/ack like `get_user_events`.
- **`user_evaluation_recorded`** push `{user_id, attempt}` on every new attempt (live + controls).
- **`notification_outcome`** push `{notification_id, user_id, completed_tasks:[{uuid,name,first_completion}]}`,
  emitted **after** a completing evaluation and **only** when a task cleared (feed is completed-only).
  Ordered after the triggering `notification` so the pip merges onto an already-rendered feed row.
- **`update_progress`** completion entries gain optional `provenance`
  `{notification_id, attempt_id, trigger:{origin,time,http_method,url}, passing:[{evaluation_strategy,result_label}]}`.
- **`EvaluationAttempt`** = `{id, user_id, timestamp, target_tool:'MISP'|'webhook', trigger, completed_any, checks[]}`;
  each check `{inject_uuid, inject_name, result_label, join_type:'AND'|'OR', outcome:1|2, completed_now, evaluations[]}`;
  each evaluation `{evaluation_strategy, result_label, outcome:1|2, score_range, debug}`.
- **`debug`** is a list-of-groups of `{message,data,style}` steps (styles `primary`/`success`/`fail`/`error`/`''`),
  matching `backend/utils.py:eval_data_filtering` step-for-step; a `python` evaluation's group is the raw
  `[[{status,exit_code,stdout,stderr,duration}]]` sandbox result (no message/style — the renderer switches on
  the `python` strategy); `query_mirror` gets the synthesized "Comparing…" + match/mismatch group (expected vs. actual).
- **Large-dump handling.** Any step `data` carries an optional `data_meta`
  `{bytes, shape, count_label, truncated, note?}`; a value over `DATA_DUMP_CAP_BYTES` (16 KB) is replaced by a
  bounded **preview string** at capture time with `truncated:true` + a "truncated at capture (memory-bounded)"
  note. A failed `data_filtering` condition's extracted-data step also carries optional `expected` + `comparison`.
- **Degradation.** `PROVENANCE_DROP_RATE` (12%) of *seeded* completions are left provenance-less, exercising the
  post-restore "cleared by — (provenance not retained)" path. Live completions always stamp provenance.
- **Controls.** `POST /mock/eval-pass/<id>` (clear next task via a full evaluation → passing attempt + provenance +
  pip), `POST /mock/eval-fail/<id>[?large=1]` (failing "checked, cleared nothing" attempt; `?large=1` forces the
  over-cap dump). Documented in `CLAUDE.md`; reset controls clear buffer A + provenance.

---

### Phase 2 — `EvaluationDebug.vue`

**Status: ✅ Done — a42ec9b.** `src/components/dashboard/EvaluationDebug.vue` ships the shared,
read-only renderer of one captured check's `{outcome, debug}`, ported from the Editor's Inject Tester
(`InjectTester.vue:571-702`) into the dark theme and matching the Phase 0 mockup surface 4. Verified
against the running mock (all 7 trace kinds render faithfully; ✕/backdrop/Esc close cleanly), no UI
wiring yet.

The shared, read-only renderer of `{outcome, debug}`, ported from the Editor's Inject Tester
outcome+debug block (`InjectTester.vue:571-702`) into the dark theme: Outcome pill
(Successful/Failed); numbered colour-grouped step timeline; per-step success/fail/error pills +
message; `<pre>` data dumps (truncated); python Status/Exit/Duration/STDOUT/STDERR table. Driven by a
mock attempt via a temporary harness.

**Acceptance.** A passing and a failing trace render identically in spirit to the Editor; python
traces show the sandbox detail; long data dumps are bounded and scroll.

**As built.**
- **Props** `check` (required — one task's evaluation), `trigger` (the captured Live-Feed reference),
  `targetTool` (`'MISP'|'webhook'`); emits `close`. Renders `check.outcome` as the Outcome pill and
  flattens every `check.evaluations[].debug` (list-of-groups) into one numbered, colour-cycled
  (`--ed-1..6`) timeline; a `python` evaluation's group renders as the Status/Exit/Duration table +
  STDOUT/STDERR (empty streams show a muted "(no output)").
- **Faithful to the frozen contract:** per-step `success`/`fail`/`error` pills; backtick spans in a
  step message render monospace (jq paths); a step's `data_meta` becomes a size/shape header ("shown
  in full" vs the gold "over cap, previewed" + `▤` at-capture note); over-cap `data` (a pre-truncated
  preview string) is shown verbatim while live values are `JSON.stringify`-pretty and scroll;
  `expected`/`comparison` render as the failure footnote; `query_mirror` carries a "synthesized trace"
  hint. Shows the trace **as captured**, never re-run.
- **Overlay:** `Teleport` to `<body>` (escapes any transformed ancestor) with its own `--sa-*`/`--ed-*`
  token set; dismissed by ✕ / backdrop / Esc; locks/restores body scroll.
- **Not in the production bundle yet.** Nothing in `index.html → main.js → App → TheDahboard` imports
  it, so `dist/` is functionally unchanged (Tailwind only content-scans it for a few unused utility
  classes); `dist/` is rebuilt + committed in Phases 3-5 when the feed/drawer wire it in. Verified via
  a temporary harness that pulls real attempts from the mock over `get_user_evaluations` (harness not
  committed).

---

### Phase 3 — Live Feed completion pip

**Status: ✅ Done — e8515f5.** `notification_outcome` is consumed and merged onto the feed row by
`notification_id`; the row shows a mint `✓ Cleared: <task>` pip. Completed-only. Verified E2E on the
mock (headless Chrome/CDP): a completing action lights exactly one pip on its own row (label, task
name, tooltip, mint check circle correct); a burst renders `<task> +N` with the full list in the
tooltip; a failing "checked nothing" action adds a row with no pip.

Consume `notification_outcome`; merge onto the feed row by `notification_id`; show a small ✓ +
cleared-task name (completed-only). No pip for un-evaluated / failed actions.

**Acceptance.** On the mock, clearing a task lights the pip on the correct feed row with the right
task name; everything else stays unmarked; first-blood is distinguishable.

**As built.**
- **`socket.js`** — a `notification_outcome` listener merges `completed_tasks` onto the matching
  `state.notificationEvents` row by `id === notification_id` (best-effort: a row that has scrolled
  out of the ring simply goes unmarked). Only the **feed** is touched in this phase; the event-history
  badges (surface 3) come from the `userEvents`↔`userEvaluations` join in Phase 5, a separate source.
- **`dashboardState.js`** — the `feed` computed exposes a `cleared` `{label, title}` on a row when
  `completed_tasks` is present; a multi-task burst becomes `<first-task> +N` with the full list in
  `title`. Reactivity note: reading the (initially absent) `completed_tasks` key in the computed
  registers the dep, so the later merge triggers a recompute (Vue 3 tracks key-add).
- **`LiveFeed.vue`** — renders the `.sa-pip` chip (✓ circle + `Cleared:` + task label) when
  `e.cleared`; styles lifted verbatim from the signed-off mockup surface 1. The task label caps at
  180 px with ellipsis so a long name can't blow out the row; the full name is in the tooltip.
- **No first-blood on the pip.** The acceptance line above ("first-blood is distinguishable") predates
  the Phase 0 signoff, which **cut** first-blood from the pip (2026-07-07) — it lives on the drawer's
  completed-task rows, not the feed. The pip is a plain completed-only `Cleared: <task>` marker, per
  the mockup. `notification_outcome.completed_tasks[].first_completion` is still carried on the wire
  (a later surface may use it), just not shown on the pip.
- **dist/ rebuilt.** LiveFeed now ships the pip in the prod bundle, so `dist/` was rebuilt + committed
  with the source (this also resynced the pre-existing dist drift flagged in Phase 2).
- **Reload caveat (by design).** The pip is a live augmentation: on a full feed reload (connect /
  reconnect / reset-live-logs) `get_notifications` returns raw notifications with no `completed_tasks`,
  so historical rows carry no pip. Durable "what cleared this" lives in the drawer provenance
  (surfaces 2–3), not the feed.

---

### Phase 4 — Drawer: completed-task provenance

**Status: ✅ Done — cfc340b.** Each completed task in the drawer's TASK TIMING list shows a
"cleared by `<method> <url>` @ `<time>`" line + a **View evaluation** control that opens the passing
trace in `EvaluationDebug` (full from buffer A, else the compact recorded outcome); a completion with
no retained provenance reads "cleared by — (provenance not retained)". Verified E2E on the mock
(headless Chrome/CDP).

Read `tasks_completion[uuid].provenance`; render "cleared by `<method> <url>` @ `<time>`" on each
done task row and a **View evaluation** control opening `EvaluationDebug` for the passing attempt
(from buffer A when present; else the compact provenance).

**Acceptance.** Each completed task shows its triggering action; View evaluation opens the passing
trace; still shows the "cleared by" line when the attempt has rolled out of buffer A.

**As built.**
- **`socket.js`** — reactive `userEvaluations` (buffer A) with `loadUserEvaluations` /
  `clearUserEvaluations` seeded from the `get_user_evaluations` ack on drawer open, plus a
  `user_evaluation_recorded` listener that live-prepends new attempts **for the open drawer's player
  only** (capped at `MAX_USER_EVALUATIONS = 20`, mirroring the backend's `ATTEMPT_BUFFER_SIZE`). This
  plumbing is shared with Phase 5's `userEvents`↔`userEvaluations` join.
- **`dashboardState.js`** — done-task rows in `selectedPlayerTasks` carry
  `clearedBy {method, url, atTime, isHook}` read from the completion's durable `provenance.trigger`
  (null → the "(provenance not retained)" note, no View control). A shared `activeEvaluation` overlay
  ref + `openEvaluation` / `closeEvaluation`, and `openTaskEvaluation(taskUuid)` which resolves the
  rich captured attempt from buffer A by `provenance.attempt_id` (the full `{outcome, debug}` trace)
  or, once it has rolled out of the ring, **degrades** to a minimal passing check rebuilt from the
  compact `provenance.passing` (recorded outcome + strategies, empty debug). `openPlayer` /
  `closePlayer` load/clear buffer A and close any open overlay.
- **`PlayerDrawer.vue`** — renders the `.sa-prov` "cleared by" line (mint method chip; webhook clears
  get the app-wide **violet** `HOOK` chip, matching the event rail + Debug banner) with a
  `View evaluation` button, or the italic "(provenance not retained)" note; mounts the
  `EvaluationDebug` overlay from `activeEvaluation`. The drawer's Esc/focus handler **defers to the
  overlay while it's open** (capture-phase no-op) so one Esc closes only the overlay, a second closes
  the drawer.
- **`EvaluationDebug.vue`** — new optional `traceRetained` prop (default `true`, preserving the
  Phase 2/3 contract); when `false` the Debug section notes "full step trace no longer retained —
  showing the recorded outcome" instead of an empty timeline.
- **dist/ rebuilt** — `PlayerDrawer` (and now `EvaluationDebug`, which it imports) ship in the prod
  bundle, so `dist/` was rebuilt + committed with the source.
- **Verified E2E** on the frozen `--no-sim --seed 1` mock (headless Chrome/CDP): a user's completed
  tasks each render a cleared-by line + View, and the deterministic drop-rate completions render the
  "(provenance not retained)" note (`with_line + blank == done`); View opens the full trace (Outcome
  Successful, numbered step group, trigger method matches the row); forcing buffer-A eviction (26
  `eval-fail`) leaves the durable cleared-by line intact while View **degrades** to the recorded
  outcome + note; and Esc closes only the overlay, leaving the drawer open. **Verify caveat:**
  `/mock/reset` does **not** reseed the RNG (`random.seed` runs once at startup), so the
  provenance-drop pattern differs on each reset — the verify picks its target user from the *current*
  world and asserts invariants, not fixed counts.

---

### Phase 5 — Drawer: event-history outcomes

Join `userEvents` ↔ `userEvaluations` by `notification_id` in `dashboardState.js`. Each event row
gets **✓ completed `<task>`** or **checked N task(s)**; expanding a "checked" row lists each checked
task (pass/fail + `result` label); a **Debug** control opens `EvaluationDebug`. Un-evaluated events
carry no badge.

**Acceptance.** On the mock, completed and failed-check events are visually distinct; the expand
lists the right tasks with correct pass/fail; Debug opens the matching trace; the in-rail search
still works.

---

### Phase 6 — Real backend capture (MISP + webhook)

Make the live engine emit what the mock has been faking.

**Build.**
- Thread `debug=True` through `inject_checker_router` for MISP + webhook, collecting
  `(success, debug_steps)`; stop discarding the webhook trace (`webhook/exercise.py:23`); synthesize
  a trace for `query_mirror`.
- In `check_inject` / `check_active_tasks`, assemble the `EvaluationAttempt` (all available tasks
  checked on the action, each with its trace) and push it into `db.USER_EVALUATION_ATTEMPTS[user_id]`
  (bounded); emit `user_evaluation_recorded`.
- Thread the triggering `notification` (id + compact trigger) from `handleMessage` / `handleWebhook`
  into the eval call; on `mark_task_completed`, attach compact `provenance` (B); emit
  `notification_outcome` after a completing evaluation.
- Handle the timed-inject path's provenance; truncate payloads/data dumps; keep all eval data
  (buffer A + `provenance`) in memory only and strip `provenance` from `backup.json` on write.

**Acceptance.** Replaying a recorded ZMQ session (`main.py --zmq_log_file …`) and posting webhooks:
completions carry correct provenance; buffer A holds the last X attempts per user with faithful
pass/fail traces; the four UI surfaces work against the **real** backend exactly as they did on the
mock; no regression to scoring, the feed, or the leaderboard; `debug=True` triggers no extra MISP or
sandbox calls beyond the normal path.
