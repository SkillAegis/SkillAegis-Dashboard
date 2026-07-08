#!/usr/bin/env python3
"""Standalone mock Socket.IO server for developing the SkillAegis dashboard.

Serves synthetic, *animated* exercise data on :4001 using the exact same
event / ack contract as ``backend/server.py`` — no MISP, Docker, scenarios or
ZeroMQ required. Point the Vite dev server at it: ``npm run dev`` already talks
to ``http://localhost:4001``, so just run this instead of ``backend/main.py``.

    python3 backend/dev_mock_server.py [--host H] [--port P]
                                       [--players N] [--unauth] [--tick SEC]
                                       [--no-sim] [--seed N]

On-demand scenario controls — POST to these (no admin panel needed) to force
headline states for inspection or screenshots:
  * ``/mock/pause`` · ``/mock/resume`` — freeze / unfreeze the simulation
    (``--no-sim`` starts paused); the board stays served, just stops moving,
  * ``/mock/clear`` — every player clears every selected task (full board),
  * ``/mock/clear/<user_id>`` — one player clears (drives the all-clear burst),
  * ``/mock/checking/<user_id>`` — fire a "being validated" pulse on that
    player's next available task (drives the per-task spinner),
  * ``/mock/eval-pass/<user_id>`` — clear that player's next available task via a
    full evaluation (inspectable passing attempt + provenance + feed pip),
  * ``/mock/eval-fail/<user_id>`` — record a failing "checked, cleared nothing"
    attempt on that player's next available task(s); ``?large=1`` forces the
    over-cap bounded-preview data dump,
  * ``/mock/empty`` — wipe all progress to a fresh board,
  * ``/mock/reset`` — rebuild the synthetic world from scratch,
  * ``/mock/zmq-stale`` · ``/mock/zmq-fresh`` — freeze / resume the reported ZMQ
    time (drives the Live Feed freshness light amber "NO LIVE DATA"; stopping
    the server drops the socket → red "OFFLINE").

What it drives, on a timer, so the board is alive the moment you load it:
  * a full board of N players with scores ticking up and rows re-sorting
    (auto-pagination + leaderboard animations),
  * players clearing every task — the fused clear bar, the admin hover-reveal,
    the "Just Cleared" strip and the Finishers champion scene,
  * a Live Feed of small / large / nested-object / raw-string JSON payloads
    (exercises the 2.5 expand-collapse toggle),
  * the gamification states: on-fire streaks, speed-runner index, trophies,
    hall-of-fame podium and the per-player activity heatmaps,
  * a second selected exercise with a prerequisite chain — drives the header's
    scenario switcher and the leaderboard's locked-task squares.

Auth: starts authenticated (so you can test the admin-only behaviours) unless
``--unauth`` is given. Log in / out from the admin panel toggles it live; any
credentials are accepted.
"""

import argparse
import copy
import json
import random
import re
import time

import socketio
from aiohttp import web

# ----------------------------------------------------------------------------
# Synthetic world
# ----------------------------------------------------------------------------
ORGS = ["circl.lu", "cert.europa.eu", "ncsc.nl", "enisa.test", "cyber.gov"]
TASK_NAMES = [
    "Create the event", "Add the domain attribute", "Tag as TLP:AMBER",
    "Add the IP-src attribute", "Create the threat-actor galaxy",
    "Publish the event", "Add a sighting", "Propose an attribute edit",
    "Add the file hash", "Enrich via module",
]
ACTIVITY_BUFFER = 32          # heat bars per player
HISTORY_BUFFER = 120          # 5s buckets in the feed timeline (~10 min shown)
PER_USER_HISTORY = 50         # per-player event ring for the drill-down drawer
                              # (deeper than the 30-event global feed)

# --- Inject-evaluation provenance (PRD-inject-eval-provenance) ----------------
# The dashboard's "why did / didn't this count?" store. The real backend's eval
# engine already produces a {message,data,style} debug trace (backend/utils.py);
# the mock synthesizes the same shape so the whole UI can be built against it.
ATTEMPT_BUFFER_SIZE = 20      # buffer A: last-X evaluation attempts kept per user
                              # (ephemeral, mirrors db.USER_EVALUATION_ATTEMPTS)
DATA_DUMP_CAP_BYTES = 16384   # a step's `data` over this is stored as a bounded
                              # preview *at capture time* (never the full MB)
PROVENANCE_DROP_RATE = 0.12   # fraction of *seeded* completions deliberately left
                              # without provenance, to exercise the post-restore
                              # "cleared by — (provenance not retained)" path
INJECT_EVAL_SUCCESS = 1       # outcome codes — verbatim from the Editor's contract
INJECT_EVAL_FAIL = 2          # (SkillAegis-Editor InjectTester: OUTCOME_SUCCESS/FAILED)

_DEV_ORIGIN_RE = re.compile(r"^http://(localhost|127\.0\.0\.1):\d+$")


def is_dev_origin(origin, *_):
    """True for any http://localhost:<port> / http://127.0.0.1:<port> origin.

    Dev-only: lets the dashboard connect whatever port Vite lands on (it
    auto-increments off :5173 when that's taken). Accepted by engineio's
    ``cors_allowed_origins`` as a callable and reused by the HTTP middleware.
    """
    return bool(origin) and bool(_DEV_ORIGIN_RE.match(origin))


sio = socketio.AsyncServer(
    async_mode="aiohttp",
    cors_allowed_origins=is_dev_origin,
)

STATE = {
    "authenticated": True,
    "paused": False,
    "players": 20,
    "exercises": [],          # public exercise dicts (get_exercises shape)
    "selected": [],           # selected exercise uuids
    "users": [],              # [{user_id, email}]
    "done": {},               # done[uid][ex_uuid] = {task_index: timestamp_sec}
    "fire": {},               # fire[uid] = {start, until}  (epoch sec)
    "activity": {},           # activity[uid] = [int,...] length ACTIVITY_BUFFER
    "history": [0] * HISTORY_BUFFER,
    "notifications": [],       # newest first
    "user_notifications": {},  # user_id -> [notif,...] newest first (drawer history)
    "notif_id": 0,
    "evaluations": {},         # buffer A: user_id -> [EvaluationAttempt,...] newest first,
                               # capped at ATTEMPT_BUFFER_SIZE (get_user_evaluations)
    "provenance": {},          # provenance[uid][ex_uuid][task_index] = compact clear-origin
                               # dict; session-durable (survives buffer A rolling over)
    "task_actions": {},        # task_uuid -> synthetic {action, evaluations} template
    "eval_id": 0,
    "verbose": False,          # feed filter: show all traffic (toggle_verbose_mode)
    "apiquery": False,         # feed filter: API requests only (toggle_apiquery_mode)
    "zmq_frozen_at": None,     # if set, keep_alive reports this frozen epoch sec
                               # (drives the client's amber "no live data" light)
}


def _zmq_last_time():
    """Epoch seconds reported in `keep_alive.zmq_last_time`. Normally wall-clock
    (fresh data every emit → client light stays LIVE); /mock/zmq-stale freezes it
    at a past moment so the age crosses the client's staleness threshold → amber,
    and /mock/zmq-fresh resumes live tracking."""
    frozen = STATE["zmq_frozen_at"]
    return frozen if frozen is not None else int(time.time())


def _uuid(prefix, n):
    # Deterministic, readable pseudo-uuids — no real randomness needed.
    return f"{prefix}-{n:04d}-0000-0000-000000000000"


