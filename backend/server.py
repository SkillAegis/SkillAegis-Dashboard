#!/usr/bin/env python3

import base64
import collections
import functools
import json
import argparse
import os
import signal
import subprocess
import atexit
from pathlib import Path
import sys
import time
import traceback
import zmq
import socketio
from aiohttp import web
import zmq.asyncio
from random import getrandbits

from aiohttp_session import setup as setup_session, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.exercise as exercise_model
import backend.notification as notification_model
import backend.db as db
import backend.config as config
from backend.appConfig import logger, admin_settings
import backend.misp_api as misp_api

from backend.target_tools.misp.exercise import is_accepted_query as is_accepted_query_misp
from backend.target_tools.suricata.exercise import getInstalledSuricataVersion


WEB_DIST_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + '/../dist')

DEBUG = False
ZMQ_LOG_FILE = None
ZMQ_START_LINE_NUMBER = 0
ZMQ_MESSAGE_COUNT_LAST_TIMESPAN = 0
ZMQ_MESSAGE_COUNT = 0
ZMQ_LAST_TIME = None
USER_ACTIVITY = collections.defaultdict(int)
ALLOWED_TARGET_TOOLS = ["MISP", 'suricata', 'webhook']

# Each running timed injects will look in this list if they should be still running.
# If it's not, it will stop. (Based on inject_uuid, trigger_type and random ID)
RUNNING_TIMED_INJECTS = []


def debounce(debounce_seconds: int = 1):
    func_last_execution_time = {}
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            key = func.__name__
            if key not in func_last_execution_time:
                func_last_execution_time[key] = now
                return func(*args, **kwargs)
            elif now >= func_last_execution_time[key] + debounce_seconds:
                func_last_execution_time[key] = now
                return func(*args, **kwargs)
            else:
                return None
        return wrapper
    return decorator


def timer():
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t1 = time.time()
            res = func(*args, **kwargs)
            elapsed = time.time() - t1
            if elapsed > 0.1:
                print(elapsed)
            return res
        return wrapper
    return decorator


# Initialize ZeroMQ context and subscriber socket
context = zmq.asyncio.Context()
zsocket = context.socket(zmq.SUB)
zmq_url = config.zmq_url
zsocket.connect(zmq_url)
zsocket.setsockopt_string(zmq.SUBSCRIBE, '')

# Initialize Socket.IO server
app = web.Application()
secret_key = base64.urlsafe_b64decode(base64.urlsafe_b64encode(os.urandom(32)))
setup_session(app, EncryptedCookieStorage(secret_key))
sio = socketio.AsyncServer(cors_allowed_origins='*', async_mode='aiohttp')
sio.attach(app)


@web.middleware
async def cors_middleware(request, handler):
    ALLOWED_ORIGINS = {"http://localhost:5173"} if DEBUG else {}

    response = await handler(request)
    if DEBUG:
        origin = request.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"

    return response


# Authentication middleware and decorator
@web.middleware
async def auth_middleware(request, handler):
    session = await get_session(request)
    if request.path in (
        "/",
        "/login",
        "/webhook",
        "/favicon.ico",
        "/socket.io/",
    ) or request.path.startswith("/assets"):
        return await handler(request)

    if not session.get("user"):
        raise web.HTTPFound("/login")

    return await handler(request)

app.middlewares.append(cors_middleware)
app.middlewares.append(auth_middleware)


async def is_authenticated(sid) -> tuple:
    env = sio.get_environ(sid)
    if not env:
        return False, "No environment context"
    request = env.get("aiohttp.request")
    if not request:
        return False, "No request context"
    session = await get_session(request)
    if "user" in session:
        return True, "Authenticated"
    return False, "Unauthorized"

def require_auth(func):
    @functools.wraps(func)
    async def wrapper(sid, *args, **kwargs):
        authenticated, reason = await is_authenticated(sid)
        if authenticated is False:
            return {"error": reason}

        return await func(sid, *args, **kwargs)

    return wrapper


# Routes
async def index(request):
    with open(WEB_DIST_DIR + '/index.html') as f:
        return web.Response(text=f.read(), content_type='text/html')

async def favicon(request):
    with open(WEB_DIST_DIR + '/favicon.ico', 'rb') as f:
        return web.Response(body=f.read(), content_type='image/x-icon')

async def options_handler(request):
    return web.Response(status=204)

