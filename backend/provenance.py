#!/usr/bin/env python3
"""Inject-evaluation provenance & debugging — capture side.

Captures the evaluation engine's `(success, debug_steps)` trace (produced when a
check runs with `debug=True`, see `backend/utils.py`) and turns each check into the
`EvaluationAttempt` contract the dashboard reads (`get_user_evaluations` /
`user_evaluation_recorded` / completion `provenance` / `notification_outcome`).

Provides the attempt/check/evaluation/trigger/provenance record builders, the
per-user attempt-buffer read/write, the data-dump bounding, and the synthesized
`query_mirror` trace. Data dumps are bounded at capture time so a per-user buffer
of 20 attempts can never hold multi-megabyte MISP events, and each completion
carries a compact, session-durable clear-origin (`provenance`) that survives the
buffer rolling over.

    EvaluationAttempt = {id, user_id, timestamp, target_tool:'MISP'|'webhook',
        trigger:{notification_id, origin, time, http_method, url, target_tool, payload},
        completed_any, checks:[{
            inject_uuid, inject_name, result_label, join_type:'AND'|'OR',
            outcome:1|2, completed_now, evaluations:[{
                evaluation_strategy, result_label, outcome:1|2, score_range, debug}]}]}

`debug` is a list-of-groups of {message,data,style} steps — except a `python`
evaluation's group is the raw [[{status,exit_code,stdout,stderr,duration}]] the
sandbox returns (no message/style — the renderer switches on the `python`
strategy). All eval data is ephemeral: the attempt buffer lives only in `db`, and
completion `provenance` is stripped before `backup.json` is written (see
`backend/exercise.py`).
"""

import json
import time

import backend.db as db


# Outcome codes for an evaluation result, matching the dashboard's EvaluationDebug.vue.
INJECT_EVAL_SUCCESS = 1
INJECT_EVAL_FAIL = 2

# A step's extracted `data` (or a python group's stdout/stderr) serializing to more
# than this is bounded to a preview *at capture time* — the buffer never retains
# the full value.
DATA_DUMP_CAP_BYTES = 16384

# Monotonic id for attempts (the drawer joins events → attempts on
# trigger.notification_id; the attempt's own id keys the "View evaluation" lookup).
_ATTEMPT_COUNTER = 0


def _next_attempt_id() -> int:
    global _ATTEMPT_COUNTER
    _ATTEMPT_COUNTER += 1
    return _ATTEMPT_COUNTER


# ---------------------------------------------------------------------------
# Data-dump bounding (memory-bounded capture)
# ---------------------------------------------------------------------------

def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size / 1024:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _shape_and_count(value):
    if isinstance(value, bool):
        return "boolean", "boolean"
    if isinstance(value, list):
        return "array", f"{len(value)} item{'' if len(value) == 1 else 's'}"
    if isinstance(value, dict):
        return "object", f"{len(value)} key{'' if len(value) == 1 else 's'}"
    if isinstance(value, str):
        return "string", f"{len(value)} char{'' if len(value) == 1 else 's'}"
    if value is None:
        return "null", "null"
    return "number", "number"


def data_meta_for(value):
    """Return (display_value, meta) for a step's extracted `data`.

    `meta` is a size/shape header (bytes · shape · count) the Debug view annotates
    every dump with. A value serializing to more than DATA_DUMP_CAP_BYTES is
    replaced by a bounded preview *string* (already-JSON text, sliced) with
    `truncated=True` + an honest "truncated at capture" note — so nothing bigger
    than the cap is ever retained in the buffer. Small values pass through unchanged
    and the frontend pretty-prints them.
    """
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = str(value)
    nbytes = len(raw.encode("utf-8"))
    shape, count = _shape_and_count(value)
    meta = {"bytes": nbytes, "shape": shape, "count_label": count, "truncated": False}
    if nbytes > DATA_DUMP_CAP_BYTES:
        preview = raw[:DATA_DUMP_CAP_BYTES]
        meta["truncated"] = True
        meta["note"] = (
            f"showing first {DATA_DUMP_CAP_BYTES // 1024} KB of {_human_bytes(nbytes)} "
            f"· remainder truncated at capture (buffer is memory-bounded — the full "
            f"value is not retained)"
        )
        return preview, meta
    return value, meta


def _is_meaningful(value) -> bool:
    """Worth a size header + dump? Matches EvaluationDebug.hasData — a primitive or
    a non-empty object/array. The `{}` placeholder on primary/success/fail steps is
    skipped (no header, no dump)."""
    if value is None:
        return False
    if isinstance(value, (dict, list, str)):
        return len(value) > 0
    return True