def build_world(n_players):
    tasks_a = [
        {"name": TASK_NAMES[i], "uuid": _uuid("taskA", i), "description": TASK_NAMES[i],
         "score": 10 + 5 * i, "requirements": {}}
        for i in range(8)
    ]
    # Linear prerequisite chain: each task needs the previous one, so the
    # leaderboard renders locked (dim, non-blink) squares. tasks_a stays
    # chain-free, keeping the default-shown exercise simple.
    tasks_b = [
        {"name": TASK_NAMES[i], "uuid": _uuid("taskB", i), "description": TASK_NAMES[i],
         "score": 20,
         "requirements": {"inject_uuid": _uuid("taskB", i - 1)} if i else {}}
        for i in range(5)
    ]
    STATE["exercises"] = [
        {"name": "MISP Triage Drill", "uuid": _uuid("exer", 1),
         "description": "Investigate and enrich an incoming event.",
         "level": "beginner", "priority": 10, "gamification": True, "tasks": tasks_a},
        {"name": "Threat-Actor Attribution", "uuid": _uuid("exer", 2),
         "description": "Attribute the campaign and publish.",
         "level": "advanced", "priority": 20, "gamification": True, "tasks": tasks_b},
    ]
    # Both selected by default so the header's scenario switcher is visible.
    STATE["selected"] = [ex["uuid"] for ex in STATE["exercises"]]
    _resolve_task_actions()   # bind each task to its synthetic action/eval template

    STATE["users"] = [
        {"user_id": i, "email": f"agent{i:02d}@{ORGS[i % len(ORGS)]}"}
        for i in range(1, n_players + 1)
    ]
    STATE["done"] = {u["user_id"]: {ex["uuid"]: {} for ex in STATE["exercises"]}
                     for u in STATE["users"]}
    STATE["fire"] = {u["user_id"]: None for u in STATE["users"]}
    STATE["activity"] = {u["user_id"]: [0] * ACTIVITY_BUFFER for u in STATE["users"]}
    STATE["user_notifications"] = {u["user_id"]: [] for u in STATE["users"]}
    STATE["evaluations"] = {u["user_id"]: [] for u in STATE["users"]}
    STATE["provenance"] = {u["user_id"]: {ex["uuid"]: {} for ex in STATE["exercises"]}
                           for u in STATE["users"]}
    STATE["eval_id"] = 0

    # Seed a believable mid-session board: most players partway, a couple already
    # cleared (so the clear bar / Just Cleared / Finishers show on first paint).
    now = time.time()
    ex0 = STATE["exercises"][0]
    n_tasks0 = len(ex0["tasks"])
    for idx, u in enumerate(STATE["users"]):
        uid = u["user_id"]
        if idx < 2:
            count = n_tasks0                       # two finishers
        else:
            count = random.randint(0, n_tasks0 - 2)
        for ti in range(count):
            STATE["done"][uid][ex0["uuid"]][ti] = now - random.uniform(30, 600)
        if count and random.random() < 0.4:
            _ignite(uid, now - random.uniform(0, 40))
        STATE["activity"][uid] = [
            random.randint(0, 3) if random.random() < 0.5 else 0
            for _ in range(ACTIVITY_BUFFER)
        ]

    # Seed a few feed rows + recent history so the Live Feed and activity
    # timeline aren't empty on first paint (the sim loop then keeps them moving).
    STATE["notifications"] = []
    STATE["notif_id"] = 0
    seeded = 0
    while seeded < 8 and STATE["notif_id"] < 60:
        notif = _make_notification(random.choice(STATE["users"]))
        if _accept(notif):
            STATE["notifications"].insert(0, notif)
            _record_user_notification(notif)
            seeded += 1
    STATE["history"] = [0] * HISTORY_BUFFER
    for i in range(len(STATE["history"]) - 24, len(STATE["history"])):
        STATE["history"][i] = random.randint(0, 4)

    # Seed the chained second exercise last, so the first exercise's seed
    # sequence above is unchanged. A spread of in-order progress renders the
    # done / available / locked squares at once; the two ex0 finishers clear it
    # too, so a full clean run still spans both selected exercises (a player at
    # the combined max keeps the Speed Index at 10.0 despite the larger ceiling).
    ex1 = STATE["exercises"][1]
    n_tasks1 = len(ex1["tasks"])
    for idx, u in enumerate(STATE["users"]):
        uid = u["user_id"]
        count1 = n_tasks1 if idx < 2 else random.randint(0, n_tasks1)
        for ti in range(count1):
            STATE["done"][uid][ex1["uuid"]][ti] = now - random.uniform(30, 600)

    # Seed a deeper per-user event history last (after the board above, so its
    # reproducible seed sequence is unchanged) — so the drill-down drawer's
    # events rail is populated the moment it opens, and clearly runs past the
    # 30-event global feed. The sim loop then live-appends on top.
    for u in STATE["users"]:
        made, attempts = 0, 0
        target = random.randint(24, 44)
        while made < target and attempts < 150:
            attempts += 1
            notif = _make_notification(u)
            if _accept(notif):
                _record_user_notification(notif)
                made += 1

    # Seed the evaluation history last (again after the board, keeping its seed
    # sequence unchanged): per-user attempt buffers, completion provenance, and a
    # guaranteed over-cap dump so every Debug-view state has data on first load.
    for u in STATE["users"]:
        _seed_user_evaluations(u)
    _seed_large_dump_attempt(STATE["users"][0], STATE["exercises"][0])

    # Surface one completion pip on the Live Feed at first paint (see the helper —
    # the pip is otherwise live-only, invisible until a completion fires). Last, so
    # the reproducible seed sequence above and buffer A stay byte-identical.
    _seed_feed_completion_pip()


def _ignite(uid, last_completion):
    STATE["fire"][uid] = {"start": last_completion - 30, "until": last_completion + 100}


def _clear_user(uid, now=None):
    # Mark every task of every selected exercise done; keep already-completed
    # timestamps so the player's *last* task lands now (drives the all-clear burst).
    now = now if now is not None else time.time()
    for ex in STATE["exercises"]:
        if ex["uuid"] in STATE["selected"]:
            done = STATE["done"][uid][ex["uuid"]]
            for ti in range(len(ex["tasks"])):
                done.setdefault(ti, now)
    _ignite(uid, now)


# ----------------------------------------------------------------------------
# Payload builders — these mirror backend/server.py + exercise.py + leaderboard.py
# ----------------------------------------------------------------------------
def _public_exercises():
    return sorted(STATE["exercises"], key=lambda e: e["priority"])


def _task_by_index(ex):
    return ex["tasks"]


def _user_score(uid, ex):
    done = STATE["done"][uid][ex["uuid"]]
    return sum(ex["tasks"][ti]["score"] for ti in done)


def _max_score(ex):
    return sum(t["score"] for t in ex["tasks"])


def _is_on_fire(uid, now):
    f = STATE["fire"].get(uid)
    return bool(f and f["until"] > now)


def build_stats(now):
    selected = [e for e in STATE["exercises"] if e["uuid"] in STATE["selected"]]
    total_max = sum(_max_score(e) for e in selected) or 1
    total_tasks = sum(len(e["tasks"]) for e in selected) or 1
    fire_window = 240

    rows = []
    for u in STATE["users"]:
        uid, email = u["user_id"], u["email"]
        score = sum(_user_score(uid, e) for e in selected)
        done_ct = sum(len(STATE["done"][uid][e["uuid"]]) for e in selected)
        rows.append({"user_id": uid, "email": email, "score": score, "done": done_ct})

    scored = [r for r in rows if r["score"] > 0]

    hall_of_fame = [
        {"user_id": r["user_id"], "email": r["email"], "score": r["score"]}
        for r in sorted(scored, key=lambda r: -r["score"])[:9]
    ]
    speed_runner = [
        {"user_id": r["user_id"], "email": r["email"], "speedrunner_score": r["score"]}
        for r in sorted(scored, key=lambda r: -r["score"])[:9]
    ]
    time_on_fire = [
        {"user_id": r["user_id"], "email": r["email"],
         "time_on_fire": round(r["done"] * fire_window * 0.9),
         "time_on_fire_interval": [int(now - 120), int(now + 60)]}
        for r in sorted(rows, key=lambda r: -r["done"]) if r["done"] > 0
    ][:9]

    top = [r["user_id"] for r in sorted(scored, key=lambda r: -r["score"])]
    trophies = _build_trophies(top)

    return {
        "hall_of_fame": hall_of_fame,
        "time_on_fire": time_on_fire,
        "speed_runner": speed_runner,
        "trophies": trophies,
        "settings": {
            "time_on_fire_window_sec": fire_window,
            # full clean run (score == total max) maps the Speed Index to 10.0
            "speedrunner_score_ceiling": total_max,
        },
    }