async def webhook(request):
    try:
        data = await request.json()
        response = await handleWebhook(data)
        if response is None:
            response = {}
    except json.decoder.JSONDecodeError as e:
        response = {"error": f"JSON Decode Error: {e}"}
        return web.Response(text=f"JSON Decode Error: {e}", status=400)
    return web.json_response(response)

async def login(request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    if (
        admin_settings["credentials"]["username"] == username
        and admin_settings["credentials"]["password"] == password
    ):
        session = await get_session(request)
        session["user"] = username
        response = {"success": True}
        return web.json_response(response)
    else:
        return web.Response(text="Invalid credentials", status=401)

async def logout(request):
    session = await get_session(request)
    session.invalidate()
    raise web.HTTPFound("/login")


@sio.event
async def connect(sid, environ):
    logger.debug("Client connected: %s", sid)

@sio.event
async def disconnect(sid):
    logger.debug("Client disconnected: %s", sid)

@sio.event
async def get_exercises(sid):
    return exercise_model.get_exercises()

@sio.event
async def get_selected_exercises(sid):
    return exercise_model.get_selected_exercises()

@sio.event
async def check_user_authenticated(sid):
    is_auth, reason = await is_authenticated(sid)
    return {"success": is_auth, "message": reason}

@sio.event
@require_auth
async def change_exercise_selection(sid, payload):
    return exercise_model.change_exercise_selection(payload['exercise_uuid'], payload['selected'])

@sio.event
async def get_progress(sid):
    return exercise_model.get_progress()

@sio.event
async def get_users_stats(sid):
    return exercise_model.get_users_stats()

@sio.event
async def get_notifications(sid):
    return notification_model.get_notifications()

@sio.event
@require_auth
async def mark_task_completed(sid, payload):
    exercise_model.mark_task_completed(int(payload['user_id']), payload['exercise_uuid'], payload['task_uuid'])
    sendRefreshScoreTask = sendRefreshScore()
    await sendRefreshScoreTask if sendRefreshScoreTask is not None else None  # Make sure check_active_tasks was not debounced

@sio.event
@require_auth
async def mark_task_incomplete(sid, payload):
    exercise_model.mark_task_incomplete(int(payload['user_id']), payload['exercise_uuid'], payload['task_uuid'])
    sendRefreshScoreTask = sendRefreshScore()
    await sendRefreshScoreTask if sendRefreshScoreTask is not None else None  # Make sure check_active_tasks was not debounced

@sio.event
@require_auth
async def reset_all_exercise_progress(sid):
    return exercise_model.resetAllExerciseProgress()

@sio.event
@require_auth
async def reset_all(sid):
    return exercise_model.resetAllCommand()

@sio.event
@require_auth
async def reset_notifications(sid):
    return notification_model.reset_notifications()

@sio.event
@require_auth
async def get_diagnostic(sid):
    return await getDiagnostic()

@sio.event
async def get_users_activity(sid):
    return notification_model.get_users_activity()

@sio.event
@require_auth
async def toggle_verbose_mode(sid, payload):
    return notification_model.set_verbose_mode(payload['verbose'])

@sio.event
@require_auth
async def toggle_apiquery_mode(sid, payload):
    return notification_model.set_apiquery_mode(payload['apiquery'])

@sio.event
@require_auth
async def remediate_setting(sid, payload):
    return await doSettingRemediation(payload['name'])

@sio.event
@require_auth
async def reload_from_disk(sid):
    return exercise_model.reloadFromDisk()

@sio.on('*')
async def any_event(event, sid, data={}):
    logger.info('>> Unhandled event %s', event)

async def handleMessage(topic, s, message):
    global ZMQ_MESSAGE_COUNT_LAST_TIMESPAN

    data = json.loads(message)

    if topic == 'misp_json_audit':
        user_id, email = notification_model.get_user_email_id_pair(data)
        if user_id is not None and user_id != 0 and '@' in email:
            if user_id not in db.USER_ID_TO_EMAIL_MAPPING:
                db.USER_ID_TO_EMAIL_MAPPING[user_id] = email
                db.EMAIL_TO_USER_ID_MAPPING[email] = user_id
                await sio.emit('new_user', email)

        user_id, authkey = notification_model.get_user_authkey_id_pair(data)
        if user_id is not None and user_id != 0:
            if authkey not in db.USER_ID_TO_AUTHKEY_MAPPING:
                db.USER_ID_TO_AUTHKEY_MAPPING[user_id] = authkey
                return

        if notification_model.is_http_request(data):
            notification = notification_model.get_notification_message(data)
            if notification_model.is_accepted_notification(notification):
                notification_model.record_notification(notification)
                ZMQ_MESSAGE_COUNT_LAST_TIMESPAN += 1
                await sio.emit('notification', notification)
            if notification_model.is_accepted_user_activity(notification):
                user_id = notification_model.get_user_id(data)
                if user_id is not None:
                    USER_ACTIVITY[user_id] += 1

        user_id = notification_model.get_user_id(data)
        if user_id is not None:
            if is_accepted_query_misp(data):
                context = get_context(topic, user_id, data)
                checking_task = exercise_model.check_active_tasks_debounced(user_id, data, context, 'MISP')
                if checking_task is not None:  # Make sure check_active_tasks was not debounced
                    succeeded_once = await checking_task
                    if succeeded_once:
                        sendRefreshScoreTask = sendRefreshScore()
                        await sendRefreshScoreTask if sendRefreshScoreTask is not None else None  # Make sure check_active_tasks was not debounced


async def handleWebhook(data):
    global ZMQ_MESSAGE_COUNT_LAST_TIMESPAN

    email = data.get('email', None)
    user_id = data.get('user_id', None)

    if user_id is not None and user_id != 0 and email is not None:
        if user_id not in db.USER_ID_TO_EMAIL_MAPPING:
            db.USER_ID_TO_EMAIL_MAPPING[user_id] = email
            db.EMAIL_TO_USER_ID_MAPPING[email] = user_id
            await sio.emit("new_user", email)
        else:
            email = db.USER_ID_TO_EMAIL_MAPPING.get(user_id, None)
    elif email is not None:
        user_id = db.EMAIL_TO_USER_ID_MAPPING.get(email, None)

    if user_id is None or email is None:
        error_message = 'Incomplete data passed to webhook endpoint. Could not get associated user'
        logger.warning(">> %s %s", error_message, json.dumps(data)[:100])
        return {"error": error_message}

    if 'target_tool' not in data:
        error_message = "Incomplete data passed to webhook endpoint. Could not get target_tool"
        logger.warning(">> %s %s", error_message, json.dumps(data)[:100])
        return {"error": error_message}

    target_tool = data["target_tool"]
    if target_tool is None or target_tool not in ALLOWED_TARGET_TOOLS:
        error_message = f"Incomplete data passed to webhook endpoint. target_tool `{target_tool}` is not a valid tool. Valid tools: `{json.dumps(ALLOWED_TARGET_TOOLS)}`"
        logger.warning(">> %s %s", error_message, json.dumps(data)[:100])
        return {"error": error_message}
    task_data = data.get('data', {})
    dashboard_message = data.get('dashboard_message', '')
    dashboard_message_variant = data.get("dashboard_message", "warning")

    ### FIXME: Remove this block. This is for a training ###
    with open('/tmp/webhook_data.json', 'w') as f:
        json.dump(task_data, f)
    if target_tool == 'webhook':
        if 'Event' in task_data and task_data.get('_secret', None) != '__secret_key__':
            dashboard_message = f"⚠ {email} is trying to cheat or hasn't reset their Event before sending it for validation ⚠"
            dashboard_message_variant = "danger"
    ### ENDFIXME ###

    if user_id is not None:
        USER_ACTIVITY[user_id] += 1
    notification = notification_model.get_notification_message_for_webhook(
        user_id,
        target_tool,
        task_data,
        dashboard_message=dashboard_message,
        dashboard_message_variant=dashboard_message_variant
    )
    notification_model.record_notification(notification)
    await sio.emit("notification", notification)

    context = get_context('webhook', user_id, data)
    checking_task = exercise_model.check_active_tasks(user_id, task_data, context, 'webhook')
    if checking_task is not None:  # Make sure check_active_tasks was not debounced. FIXME: This might not be necessary anymore.
        succeeded_once = await checking_task
        if succeeded_once:
            sendRefreshScoreTask = sendRefreshScore()
            (
                await sendRefreshScoreTask
                if sendRefreshScoreTask is not None
                else None
            )  # Make sure check_active_tasks was not debounced


@debounce(debounce_seconds=0)
async def sendRefreshScore():
    progress = exercise_model.get_progress()
    await sio.emit('update_progress', progress)
    users_stats = exercise_model.get_users_stats()
    await sio.emit("update_statistics", users_stats)


async def sendUserInjectCheckInProgress(user: int, inject_uuid: str):
    await sio.emit('user_task_check_in_progress', {
        'user_id': user,
        'inject_uuid': inject_uuid
    })


def get_context(topic: str, user_id: int, data: dict) -> dict:
    context = {
        'zmq_topic': topic,
        'user_id': user_id,
        'user_email': db.USER_ID_TO_EMAIL_MAPPING.get(user_id, None),
        'user_authkey': db.USER_ID_TO_AUTHKEY_MAPPING.get(user_id, None),
    }
    if 'Log' in data:
        if 'request_is_rest' in data['Log']:
            context['request_is_rest'] = data['Log']['request_is_rest']
    elif 'authkey_id' in data:
        context['request_is_rest'] = True

    context['webhook'] = topic == 'webhook'
    if topic == 'webhook':
        context["zmq_topic"] = None

    return context


async def getDiagnostic() -> dict:
    global ZMQ_MESSAGE_COUNT

    diagnostic = {}
    diagnostic['MISP'] = {
        'url': config.misp_url,
        'apikey': config.misp_apikey[0:4] + '*'*32 + config.misp_apikey[36:],
    }
    misp_version = await misp_api.getVersion()
    if misp_version is None:
        diagnostic['online'] = False
        return diagnostic
    diagnostic['version'] = misp_version
    misp_settings = await misp_api.getSettings()
    diagnostic['settings'] = misp_settings
    diagnostic['zmq_message_count'] = ZMQ_MESSAGE_COUNT
    diagnostic['suricata'] = {
        'version': getInstalledSuricataVersion(),
    }
    return diagnostic


async def doSettingRemediation(setting) -> dict:
    result = await misp_api.remediateSetting(setting)
    return result


async def notification_history():
    global ZMQ_MESSAGE_COUNT_LAST_TIMESPAN
    while True:
        await sio.sleep(db.NOTIFICATION_HISTORY_FREQUENCY)
        notification_model.record_notification_history(ZMQ_MESSAGE_COUNT_LAST_TIMESPAN)
        ZMQ_MESSAGE_COUNT_LAST_TIMESPAN = 0
        payload = notification_model.get_notifications_history()
        await sio.emit('update_notification_history', payload)


async def record_users_activity():
    global USER_ACTIVITY

    while True:
        await sio.sleep(db.USER_ACTIVITY_FREQUENCY)
        for user_id, activity in USER_ACTIVITY.items():
            notification_model.record_user_activity(user_id, activity)
            USER_ACTIVITY[user_id] = 0
        payload = notification_model.get_users_activity()
        await sio.emit('update_users_activity', payload)


async def keepalive():
    global ZMQ_LAST_TIME
    while True:
        await sio.sleep(5)
        payload = {
            'zmq_last_time': ZMQ_LAST_TIME,
        }
        await sio.emit('keep_alive', payload)
        await sendRefreshScore()


async def backup_exercises_progress():
    while True:
        await sio.sleep(5)
        exercise_model.backup_exercises_progress()


def start_sandbox_agent():
    bin_path = sys.executable
    script_path = os.path.abspath("./backend/sandboxAgent.py")
    process = subprocess.Popen(
        [bin_path, script_path],
        preexec_fn=os.setsid,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    atexit.register(lambda: os.killpg(os.getpgid(process.pid), signal.SIGTERM))
    return process


def start_timed_injects():
    global RUNNING_TIMED_INJECTS

    full_selected_exercises = [exercise for exercise in exercise_model.get_all_exercises() if exercise['exercise']['uuid'] in exercise_model.get_selected_exercises()]
    selected_inject_flows = []
    for exercise in full_selected_exercises:
        for inject_flow in exercise['inject_flow']:
            selected_inject_flows.append(inject_flow)

    stop_all_timed_injects()

    for injectF in selected_inject_flows:
        triggers = injectF.get("sequence", {}).get("trigger", [])
        if ('periodic' in triggers or 'triggered_at' in triggers) and "timing" in injectF:
            for trigger_type, value in injectF['timing'].items():
                if trigger_type == 'triggered_at' and value is not None:
                    start_timed_inject(injectF, trigger_type, value)
                if trigger_type == 'periodic_run_every' and value is not None:
                    start_timed_inject(injectF, trigger_type, value)


def start_timed_inject(injectF, trigger_type, value):
    global RUNNING_TIMED_INJECTS
    if f"{trigger_type}-{injectF['inject_uuid']}" in RUNNING_TIMED_INJECTS:
        return  # Timed inject already running
    random_bits = getrandbits(32)
    uniq_str = f"{trigger_type}-{injectF['inject_uuid']}_{random_bits}"
    RUNNING_TIMED_INJECTS.append(uniq_str)
    sio.start_background_task(timed_inject, injectF, trigger_type, value, random_bits)


def stop_all_timed_injects():
    global RUNNING_TIMED_INJECTS
    RUNNING_TIMED_INJECTS = []


async def timed_inject(injectF, trigger_type, value, random_bits):
    global RUNNING_TIMED_INJECTS

    inject = db.INJECT_BY_UUID.get(injectF['inject_uuid'], None)
    if inject is None:
        return

    uniq_str = f"{trigger_type}-{injectF['inject_uuid']}_{random_bits}"
    if trigger_type == 'triggered_at':
        seconds = value
        await sio.sleep(seconds)
        if uniq_str not in RUNNING_TIMED_INJECTS:
            return  # Timed inject has been stopped

    elif trigger_type == 'periodic_run_every':
        seconds = value
        while True:
            await sio.sleep(seconds)
            if uniq_str not in RUNNING_TIMED_INJECTS:
                return  # Timed inject has been stopped

            data = {}
            context = {
                'evaluation_trigger': trigger_type,
                'request_is_rest': False  # User did not perform the request since we're in timed inject context
            }
            checking_task = exercise_model.check_inject_for_timed_inject(inject, data, context)
            if checking_task is not None:  # Make sure check_active_tasks was not debounced
                succeeded_once = await checking_task
                if succeeded_once:
                    await sendRefreshScore()


# Function to forward zmq messages to Socket.IO
async def forward_zmq_to_socketio():
    global ZMQ_MESSAGE_COUNT, ZMQ_LAST_TIME

    while True:
        message = await zsocket.recv_string()
        topic, s, m = message.partition(" ")
        try:
            ZMQ_MESSAGE_COUNT += 1
            ZMQ_LAST_TIME = time.time()
            await handleMessage(topic, s, m)
        except Exception as e:
            print(e)
            logger.error('Error handling message %s', e)


# Function to forward zmq messages to Socket.IO
async def forward_fake_zmq_to_socketio():
    global ZMQ_MESSAGE_COUNT, ZMQ_LAST_TIME, ZMQ_LOG_FILE, ZMQ_START_LINE_NUMBER
    filename = ZMQ_LOG_FILE
    start_line_number = ZMQ_START_LINE_NUMBER
    line_number = sum(1 for _ in open(filename))
    print(f'Preparing to feed {line_number} lines..')
    print(f'Starting from line {start_line_number}.')
    await sio.sleep(2)

    print('Feeding started')
    line_count = 0
    last_print = time.time()
    with open(filename) as f:
        for line in f:
            line_count += 1
            if line_count-1 < start_line_number:
                continue
            now = time.time()
            if line_count % (int(line_number/100)) == 0 or (now - last_print >= 5):
                last_print = now
                print(f'Feeding {line_count} / {line_number} - ({100* line_count / line_number:.1f}%)')
            split = line.split(' ', 1)
            topic = split[0]
            s = ''
            m = split[1]
            if topic != 'misp_json_self':
                await sio.sleep(0.01)
            try:
                ZMQ_MESSAGE_COUNT += 1
                ZMQ_LAST_TIME = time.time()
                await handleMessage(topic, s, m)
            except Exception as e:
                print(e)
                print(line)
                print(traceback.format_exc())
                logger.error('Error handling message: %s', e)
                await sio.sleep(5)
    print('Feeding done.')


async def init_app(zmq_log_file=None, zmq_start_line_number: int = 0, debug=False):
    global ZMQ_LOG_FILE, ZMQ_START_LINE_NUMBER, DEBUG

    DEBUG = debug
    if zmq_log_file is not None:
        ZMQ_LOG_FILE = zmq_log_file
        ZMQ_START_LINE_NUMBER = zmq_start_line_number
        sio.start_background_task(forward_fake_zmq_to_socketio)
    else:
        exercise_model.restore_exercices_progress()
        sio.start_background_task(forward_zmq_to_socketio)
    sio.start_background_task(keepalive)
    sio.start_background_task(notification_history)
    sio.start_background_task(record_users_activity)
    sio.start_background_task(backup_exercises_progress)
    start_sandbox_agent()

    start_timed_injects()

    return app


app.router.add_static('/assets', WEB_DIST_DIR + '/assets')
app.router.add_get('/', index)
app.router.add_get('/favicon.ico', favicon)
app.router.add_post('/webhook', webhook)
app.router.add_post('/login', login)
app.router.add_route("OPTIONS", "/{tail:.*}", options_handler)