def _bound_data_filtering_debug(debug_steps):
    """Walk a list-of-groups of {message,data,style} steps and bound every
    meaningful `data` dump in place on a shallow copy — the engine's own trace is
    left untouched. `data_meta` is attached only to steps that actually carry
    extracted data (the '' / 'error' / 'fail' steps)."""
    bounded_groups = []
    for group in debug_steps or []:
        bounded_steps = []
        for step in group or []:
            if isinstance(step, dict) and "data" in step and _is_meaningful(step.get("data")):
                display, meta = data_meta_for(step["data"])
                new_step = dict(step)
                new_step["data"] = display
                new_step["data_meta"] = meta
                bounded_steps.append(new_step)
            else:
                bounded_steps.append(step)
        bounded_groups.append(bounded_steps)
    return bounded_groups


def _truncate_text(text) -> str:
    if not isinstance(text, str):
        return text
    if len(text.encode("utf-8")) <= DATA_DUMP_CAP_BYTES:
        return text
    return text[:DATA_DUMP_CAP_BYTES] + "\n…[truncated at capture (memory-bounded)]"


def _bound_python_debug(debug_steps):
    """The sandbox result is [[{status,exit_code,stdout,stderr,duration}]] — no
    message/style. Keep it verbatim but bound the (potentially large) stdout/stderr
    so the buffer stays small."""
    bounded_groups = []
    for group in debug_steps or []:
        bounded_steps = []
        for step in group or []:
            if isinstance(step, dict) and ("stdout" in step or "stderr" in step):
                new_step = dict(step)
                new_step["stdout"] = _truncate_text(new_step.get("stdout", ""))
                new_step["stderr"] = _truncate_text(new_step.get("stderr", ""))
                bounded_steps.append(new_step)
            else:
                bounded_steps.append(step)
        bounded_groups.append(bounded_steps)
    return bounded_groups


# ---------------------------------------------------------------------------
# query_mirror synthesized trace
# ---------------------------------------------------------------------------

def synthesize_query_mirror_debug(expected_data, data_to_validate, success: bool):
    """query_mirror is a pure equality check with no native step trace: emit a
    minimal group — a `primary` "Comparing…" step + a success/fail step carrying
    expected vs. actual — so its outcome renders in the Debug view like every other
    strategy. EvaluationDebug flags it as synthesized."""
    payload = {"expected": expected_data, "actual": data_to_validate}
    display, meta = data_meta_for(payload)
    outcome_step = {
        "message": ("Query result matches expected" if success
                    else "Query result does not match expected"),
        "data": display,
        "data_meta": meta,
        "style": "success" if success else "fail",
    }
    return [[
        {"message": "Comparing query result against expected", "data": {}, "style": "primary"},
        outcome_step,
    ]]


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------

def build_evaluation_record(inject_evaluation: dict, success, debug_steps) -> dict:
    """One entry of a check's `evaluations[]` — the captured trace of a single
    `inject_evaluation`. Bounds large dumps at capture time (python groups keep
    their sandbox shape; everything else is the data_filtering step shape)."""
    strategy = inject_evaluation.get("evaluation_strategy", "")
    if strategy == "python":
        debug = _bound_python_debug(debug_steps)
    else:
        debug = _bound_data_filtering_debug(debug_steps)
    return {
        "evaluation_strategy": strategy,
        "result_label": inject_evaluation.get("result", ""),
        "outcome": INJECT_EVAL_SUCCESS if success else INJECT_EVAL_FAIL,
        "score_range": inject_evaluation.get("score_range", [0, 0]),
        "debug": debug,
    }


def _check_result_label(inject: dict) -> str:
    """The task-level result label surfaced on the drawer's event checklist. Uses
    the first evaluation's `result`, falling back to the inject name."""
    for inject_evaluation in inject.get("inject_evaluation", []):
        label = inject_evaluation.get("result")
        if label:
            return label
    return inject.get("name", "")


def build_check_record(inject: dict, evaluations: list, completed: bool) -> dict:
    """One per available task an action was checked against. `join_type` is
    normalised to AND/OR for display (a single-evaluation inject with no declared
    join type reads as AND — all-must-pass)."""
    join_type = inject.get("inject_evaluation_join_type")
    join_type = "OR" if join_type == "OR" else "AND"
    return {
        "inject_uuid": inject["uuid"],
        "inject_name": inject.get("name", ""),
        "result_label": _check_result_label(inject),
        "join_type": join_type,
        "outcome": INJECT_EVAL_SUCCESS if completed else INJECT_EVAL_FAIL,
        "completed_now": bool(completed),
        "evaluations": evaluations,
    }