def _build_trophies(top_user_ids):
    def winners(ids):
        emap = {u["user_id"]: u["email"] for u in STATE["users"]}
        return [{"user_id": i, "email": emap[i]} for i in ids if i in emap]

    return {
        "grinder": {"metadata": {"id": "grinder", "name": "The Grinder"},
                    "users": winners(top_user_ids[:1])},
        "bounce-back": {"metadata": {"id": "bounce-back", "name": "Bounce Back"},
                        "users": winners(top_user_ids[1:3])},
        "messenger": {"metadata": {"id": "messenger", "name": "Messenger"},
                      "users": winners(top_user_ids[3:4])},
        "spammer": {"metadata": {"id": "spammer", "name": "Spammer"},
                    "users": winners(top_user_ids[4:6])},
    }


def build_progress():
    now = time.time()
    stats = build_stats(now)
    hof = {e["user_id"] for e in stats["hall_of_fame"]}
    speed = {e["user_id"] for e in stats["speed_runner"]}
    fire_lb = {e["user_id"] for e in stats["time_on_fire"]}
    # trophy metadata held, per user
    held = {}
    for t in stats["trophies"].values():
        for w in t["users"]:
            held.setdefault(w["user_id"], []).append(t["metadata"])

    selected = [e for e in STATE["exercises"] if e["uuid"] in STATE["selected"]]

    # Earliest completer per (exercise, task index) — mirrors
    # exercise.py::mark_task_completed's first_completion bookkeeping so the
    # dashboard's first-blood badge lights up on the true earliest clearer.
    first_by_task = {}
    for ex in selected:
        for ti in range(len(ex["tasks"])):
            best_uid, best_ts = None, None
            for u in STATE["users"]:
                done = STATE["done"][u["user_id"]][ex["uuid"]]
                if ti in done and (best_ts is None or done[ti] < best_ts):
                    best_ts, best_uid = done[ti], u["user_id"]
            if best_uid is not None:
                first_by_task[(ex["uuid"], ti)] = best_uid

    progress = {}
    for u in STATE["users"]:
        uid, email = u["user_id"], u["email"]
        exercises = {}
        for ex in selected:
            done = STATE["done"][uid][ex["uuid"]]
            tc = {}
            for ti, task in enumerate(ex["tasks"]):
                if ti in done:
                    entry = {"user_id": uid, "timestamp": done[ti],
                             "first_completion": first_by_task.get((ex["uuid"], ti)) == uid}
                    # Completion provenance (data model B) rides the existing
                    # snapshot — no new event needed for the drawer's "cleared by".
                    prov = STATE["provenance"].get(uid, {}).get(ex["uuid"], {}).get(ti)
                    if prov is not None:
                        entry["provenance"] = prov
                    tc[task["uuid"]] = entry
                else:
                    tc[task["uuid"]] = False
            exercises[ex["uuid"]] = {
                "tasks_completion": tc,
                "score": _user_score(uid, ex),
                "max_score": _max_score(ex),
            }
        f = STATE["fire"].get(uid)
        on_fire = _is_on_fire(uid, now)
        progress[uid] = {
            "email": email,
            "user_id": uid,
            "exercises": exercises,
            "status": {
                "is_on_fire": on_fire,
                "on_fire_last_interval": [f["start"], f["until"]] if on_fire else None,
                "is_on_fire_leaderboard": uid in fire_lb,
                "is_on_all_house_fame": uid in hof,
                "is_speed_runner": uid in speed,
                "trophies": held.get(uid, []),
            },
        }
    return progress, stats


# --- Live feed notification payloads (varied, to exercise the 2.5 toggle) ----
_PAYLOAD_SHAPES = ["small", "large", "nested", "raw", "webhook"]
_URLS = ["/events/index", "/attributes/add", "/events/view/42", "/tags/attachTag",
         "/objects/add/42", "/events/publish/42", "/sightings/add"]
_METHODS = ["GET", "POST", "PUT", "DELETE"]


