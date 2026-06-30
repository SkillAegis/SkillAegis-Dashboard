#!/usr/bin/env python3
"""Standalone mock Socket.IO server for developing the SkillAegis dashboard.

Serves synthetic, *animated* exercise data on :4001 using the exact same
event / ack contract as ``backend/server.py`` — no MISP, Docker, scenarios or
ZeroMQ required. Point the Vite dev server at it: ``npm run dev`` already talks
to ``http://localhost:4001``, so just run this instead of ``backend/main.py``.

    python3 backend/dev_mock_server.py [--host H] [--port P]
                                       [--players N] [--unauth] [--tick SEC]

What it drives, on a timer, so the board is alive the moment you load it:
  * a full board of N players with scores ticking up and rows re-sorting
    (auto-pagination + leaderboard animations),
  * players clearing every task — the fused clear bar, the admin hover-reveal,
    the "Just Cleared" strip and the Finishers champion scene,
  * a Live Feed of small / large / nested-object / raw-string JSON payloads
    (exercises the 2.5 expand-collapse toggle),
  * the gamification states: on-fire streaks, speed-runner index, trophies,
    hall-of-fame podium and the per-player activity heatmaps.

Auth: starts authenticated (so you can test the admin-only behaviours) unless
``--unauth`` is given. Log in / out from the admin panel toggles it live; any
credentials are accepted.
"""

import argparse
import random
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

sio = socketio.AsyncServer(
    async_mode="aiohttp",
    cors_allowed_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
)

STATE = {
    "authenticated": True,
    "players": 20,
    "exercises": [],          # public exercise dicts (get_exercises shape)
    "selected": [],           # selected exercise uuids
    "users": [],              # [{user_id, email}]
    "done": {},               # done[uid][ex_uuid] = {task_index: timestamp_sec}
    "fire": {},               # fire[uid] = {start, until}  (epoch sec)
    "activity": {},           # activity[uid] = [int,...] length ACTIVITY_BUFFER
    "history": [0] * HISTORY_BUFFER,
    "notifications": [],       # newest first
    "notif_id": 0,
}


def _uuid(prefix, n):
    # Deterministic, readable pseudo-uuids — no real randomness needed.
    return f"{prefix}-{n:04d}-0000-0000-000000000000"


def build_world(n_players):
    tasks_a = [
        {"name": TASK_NAMES[i], "uuid": _uuid("taskA", i), "description": TASK_NAMES[i],
         "score": 10 + 5 * i, "requirements": {}}
        for i in range(8)
    ]
    tasks_b = [
        {"name": TASK_NAMES[i], "uuid": _uuid("taskB", i), "description": TASK_NAMES[i],
         "score": 20, "requirements": {}}
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
    STATE["selected"] = [_uuid("exer", 1)]   # exercise 0 shown; toggle #2 in admin panel

    STATE["users"] = [
        {"user_id": i, "email": f"agent{i:02d}@{ORGS[i % len(ORGS)]}"}
        for i in range(1, n_players + 1)
    ]
    STATE["done"] = {u["user_id"]: {ex["uuid"]: {} for ex in STATE["exercises"]}
                     for u in STATE["users"]}
    STATE["fire"] = {u["user_id"]: None for u in STATE["users"]}
    STATE["activity"] = {u["user_id"]: [0] * ACTIVITY_BUFFER for u in STATE["users"]}

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
    for _ in range(8):
        STATE["notifications"].insert(0, _make_notification(random.choice(STATE["users"])))
    STATE["history"] = [0] * HISTORY_BUFFER
    for i in range(len(STATE["history"]) - 24, len(STATE["history"])):
        STATE["history"][i] = random.randint(0, 4)


def _ignite(uid, last_completion):
    STATE["fire"][uid] = {"start": last_completion - 30, "until": last_completion + 100}


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
    progress = {}
    for u in STATE["users"]:
        uid, email = u["user_id"], u["email"]
        exercises = {}
        for ex in selected:
            done = STATE["done"][uid][ex["uuid"]]
            tc = {}
            for ti, task in enumerate(ex["tasks"]):
                if ti in done:
                    tc[task["uuid"]] = {"user_id": uid, "timestamp": done[ti],
                                        "first_completion": False}
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
    await sio.emit("keep_alive", {"zmq_last_time": int(time.time())}, to=to)


# ----------------------------------------------------------------------------
# Simulation loop
# ----------------------------------------------------------------------------
async def simulate(tick):
    while True:
        await sio.sleep(tick)
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
            burst = range(nxt, n_tasks) if random.random() < 0.15 else [nxt]
            for ti in burst:
                done[ti] = now
            _ignite(uid, now)
            STATE["activity"][uid][-1] += len(list(burst))

        # a few feed events each tick, from active-ish users
        for _ in range(random.randint(1, 3)):
            user = random.choice(STATE["users"])
            notif = _make_notification(user)
            STATE["notifications"].insert(0, notif)
            del STATE["notifications"][30:]
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


@sio.event
async def reset_all_exercise_progress(sid):
    for uid in STATE["done"]:
        for ex_uuid in STATE["done"][uid]:
            STATE["done"][uid][ex_uuid] = {}
        STATE["fire"][uid] = None
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
    return {"success": True}


@sio.event
async def reload_from_disk(sid):
    return {"success": True}


@sio.event
async def toggle_verbose_mode(sid, payload):
    return {"success": True}


@sio.event
async def toggle_apiquery_mode(sid, payload):
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
DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}


@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    origin = request.headers.get("Origin", "")
    if origin in DEV_ORIGINS:
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
    return web.json_response({"mock": "SkillAegis dashboard dev server",
                              "authenticated": STATE["authenticated"]})


async def options_handler(request):
    return web.Response(status=204)


def main():
    ap = argparse.ArgumentParser(description="SkillAegis dashboard mock server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--players", type=int, default=20)
    ap.add_argument("--tick", type=float, default=2.5, help="simulation tick seconds")
    ap.add_argument("--unauth", action="store_true", help="start logged out (viewer)")
    args = ap.parse_args()

    STATE["players"] = args.players
    STATE["authenticated"] = not args.unauth
    random.seed(1)
    build_world(args.players)

    app = web.Application(middlewares=[cors_middleware])
    sio.attach(app)
    app.router.add_get("/", index)
    app.router.add_post("/login", login)
    app.router.add_post("/logout", logout)
    app.router.add_route("OPTIONS", "/{tail:.*}", options_handler)

    async def _start(app):
        sio.start_background_task(simulate, args.tick)
    app.on_startup.append(_start)

    print(f"Mock dashboard server on http://{args.host}:{args.port} "
          f"({args.players} players, tick {args.tick}s, "
          f"{'admin' if STATE['authenticated'] else 'viewer'} mode)")
    print("Point `npm run dev` (http://localhost:5173) at it — it already targets :4001.")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