def _truncate_payload(payload):
    """Bound the evaluated-data snapshot the attempt/feed carries. Notification
    payloads are usually small (a form/JSON dict or a "@data - N byte(s)" string);
    this only bites a pathologically large string."""
    if isinstance(payload, str) and len(payload.encode("utf-8")) > DATA_DUMP_CAP_BYTES:
        return payload[:DATA_DUMP_CAP_BYTES] + "…"
    return payload


def build_trigger(notification) -> dict:
    """The compact Live-Feed reference an attempt/provenance carries — links the
    attempt to the feed row it came from. Webhooks have no url/method, so the row
    (and the Debug banner) shows HOOK <target_tool>. Degrades gracefully when no
    notification was built for the action (e.g. a non-http-request audit event)."""
    if not notification:
        return {"notification_id": None, "origin": None, "time": None,
                "http_method": None, "url": None, "target_tool": None, "payload": None}
    is_webhook = notification.get("notification_origin") == "webhook"
    target_tool = notification.get("target_tool")
    return {
        "notification_id": notification.get("id"),
        "origin": notification.get("notification_origin"),
        "time": notification.get("time"),
        "http_method": "HOOK" if is_webhook else notification.get("http_method"),
        "url": (target_tool or "webhook") if is_webhook else notification.get("url"),
        "target_tool": target_tool,
        "payload": _truncate_payload(notification.get("payload")),
    }


def build_timed_trigger(context: dict) -> dict:
    """A timed inject has no incoming feed action: attribute it to the timed
    trigger, not a notification_id."""
    return {
        "notification_id": None,
        "origin": "timed",
        "time": time.strftime("%H:%M:%S"),
        "http_method": "TIMED",
        "url": (context or {}).get("evaluation_trigger", "timed inject"),
        "target_tool": None,
        "payload": None,
    }


def build_attempt(user_id: int, trigger: dict, checks: list, target_tool=None) -> dict:
    """Assemble one EvaluationAttempt from the checks gathered on a single action."""
    if target_tool is None:
        target_tool = "webhook" if trigger.get("origin") == "webhook" else "MISP"
    return {
        "id": _next_attempt_id(),
        "user_id": user_id,
        "timestamp": time.time(),
        "target_tool": target_tool,
        "trigger": trigger,
        "completed_any": any(c.get("completed_now") for c in checks),
        "checks": checks,
    }


def record_attempt(user_id: int, attempt: dict) -> None:
    """Push into the attempt buffer (bounded ring, newest first)."""
    db.addUserEvaluationAttempt(user_id, attempt)


def build_provenance(attempt: dict, check: dict) -> dict:
    """Compact, session-durable clear-origin attached to a completion entry.
    Survives the attempt buffer rolling over — the full trace stays in the buffer
    only while retained; this keeps the drawer's "cleared by" line working after."""
    trigger = attempt.get("trigger", {})
    return {
        "notification_id": trigger.get("notification_id"),
        "attempt_id": attempt.get("id"),
        "trigger": {
            "origin": trigger.get("origin"),
            "time": trigger.get("time"),
            "http_method": trigger.get("http_method"),
            "url": trigger.get("url"),
        },
        "passing": [
            {"evaluation_strategy": e["evaluation_strategy"], "result_label": e["result_label"]}
            for e in check.get("evaluations", [])
            if e.get("outcome") == INJECT_EVAL_SUCCESS
        ],
    }


def strip_provenance(entry: dict) -> dict:
    """A shallow copy of a completion entry without the ephemeral `provenance` key —
    used when serialising EXERCISES_STATUS to backup.json (all eval data is
    memory-only)."""
    return {k: v for k, v in entry.items() if k != "provenance"}


# ---------------------------------------------------------------------------
# Read side (Socket.IO ack)
# ---------------------------------------------------------------------------

def get_user_evaluations(user_id: int) -> list:
    """The attempt buffer for a user (newest first) — seeds the drawer's evaluation
    view. Ungated read ack, like get_user_events and the other read acks."""
    buffer = db.USER_EVALUATION_ATTEMPTS.get(user_id)
    return list(buffer) if buffer is not None else []