def _make_notification(user):
    STATE["notif_id"] += 1
    nid = STATE["notif_id"]
    shape = random.choice(_PAYLOAD_SHAPES)
    now_s = time.strftime("%H:%M:%S")
    base = {"id": nid, "user_id": user["user_id"], "user": user["email"],
            "time": now_s, "response_code": 200, "user_agent": "PyMISP/2.4"}

    if shape == "webhook":
        return {**base, "notification_origin": "webhook", "target_tool": "suricata",
                "payload": f"@data - {random.randint(120, 4096)} byte(s), "
                           f"{random.randint(2, 14)} key(s)",
                "is_api_request": False}

    if shape == "small":
        payload = {"event_id": str(random.randint(1, 999)),
                   "org": random.choice(ORGS).split(".")[0].upper()}
    elif shape == "large":
        payload = {
            "event_id": str(random.randint(1, 999)), "category": "Network activity",
            "type": "domain", "to_ids": True, "distribution": "1",
            "comment": "suspicious lookup observed in passive DNS",
            "org": "CIRCL", "sharing_group_id": "0", "first_seen": "2026-06-01",
            "last_seen": "2026-06-29", "tag": "tlp:amber", "deleted": False,
            "value": f"malicious-{random.randint(100,999)}.example.com",
        }
    elif shape == "nested":
        payload = {"action": "add", "Event": {
            "info": "Spear-phishing campaign against energy sector",
            "threat_level_id": "2", "analysis": "1",
            "Attribute": [{"type": "domain", "value": "evil.example",
                           "category": "Network activity"},
                          {"type": "ip-src", "value": "203.0.113.7"}]}}
    else:  # raw long string
        payload = ("Authorization=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                   "payload-truncated-for-demo-" + "x" * random.randint(40, 90))

    method = random.choice(_METHODS)
    return {**base, "notification_origin": "zmq", "url": random.choice(_URLS),
            "http_method": method, "payload": payload,
            "is_api_request": isinstance(payload, dict)}


def _accept(notif):
    """Server-side feed filter, mirroring the real backend's verbose / apiquery
    modes (see backend/notification.py:is_accepted_notification). Verbose shows
    everything; apiquery keeps only API (JSON) requests; the default hides the
    raw non-API "noise" while keeping API requests and webhook notifications."""
    if STATE["verbose"]:
        return True
    if STATE["apiquery"]:
        return bool(notif.get("is_api_request"))
    return notif.get("notification_origin") == "webhook" or bool(notif.get("is_api_request"))


def _record_user_notification(notif):
    """Append an accepted notification to its author's per-user history ring —
    mirrors backend/notification.py:record_notification, which records every
    accepted notification into a deeper per-user buffer keyed by user_id. Feeds
    the drill-down drawer's events rail (get_user_events)."""
    uid = notif.get("user_id")
    if uid is None:
        return
    buf = STATE["user_notifications"].setdefault(uid, [])
    buf.insert(0, notif)
    del buf[PER_USER_HISTORY:]


# ----------------------------------------------------------------------------
# Inject-evaluation provenance — synthetic {outcome, debug} attempts
# (PRD-inject-eval-provenance). Every helper here fabricates data in the exact
# shape the real engine emits: `debug` is a list-of-groups, each group a list of
# {message,data,style} steps (styles: primary/success/fail/error/''); a `python`
# evaluation's group is [[{status,exit_code,stdout,stderr,duration}]] verbatim
# from sandboxClient. Kept faithful so Phase 6's real backend can drop straight
# in behind the same UI.
# ----------------------------------------------------------------------------

# Per-task synthetic action + evaluation template, keyed by task name (the mock's
# TASK_NAMES). Gives each task a plausible clearing action (the Live Feed row) and
# one evaluation whose strategy dictates the debug trace kind. Resolved once per
# task-uuid into STATE["task_actions"] so a task always looks the same everywhere.
_TASK_TEMPLATES = {
    "Create the event": {
        "origin": "zmq", "http_method": "POST", "url": "/events/add",
        "result_label": "Event created", "join_type": "AND",
        "evals": [{
            "strategy": "data_filtering", "result": "Event has a populated info field",
            "paths": [".Event.info"],
            "fail": {"extract": "", "expected": ["<non-empty info>"], "comparison": "count"},
        }],
    },
    "Add the domain attribute": {
        "origin": "zmq", "http_method": "POST", "url": "/attributes/add",
        "result_label": "Domain attribute present", "join_type": "AND",
        "evals": [{
            "strategy": "data_filtering", "result": "A domain attribute was added",
            "paths": ['.Event.Attribute[] | select(.type == "domain").value'],
            "fail": {"extract": ["192.0.2.10", "198.51.100.4"],
                     "expected": ["evil.example"], "comparison": "contains"},
        }],
    },
    "Tag as TLP:AMBER": {
        "origin": "zmq", "http_method": "POST", "url": "/tags/attachTag",
        "result_label": "Event tagged tlp:amber", "join_type": "AND",
        "evals": [{
            "strategy": "data_filtering", "result": "Event carries the tlp:amber tag",
            "paths": [".Event.Tag[].name"],
            "fail": {"extract": ["tlp:white", 'misp-galaxy:sector="IT"', 'workflow:state="draft"'],
                     "expected": ["tlp:amber"], "comparison": "contains"},
        }],
    },
    "Add the IP-src attribute": {
        "origin": "zmq", "http_method": "POST", "url": "/attributes/add",
        "result_label": "IP-src attribute present", "join_type": "AND",
        "evals": [{
            "strategy": "data_filtering", "result": "An ip-src attribute was added",
            "paths": ['.Event.Attribute[] | select(.type == "ip-src").value'],
            "fail": {"extract": [], "expected": ["203.0.113.7"], "comparison": "count"},
        }],
    },
    "Create the threat-actor galaxy": {
        "origin": "zmq", "http_method": "POST", "url": "/galaxies/attachCluster/42",
        "result_label": "Threat-actor galaxy attached", "join_type": "OR",
        "evals": [{
            "strategy": "query_mirror", "result": "Threat-actor galaxy attached",
            "expected": {"response": [{"Galaxy": {"type": "threat-actor", "name": "APT29"}}]},
            "actual": {"response": []},
        }],
    },
    "Publish the event": {
        "origin": "zmq", "http_method": "POST", "url": "/events/publish/42",
        "result_label": "Event is published", "join_type": "AND",
        "evals": [{
            "strategy": "python", "result": "Event is published",
            "stdout_pass": "checking published flag…\nEvent.published == True\nreturning True",
            "stdout_fail": "checking published flag…\nEvent.published == False\nreturning False",
        }],
    },
    "Add a sighting": {
        "origin": "webhook", "webhook_tool": "sightings",
        "result_label": "Sighting recorded", "join_type": "AND",
        "evals": [{
            "strategy": "python", "result": "At least one sighting recorded",
            "stdout_pass": ("checking sightings for 3 indicators…\n"
                            "  185.99.132.4      → 2 sightings ✓\n"
                            "  evil-phish.example → 1 sighting  ✓\n"
                            "  a1b2c3…f9         → 1 sighting  ✓\n"
                            "all indicators sighted — returning True"),
            "stdout_fail": ("checking sightings for 3 indicators…\n"
                            "  185.99.132.4      → 0 sightings ✗\n"
                            "no sightings recorded yet — returning False"),
            "stderr": "/sandbox/eval.py:14: DeprecationWarning: use Sighting.list() instead of legacy fetch",
        }],
    },
    "Propose an attribute edit": {
        "origin": "zmq", "http_method": "POST", "url": "/shadow_attributes/add/42",
        "result_label": "A proposal exists on the event", "join_type": "AND",
        "evals": [{
            "strategy": "data_filtering", "result": "A shadow attribute (proposal) exists",
            "paths": [".Event.ShadowAttribute | length"],
            "fail": {"extract": 0, "expected": [">0"], "comparison": "count"},
        }],
    },
    "Add the file hash": {
        "origin": "zmq", "http_method": "POST", "url": "/objects/add/42",
        "result_label": "A file hash was added", "join_type": "AND",
        "evals": [{
            "strategy": "data_filtering", "result": "A sha256 hash was added",
            "paths": ['.Event.Object[].Attribute[] | select(.type == "sha256").value'],
            "fail": {"extract": ["not-a-valid-hash"], "expected": ["a1b2c3…7788"],
                     "comparison": "contains", "large": True},
        }],
    },
    "Enrich via module": {
        "origin": "webhook", "webhook_tool": "enrichment",
        "result_label": "Indicators enriched", "join_type": "AND",
        "evals": [{
            "strategy": "python", "result": "Enrichment module returned data",
            "stdout_pass": "enriching 3 indicators via module…\nreceived 5 related objects\nreturning True",
            "stdout_fail": "enriching 3 indicators via module…\nmodule returned no data\nreturning False",
        }],
    },
}
_DEFAULT_TEMPLATE = "Create the event"


def _resolve_task_actions():
    """Bind each task-uuid to its (deep-copied) action template, scoring each
    evaluation to the task's own points. Kept off the task dicts themselves so
    `get_exercises` stays clean."""
    STATE["task_actions"] = {}
    for ex in STATE["exercises"]:
        for task in ex["tasks"]:
            tmpl = copy.deepcopy(_TASK_TEMPLATES.get(task["name"],
                                                     _TASK_TEMPLATES[_DEFAULT_TEMPLATE]))
            for ev in tmpl["evals"]:
                ev["score"] = [0, task["score"]]
            STATE["task_actions"][task["uuid"]] = tmpl


def _task_action(ex, ti):
    return STATE["task_actions"][ex["tasks"][ti]["uuid"]]


def _available_indices(ex, done):
    """Task indices the engine would actually check on an action: incomplete and
    (for the chained exercise) not still locked behind an unmet prerequisite."""
    avail = []
    for ti, t in enumerate(ex["tasks"]):
        if ti in done:
            continue
        req = (t.get("requirements") or {}).get("inject_uuid")
        if req is not None:
            req_ti = _find_task_index(ex, req)
            if req_ti is not None and req_ti not in done:
                continue
        avail.append(ti)
    return avail


def _data_meta(value):
    """Return (display_value, meta) for a step's extracted `data`. meta carries a
    size/shape header (bytes · shape · count) so the Debug view can annotate every
    dump. A value serializing to more than DATA_DUMP_CAP_BYTES is replaced by a
    bounded preview *string* (truncated="over cap") — the mock, like Phase 6, never
    retains the full multi-MB value."""
    raw = json.dumps(value, ensure_ascii=False)
    nbytes = len(raw.encode("utf-8"))
    if isinstance(value, bool):
        shape, count = "boolean", "boolean"
    elif isinstance(value, list):
        shape, count = "array", f"{len(value)} item{'' if len(value) == 1 else 's'}"
    elif isinstance(value, dict):
        shape, count = "object", f"{len(value)} key{'' if len(value) == 1 else 's'}"
    elif isinstance(value, str):
        shape, count = "string", f"{len(value)} char{'' if len(value) == 1 else 's'}"
    elif value is None:
        shape, count = "null", "null"
    else:
        shape, count = "number", "number"
    meta = {"bytes": nbytes, "shape": shape, "count_label": count, "truncated": False}
    if nbytes > DATA_DUMP_CAP_BYTES:
        preview = raw[:DATA_DUMP_CAP_BYTES]
        meta["truncated"] = True
        meta["note"] = (f"showing first {DATA_DUMP_CAP_BYTES // 1024} KB of "
                        f"{_human_bytes(nbytes)} · remainder truncated at capture "
                        f"(buffer is memory-bounded — the full value is not retained)")
        return preview, meta
    return value, meta


def _human_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n / 1024:.1f} {unit}"
        n /= 1024


# A fabricated "multi-MB MISP event" whose byte count is reported honestly but
# whose payload is stored only as a bounded preview — exactly the shape the Debug
# view's large-dump handling renders (size/shape header + "truncated at capture").
_BIG_EVENT_PREVIEW = json.dumps({
    "Event": {
        "uuid": "6f1e2c9a-4b7d-4e02-9f1a-2c8e5b0a11c3",
        "info": "Imported incident bundle — APT phishing wave",
        "date": "2026-07-07", "threat_level_id": "2", "analysis": "1",
        "Attribute": [
            {"type": "ip-dst", "category": "Network activity", "value": "185.99.132.4", "to_ids": True},
            {"type": "domain", "category": "Network activity", "value": "evil-phish.example", "to_ids": True},
            {"type": "sha256", "category": "Payload delivery", "value": "a1b2c3d4e5f6…7788", "to_ids": True},
            {"type": "url", "category": "Network activity", "value": "http://evil-phish…", "to_ids": True},
        ],
    },
}, indent=2)


def _big_dump_meta():
    """(preview, meta) for an over-cap extract without ever building the MB of
    data. Reports a realistic large size and object shape."""
    return _BIG_EVENT_PREVIEW, {
        "bytes": 2_517_213, "shape": "object",
        "count_label": "1,284 attributes · 96 objects", "truncated": True,
        "note": "showing first 16 KB of 2.4 MB · remainder truncated at capture "
                "(buffer is memory-bounded — the full event is not retained)",
    }


def _debug_data_filtering(ev, passing, large=False):
    """List-of-groups mirroring backend/utils.py:eval_data_filtering exactly."""
    groups = []
    if passing:
        for path in ev["paths"]:
            groups.append([
                {"message": f"Testing `{path}`", "data": {}, "style": "primary"},
                {"message": "Condition satisfied", "data": {}, "style": "success"},
            ])
        return groups
    # Failing: the real engine breaks out on the first unsatisfied param, so only
    # the first group appears.
    path = ev["paths"][0]
    fail = ev.get("fail", {})
    if large or fail.get("large"):
        preview, meta = _big_dump_meta()
        return [[
            {"message": f"Testing `{path}`", "data": {}, "style": "primary"},
            {"message": "The provided path could not extract data",
             "data": preview, "data_meta": meta, "style": "error"},
        ]]
    disp, meta = _data_meta(fail.get("extract", []))
    extracted_step = {"message": "The provided path extracted the following data to validate",
                      "data": disp, "data_meta": meta, "style": ""}
    if "expected" in fail:
        extracted_step["expected"] = fail["expected"]
    if "comparison" in fail:
        extracted_step["comparison"] = fail["comparison"]
    return [[
        {"message": f"Testing `{path}`", "data": {}, "style": "primary"},
        {"message": "Condition not satisfied", "data": {}, "style": "fail"},
        extracted_step,
    ]]


def _debug_python(ev, passing):
    """[[result]] mirroring sandboxClient.run(debug=True): a single group holding
    the raw sandbox result dict (no message/style — the Debug view switches on the
    evaluation's `python` strategy to render the Status/Exit/Duration table)."""
    result = {
        "status": "success",
        "exit_code": 0,
        "duration": round(random.uniform(0.18, 0.92), 2),
        "stdout": ev["stdout_pass"] if passing else ev["stdout_fail"],
        "stderr": ev.get("stderr", ""),
    }
    return [[result]]


def _debug_query_mirror(ev, passing):
    """Synthesized trace (query_mirror is a pure equality check with no native
    trace — PRD decision): a primary "Comparing…" step + a success/fail step
    carrying expected vs. actual."""
    expected = ev["expected"]
    actual = expected if passing else ev["actual"]
    disp, meta = _data_meta({"expected": expected, "actual": actual})
    outcome_step = {
        "message": ("Query result matches expected" if passing
                    else "Query result does not match expected"),
        "data": disp, "data_meta": meta,
        "style": "success" if passing else "fail",
    }
    return [[
        {"message": "Comparing query result against expected", "data": {}, "style": "primary"},
        outcome_step,
    ]]


def _build_evaluation(ev, passing, large=False):
    strat = ev["strategy"]
    if strat == "python":
        debug = _debug_python(ev, passing)
    elif strat == "query_mirror":
        debug = _debug_query_mirror(ev, passing)
    else:
        debug = _debug_data_filtering(ev, passing, large=large)
    return {
        "evaluation_strategy": strat,
        "result_label": ev["result"],
        "outcome": INJECT_EVAL_SUCCESS if passing else INJECT_EVAL_FAIL,
        "score_range": ev.get("score", [0, 10]),
        "debug": debug,
    }


def _build_check(ex, ti, passing, large=False):
    task = ex["tasks"][ti]
    tmpl = _task_action(ex, ti)
    return {
        "inject_uuid": task["uuid"],
        "inject_name": task["name"],
        "result_label": tmpl["result_label"],
        "join_type": tmpl["join_type"],
        "outcome": INJECT_EVAL_SUCCESS if passing else INJECT_EVAL_FAIL,
        "completed_now": passing,
        "evaluations": [_build_evaluation(ev, passing, large=large) for ev in tmpl["evals"]],
    }


def _sample_action_payload(ex, ti):
    task = ex["tasks"][ti]
    return {"action": "edit", "inject": task["name"], "event_id": str(random.randint(10, 99))}


def _eval_notification(user, ex, ti, ts):
    """A Live Feed notification for the action that triggered an evaluation, in
    the real backend's notification shape (zmq: url/http_method/payload/is_api_request;
    webhook: target_tool + a "@data - N byte(s)" string, no url). Its `id` is what
    the attempt/provenance and notification_outcome all key off."""
    STATE["notif_id"] += 1
    nid = STATE["notif_id"]
    tmpl = _task_action(ex, ti)
    tstr = time.strftime("%H:%M:%S", time.localtime(ts))
    base = {"id": nid, "user_id": user["user_id"], "user": user["email"],
            "time": tstr, "response_code": 200, "user_agent": "PyMISP/2.4"}
    if tmpl["origin"] == "webhook":
        return {**base, "notification_origin": "webhook",
                "target_tool": tmpl["webhook_tool"],
                "payload": f"@data - {random.randint(400, 1600)} byte(s), "
                           f"{random.randint(4, 12)} key(s)"}
    return {**base, "notification_origin": "zmq", "url": tmpl["url"],
            "http_method": tmpl["http_method"], "payload": _sample_action_payload(ex, ti),
            "is_api_request": True}


def _trigger_from_notif(notif):
    """The compact Live-Feed reference an attempt/provenance carries. Webhooks have
    no url/method → the row (and Debug trigger line) shows HOOK <target_tool>."""
    is_web = notif.get("notification_origin") == "webhook"
    return {
        "notification_id": notif["id"],
        "origin": notif.get("notification_origin"),
        "time": notif["time"],
        "http_method": "HOOK" if is_web else notif.get("http_method"),
        "url": (notif.get("target_tool") or "webhook") if is_web else notif.get("url"),
        "target_tool": notif.get("target_tool"),
        "payload": _truncate_trigger_payload(notif.get("payload")),
    }


def _truncate_trigger_payload(payload):
    """Bound the evaluated-data snapshot the same way Phase 6 must. Mock payloads
    are tiny, so this only ever bites a pathological string."""
    if isinstance(payload, str) and len(payload.encode("utf-8")) > DATA_DUMP_CAP_BYTES:
        return payload[:DATA_DUMP_CAP_BYTES] + "…"
    return payload


def _build_attempt(user, ex, ts, notif, checked_indices, completed_indices, large=False):
    """One EvaluationAttempt: the action, plus one check per *available* task it was
    evaluated against, each check carrying its evaluations' debug traces."""
    STATE["eval_id"] += 1
    checks = [_build_check(ex, ti, ti in completed_indices, large=large)
              for ti in checked_indices]
    trig = _trigger_from_notif(notif)
    return {
        "id": STATE["eval_id"],
        "user_id": user["user_id"],
        "timestamp": ts,
        "target_tool": "webhook" if trig["origin"] == "webhook" else "MISP",
        "trigger": trig,
        "completed_any": bool(completed_indices),
        "checks": checks,
    }


def _push_attempt(uid, attempt):
    buf = STATE["evaluations"].setdefault(uid, [])
    buf.insert(0, attempt)
    del buf[ATTEMPT_BUFFER_SIZE:]


def _is_first_completion(uid, ex, ti):
    my_ts = STATE["done"][uid][ex["uuid"]].get(ti)
    if my_ts is None:
        return False
    for u in STATE["users"]:
        other = STATE["done"][u["user_id"]][ex["uuid"]].get(ti)
        if other is not None and other < my_ts:
            return False
    return True


def _set_provenance(uid, ex, ti, notif, attempt, check):
    """Attach compact, session-durable clear-origin to a completion (data model B).
    Survives buffer A rolling over; the full trace stays in A only while retained."""
    trig = attempt["trigger"]
    STATE["provenance"][uid][ex["uuid"]][ti] = {
        "notification_id": notif["id"],
        "attempt_id": attempt["id"],
        "trigger": {"origin": trig["origin"], "time": trig["time"],
                    "http_method": trig["http_method"], "url": trig["url"]},
        "passing": [{"evaluation_strategy": e["evaluation_strategy"],
                     "result_label": e["result_label"]}
                    for e in check["evaluations"] if e["outcome"] == INJECT_EVAL_SUCCESS],
    }


def _seed_user_evaluations(user):
    """Backfill a believable evaluation history: one passing attempt per completed
    task (in completion order), plus a few failing "checked, cleared nothing"
    attempts on the current available task(s). Provenance is set for (most) passes;
    buffer A keeps only the newest ATTEMPT_BUFFER_SIZE, so older completions keep
    their compact provenance but lose the full trace — the real lifecycle."""
    uid = user["user_id"]
    selected = [e for e in STATE["exercises"] if e["uuid"] in STATE["selected"]]
    events = []  # (ts, ex, checked_indices, completed_indices)
    for ex in selected:
        done = STATE["done"][uid][ex["uuid"]]
        for ti, ts in sorted(done.items(), key=lambda kv: kv[1]):
            events.append((ts, ex, [ti], [ti]))
        avail = _available_indices(ex, done)
        if avail:
            base = max(done.values()) if done else (time.time() - 300)
            for k in range(random.randint(0, 2)):
                # occasionally check two available tasks at once → "checked 2 tasks"
                checked = avail[:2] if (k == 0 and len(avail) >= 2 and random.random() < 0.5) else [avail[0]]
                events.append((base + 20 + 40 * k, ex, checked, []))
    events.sort(key=lambda e: e[0])
    for ts, ex, checked, completed in events:
        notif = _eval_notification(user, ex, (completed or checked)[0], ts)
        _record_user_notification(notif)
        attempt = _build_attempt(user, ex, ts, notif, checked, completed)
        _push_attempt(uid, attempt)
        for ti in completed:
            if random.random() < PROVENANCE_DROP_RATE:
                continue  # exercise the post-restore "provenance not retained" path
            check = next(c for c in attempt["checks"]
                         if c["inject_uuid"] == ex["tasks"][ti]["uuid"])
            _set_provenance(uid, ex, ti, notif, attempt, check)


def _seed_large_dump_attempt(user, ex):
    """Ensure one over-cap failing attempt is inspectable on first load, so the
    Debug view's bounded-preview handling has data without waiting on a control."""
    ti = next((i for i in range(len(ex["tasks"]))
               if _task_action(ex, i)["evals"][0]["strategy"] == "data_filtering"), 0)
    ts = time.time() - random.uniform(30, 120)
    notif = _eval_notification(user, ex, ti, ts)
    _record_user_notification(notif)
    attempt = _build_attempt(user, ex, ts, notif, [ti], [], large=True)
    _push_attempt(user["user_id"], attempt)


def _seed_feed_completion_pip():
    """Demo affordance: surface ONE completion pip on the Live Feed at first paint.

    Surface 1's pip is normally a *live* augmentation — `notification_outcome`
    merges `completed_tasks` onto a feed row as the completion happens, so a fresh
    load / reload shows only raw notifications and no pip (the durable record lives
    in the drawer, surfaces 2-3). That leaves surface 1 invisible until a live
    completion fires (the sim, or POST /mock/eval-pass/<id>) — unlike the drawer
    surfaces, which are already seeded to inspect on load. Seed the most recent real
    completion as a top-of-feed row already carrying `completed_tasks` so the pip is
    visible immediately.

    Called last in build_world so the reproducible seed sequence above is unchanged;
    no attempt is pushed to buffer A, so the evaluation history stays byte-identical.
    """
    selected = [e for e in STATE["exercises"] if e["uuid"] in STATE["selected"]]
    if not selected:
        return
    ex = selected[0]
    # First user with a completed task in this exercise; use their latest completion.
    for u in STATE["users"]:
        done = STATE["done"][u["user_id"]][ex["uuid"]]
        if not done:
            continue
        ti = max(done.items(), key=lambda kv: kv[1])[0]
        notif = _eval_notification(u, ex, ti, done[ti])
        notif["completed_tasks"] = [{
            "uuid": ex["tasks"][ti]["uuid"],
            "name": ex["tasks"][ti]["name"],
            "first_completion": _is_first_completion(u["user_id"], ex, ti),
        }]
        STATE["notifications"].insert(0, notif)
        _record_user_notification(notif)
        return


async def _record_live_completion(user, ex, completed_indices, now):
    """Live path: a mock action that cleared task(s). Emits the feed row FIRST (so
    the client has rendered it), then the attempt, then notification_outcome — the
    order the pip merge relies on."""
    uid = user["user_id"]
    notif = _eval_notification(user, ex, completed_indices[0], now)
    STATE["notifications"].insert(0, notif)
    del STATE["notifications"][30:]
    _record_user_notification(notif)
    await sio.emit("notification", notif)
    attempt = _build_attempt(user, ex, now, notif, list(completed_indices), list(completed_indices))
    _push_attempt(uid, attempt)
    for ti in completed_indices:
        check = next(c for c in attempt["checks"]
                     if c["inject_uuid"] == ex["tasks"][ti]["uuid"])
        _set_provenance(uid, ex, ti, notif, attempt, check)
    await sio.emit("user_evaluation_recorded", {"user_id": uid, "attempt": attempt})
    completed_tasks = [{"uuid": ex["tasks"][ti]["uuid"], "name": ex["tasks"][ti]["name"],
                        "first_completion": _is_first_completion(uid, ex, ti)}
                       for ti in completed_indices]
    await sio.emit("notification_outcome", {
        "notification_id": notif["id"], "user_id": uid, "completed_tasks": completed_tasks})


async def _record_live_failed_check(user, ex, checked_indices, now, large=False):
    """Live path: a mock action evaluated against available task(s) that cleared
    nothing. No notification_outcome (the feed is completed-only)."""
    uid = user["user_id"]
    notif = _eval_notification(user, ex, checked_indices[0], now)
    STATE["notifications"].insert(0, notif)
    del STATE["notifications"][30:]
    _record_user_notification(notif)
    await sio.emit("notification", notif)
    attempt = _build_attempt(user, ex, now, notif, list(checked_indices), [], large=large)
    _push_attempt(uid, attempt)
    await sio.emit("user_evaluation_recorded", {"user_id": uid, "attempt": attempt})
    return attempt


# ----------------------------------------------------------------------------
# Emit helpers
# ----------------------------------------------------------------------------
async def emit_all(to=None):
    progress, stats = build_progress()
    await sio.emit("update_progress", progress, to=to)
    await sio.emit("update_statistics", stats, to=to)
    await sio.emit("update_users_activity", {
        "activity": {u["user_id"]: STATE["activity"][u["user_id"]] for u in STATE["users"]},
        "config": {"timestamp_min": 16, "buffer_resolution_per_minute": 2,
                   "frequency": 5, "activity_buffer_size": ACTIVITY_BUFFER},
    }, to=to)
    await sio.emit("update_notification_history", {
        "history": list(STATE["history"]),
        "config": {"buffer_resolution_per_minute": 12, "buffer_timestamp_min": 10,
                   "frequency": 5, "notification_history_size": HISTORY_BUFFER},
    }, to=to)
    await sio.emit("keep_alive", {"zmq_last_time": _zmq_last_time()}, to=to)


# ----------------------------------------------------------------------------
# Simulation loop
# ----------------------------------------------------------------------------
async def simulate(tick):
    while True:
        await sio.sleep(tick)
        if STATE["paused"]:
            # Frozen for inspection/screenshots: keep the connection fresh but
            # don't mutate scores, feed or buffers.
            await sio.emit("keep_alive", {"zmq_last_time": _zmq_last_time()})
            continue
        now = time.time()
        ex0 = STATE["exercises"][0]
        ex0_uuid = ex0["uuid"]
        n_tasks = len(ex0["tasks"])

        movers = [u for u in STATE["users"]
                  if len(STATE["done"][u["user_id"]][ex0_uuid]) < n_tasks]
        random.shuffle(movers)

        notif_this_tick = 0
        for u in movers[:random.randint(1, 3)]:
            uid = u["user_id"]
            done = STATE["done"][uid][ex0_uuid]
            nxt = next(ti for ti in range(n_tasks) if ti not in done)
            # occasionally a player clears everything that's left in one go
            burst = list(range(nxt, n_tasks)) if random.random() < 0.15 else [nxt]
            for ti in burst:
                done[ti] = now
            _ignite(uid, now)
            STATE["activity"][uid][-1] += len(burst)
            # Emit the clearing action's feed row + evaluation attempt + provenance
            # + notification_outcome (lights the feed pip on the row just emitted).
            await _record_live_completion(u, ex0, burst, now)
            notif_this_tick += 1

        # Occasionally a player acts but clears nothing → a failing "checked N"
        # attempt (drives the drawer's failure diagnostics live). No feed pip.
        if movers and random.random() < 0.6:
            u = random.choice(movers)
            avail = _available_indices(ex0, STATE["done"][u["user_id"]][ex0_uuid])
            if avail:
                checked = avail[:2] if (len(avail) >= 2 and random.random() < 0.4) else [avail[0]]
                await _record_live_failed_check(u, ex0, checked, now)
                notif_this_tick += 1

        # "Being validated" pulses: mirror the real backend re-checking a
        # trainee's injects after they act. Fire on a few players' next
        # available task so the leaderboard's per-task spinner is alive.
        checkers = [u for u in movers]
        random.shuffle(checkers)
        for u in checkers[: random.randint(1, 3)]:
            uid = u["user_id"]
            done = STATE["done"][uid][ex0_uuid]
            nxt = next((ti for ti in range(n_tasks) if ti not in done), None)
            if nxt is not None:
                await sio.emit("user_task_check_in_progress",
                               {"user_id": uid, "inject_uuid": ex0["tasks"][nxt]["uuid"]})

        # a few feed events each tick, from active-ish users
        for _ in range(random.randint(1, 3)):
            user = random.choice(STATE["users"])
            notif = _make_notification(user)
            if not _accept(notif):
                continue
            STATE["notifications"].insert(0, notif)
            del STATE["notifications"][30:]
            _record_user_notification(notif)
            await sio.emit("notification", notif)
            notif_this_tick += 1

        # advance the activity + history ring buffers one slot
        for uid in STATE["activity"]:
            buf = STATE["activity"][uid]
            buf.pop(0)
            buf.append(0)
        STATE["history"].pop(0)
        STATE["history"].append(notif_this_tick)

        await emit_all()


# ----------------------------------------------------------------------------
# Socket.IO event handlers (ack-callback contract from socket.js)
# ----------------------------------------------------------------------------
@sio.event
async def connect(sid, environ):
    await emit_all(to=sid)          # paint immediately, don't wait for the timer


@sio.event
async def disconnect(sid):
    pass


@sio.event
async def get_exercises(sid):
    return _public_exercises()


@sio.event
async def get_selected_exercises(sid):
    return STATE["selected"]


@sio.event
async def get_progress(sid):
    progress, _ = build_progress()
    return progress


@sio.event
async def get_users_stats(sid):
    return build_stats(time.time())


@sio.event
async def get_notifications(sid):
    return list(STATE["notifications"])


@sio.event
async def get_user_events(sid, data):
    try:
        uid = int(data.get("user_id"))
    except (TypeError, ValueError):
        return []
    return list(STATE["user_notifications"].get(uid, []))


@sio.event
async def get_user_evaluations(sid, data):
    """Seed the drawer's evaluation view on open — buffer A for a user (newest
    first), mirroring get_user_events. Ungated request/ack like the other reads."""
    try:
        uid = int(data.get("user_id"))
    except (TypeError, ValueError):
        return []
    return list(STATE["evaluations"].get(uid, []))


@sio.event
async def get_users_activity(sid):
    return {
        "activity": {u["user_id"]: STATE["activity"][u["user_id"]] for u in STATE["users"]},
        "config": {"timestamp_min": 16, "buffer_resolution_per_minute": 2,
                   "frequency": 5, "activity_buffer_size": ACTIVITY_BUFFER},
    }


@sio.event
async def get_diagnostic(sid):
    return {}


@sio.event
async def check_user_authenticated(sid):
    return {"success": STATE["authenticated"], "message": ""}


def _find_task_index(ex, task_uuid):
    for ti, t in enumerate(ex["tasks"]):
        if t["uuid"] == task_uuid:
            return ti
    return None


@sio.event
async def mark_task_completed(sid, payload):
    _apply_completion(payload, complete=True)
    await emit_all()


@sio.event
async def mark_task_incomplete(sid, payload):
    _apply_completion(payload, complete=False)
    await emit_all()


def _apply_completion(payload, complete):
    uid = int(payload["user_id"])
    ex = next((e for e in STATE["exercises"] if e["uuid"] == payload["exercise_uuid"]), None)
    if ex is None or uid not in STATE["done"]:
        return
    ti = _find_task_index(ex, payload["task_uuid"])
    if ti is None:
        return
    done = STATE["done"][uid][ex["uuid"]]
    if complete:
        done[ti] = time.time()
    else:
        done.pop(ti, None)


@sio.event
async def change_exercise_selection(sid, payload):
    uuid, selected = payload["exercise_uuid"], payload["selected"]
    if selected and uuid not in STATE["selected"]:
        STATE["selected"].append(uuid)
    elif not selected and uuid in STATE["selected"]:
        STATE["selected"].remove(uuid)
    await emit_all()
    return {"success": True}


def _clear_evaluation_state():
    """Drop buffer A + completion provenance for everyone — used whenever progress
    itself is wiped, so no stale 'cleared by' lines survive a reset."""
    for uid in STATE["evaluations"]:
        STATE["evaluations"][uid] = []
    for uid in STATE["provenance"]:
        for ex_uuid in STATE["provenance"][uid]:
            STATE["provenance"][uid][ex_uuid] = {}


@sio.event
async def reset_all_exercise_progress(sid):
    for uid in STATE["done"]:
        for ex_uuid in STATE["done"][uid]:
            STATE["done"][uid][ex_uuid] = {}
        STATE["fire"][uid] = None
    _clear_evaluation_state()
    await emit_all()
    return {"success": True}


@sio.event
async def reset_all(sid):
    build_world(STATE["players"])
    await emit_all()
    return {"success": True}


@sio.event
async def reset_notifications(sid):
    STATE["notifications"].clear()
    for buf in STATE["user_notifications"].values():
        buf.clear()
    return {"success": True}


@sio.event
async def reload_from_disk(sid):
    return {"success": True}


@sio.event
async def toggle_verbose_mode(sid, payload):
    STATE["verbose"] = bool(payload.get("verbose"))
    return {"success": True}


@sio.event
async def toggle_apiquery_mode(sid, payload):
    STATE["apiquery"] = bool(payload.get("apiquery"))
    return {"success": True}


@sio.event
async def remediate_setting(sid, payload):
    return {"success": True}


@sio.on("*")
async def catch_all(event, sid, *args):
    print(f">> unhandled event: {event}")


# ----------------------------------------------------------------------------
# HTTP routes (login / logout) with dev CORS
# ----------------------------------------------------------------------------
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    origin = request.headers.get("Origin", "")
    if is_dev_origin(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return resp


async def login(request):
    STATE["authenticated"] = True
    return web.json_response({"success": True, "message": "mock login ok"})


async def logout(request):
    STATE["authenticated"] = False
    return web.json_response({"success": True})


async def index(request):
    return web.json_response({
        "mock": "SkillAegis dashboard dev server",
        "authenticated": STATE["authenticated"],
        "paused": STATE["paused"],
        "controls": ["POST /mock/pause", "POST /mock/resume", "POST /mock/clear",
                     "POST /mock/clear/<user_id>", "POST /mock/checking/<user_id>",
                     "POST /mock/eval-pass/<user_id>", "POST /mock/eval-fail/<user_id>[?large=1]",
                     "POST /mock/empty", "POST /mock/reset",
                     "POST /mock/zmq-stale", "POST /mock/zmq-fresh"],
    })


# --- On-demand scenario controls (dev-only HTTP pokes) ----------------------
async def mock_pause(request):
    STATE["paused"] = True
    return web.json_response({"success": True, "paused": True})


async def mock_resume(request):
    STATE["paused"] = False
    return web.json_response({"success": True, "paused": False})


async def mock_clear_all(request):
    for uid in STATE["done"]:
        _clear_user(uid)
    await emit_all()
    return web.json_response({"success": True, "cleared": "all"})


async def mock_clear_user(request):
    try:
        uid = int(request.match_info["user_id"])
    except ValueError:
        return web.json_response({"success": False, "error": "user_id must be an int"},
                                 status=400)
    if uid not in STATE["done"]:
        return web.json_response({"success": False, "error": f"no user {uid}"}, status=404)
    _clear_user(uid)
    await emit_all()
    return web.json_response({"success": True, "cleared": uid})


async def mock_checking_user(request):
    try:
        uid = int(request.match_info["user_id"])
    except ValueError:
        return web.json_response({"success": False, "error": "user_id must be an int"},
                                 status=400)
    if uid not in STATE["done"]:
        return web.json_response({"success": False, "error": f"no user {uid}"}, status=404)
    # Fire a check pulse on this player's next available task in each selected
    # exercise, so the "being validated" spinner can be forced for a screenshot
    # regardless of which scenario tab is showing.
    fired = []
    for ex in STATE["exercises"]:
        if ex["uuid"] not in STATE["selected"]:
            continue
        done = STATE["done"][uid][ex["uuid"]]
        nxt = next((ti for ti in range(len(ex["tasks"])) if ti not in done), None)
        if nxt is not None:
            task_uuid = ex["tasks"][nxt]["uuid"]
            await sio.emit("user_task_check_in_progress",
                           {"user_id": uid, "inject_uuid": task_uuid})
            fired.append(task_uuid)
    return web.json_response({"success": True, "checking": uid, "tasks": fired})


def _parse_user_id(request):
    """(uid, error_response) — shared parse/validate for the eval controls."""
    try:
        uid = int(request.match_info["user_id"])
    except ValueError:
        return None, web.json_response({"success": False, "error": "user_id must be an int"},
                                       status=400)
    if uid not in STATE["done"]:
        return None, web.json_response({"success": False, "error": f"no user {uid}"}, status=404)
    return uid, None


def _user_by_id(uid):
    return next(u for u in STATE["users"] if u["user_id"] == uid)


async def mock_eval_pass(request):
    """Clear this player's next available task via a full evaluation — produces an
    inspectable passing attempt, stamps provenance, and lights the feed pip."""
    uid, err = _parse_user_id(request)
    if err:
        return err
    now = time.time()
    for ex in STATE["exercises"]:
        if ex["uuid"] not in STATE["selected"]:
            continue
        avail = _available_indices(ex, STATE["done"][uid][ex["uuid"]])
        if avail:
            ti = avail[0]
            STATE["done"][uid][ex["uuid"]][ti] = now
            _ignite(uid, now)
            await _record_live_completion(_user_by_id(uid), ex, [ti], now)
            await emit_all()
            return web.json_response({"success": True, "user": uid,
                                      "completed": ex["tasks"][ti]["name"]})
    return web.json_response({"success": False, "error": "no available task to clear"},
                             status=409)


async def mock_eval_fail(request):
    """Record a failing "checked, cleared nothing" attempt on this player's next
    available task(s) — an inspectable failing trace. `?large=1` forces the
    over-cap bounded-preview dump."""
    uid, err = _parse_user_id(request)
    if err:
        return err
    large = request.query.get("large") in ("1", "true", "yes")
    now = time.time()
    for ex in STATE["exercises"]:
        if ex["uuid"] not in STATE["selected"]:
            continue
        avail = _available_indices(ex, STATE["done"][uid][ex["uuid"]])
        if avail:
            checked = avail[:2] if (len(avail) >= 2 and not large) else [avail[0]]
            attempt = await _record_live_failed_check(_user_by_id(uid), ex, checked, now, large=large)
            return web.json_response({"success": True, "user": uid, "attempt_id": attempt["id"],
                                      "checked": [ex["tasks"][t]["name"] for t in checked],
                                      "large": large})
    return web.json_response({"success": False, "error": "no available task to check"},
                             status=409)


async def mock_empty(request):
    for uid in STATE["done"]:
        for ex_uuid in STATE["done"][uid]:
            STATE["done"][uid][ex_uuid] = {}
        STATE["fire"][uid] = None
    _clear_evaluation_state()
    await emit_all()
    return web.json_response({"success": True, "board": "empty"})


async def mock_reset(request):
    build_world(STATE["players"])
    await emit_all()
    return web.json_response({"success": True, "reset": True})


async def mock_zmq_stale(request):
    # Freeze the reported ZMQ time and stop advancing it; the client's freshness
    # light ages into amber "NO LIVE DATA" within its staleness window.
    STATE["zmq_frozen_at"] = int(time.time())
    await sio.emit("keep_alive", {"zmq_last_time": STATE["zmq_frozen_at"]})
    return web.json_response({"success": True, "zmq_frozen_at": STATE["zmq_frozen_at"]})


async def mock_zmq_fresh(request):
    # Resume live ZMQ time → client light returns to mint "LIVE".
    STATE["zmq_frozen_at"] = None
    await sio.emit("keep_alive", {"zmq_last_time": _zmq_last_time()})
    return web.json_response({"success": True, "zmq": "fresh"})


async def options_handler(request):
    return web.Response(status=204)


def main():
    ap = argparse.ArgumentParser(description="SkillAegis dashboard mock server")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1; pass 0.0.0.0 to expose "
                         "on all interfaces)")
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--players", type=int, default=20)
    ap.add_argument("--tick", type=float, default=2.5, help="simulation tick seconds")
    ap.add_argument("--unauth", action="store_true", help="start logged out (viewer)")
    ap.add_argument("--no-sim", action="store_true",
                    help="start with the simulation paused (frozen board)")
    ap.add_argument("--seed", type=int, default=1,
                    help="random seed for a reproducible world (default 1)")
    args = ap.parse_args()

    STATE["players"] = args.players
    STATE["authenticated"] = not args.unauth
    STATE["paused"] = args.no_sim
    random.seed(args.seed)
    build_world(args.players)

    app = web.Application(middlewares=[cors_middleware])
    sio.attach(app)
    app.router.add_get("/", index)
    app.router.add_post("/login", login)
    app.router.add_post("/logout", logout)
    app.router.add_post("/mock/pause", mock_pause)
    app.router.add_post("/mock/resume", mock_resume)
    app.router.add_post("/mock/clear", mock_clear_all)
    app.router.add_post("/mock/clear/{user_id}", mock_clear_user)
    app.router.add_post("/mock/checking/{user_id}", mock_checking_user)
    app.router.add_post("/mock/eval-pass/{user_id}", mock_eval_pass)
    app.router.add_post("/mock/eval-fail/{user_id}", mock_eval_fail)
    app.router.add_post("/mock/empty", mock_empty)
    app.router.add_post("/mock/reset", mock_reset)
    app.router.add_post("/mock/zmq-stale", mock_zmq_stale)
    app.router.add_post("/mock/zmq-fresh", mock_zmq_fresh)
    app.router.add_route("OPTIONS", "/{tail:.*}", options_handler)

    async def _start(app):
        sio.start_background_task(simulate, args.tick)
    app.on_startup.append(_start)

    print(f"Mock dashboard server on http://{args.host}:{args.port} "
          f"({args.players} players, tick {args.tick}s, "
          f"{'admin' if STATE['authenticated'] else 'viewer'} mode"
          f"{', PAUSED' if STATE['paused'] else ''})")
    print("Point `npm run dev` (http://localhost:5173) at it — it already targets :4001.")
    print(f"Controls: curl -X POST http://localhost:{args.port}/mock/"
          "{pause,resume,clear,clear/<id>,checking/<id>,eval-pass/<id>,"
          "eval-fail/<id>,empty,reset,zmq-stale,zmq-fresh}")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
