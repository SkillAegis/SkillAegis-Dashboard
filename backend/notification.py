#!/usr/bin/env python3

import datetime
import json
import re
from typing import Union
import backend.db as db
import backend.config as config
import backend.appConfig as appConfig
from urllib.parse import parse_qs


VERBOSE_MODE = False
APIQUERY_MODE = False
NOTIFICATION_COUNT = 1


def set_verbose_mode(enabled: bool):
    global VERBOSE_MODE
    VERBOSE_MODE = enabled


def set_apiquery_mode(enabled: bool):
    global APIQUERY_MODE
    APIQUERY_MODE = enabled


def get_notifications() -> list[dict]:
    return list(db.NOTIFICATION_MESSAGES)


def get_user_events(user_id: int) -> list[dict]:
    buffer = db.USER_NOTIFICATION_MESSAGES.get(user_id)
    return list(buffer) if buffer is not None else []


def get_notifications_history() -> dict:
    return {
        'history': list(db.NOTIFICATION_HISTORY),
        'config': {
            'buffer_resolution_per_minute': db.NOTIFICATION_HISTORY_BUFFER_RESOLUTION_PER_MIN,
            'buffer_timestamp_min': db.NOTIFICATION_HISTORY_BUFFER_TIMESPAN_MIN,
            'frequency': db.NOTIFICATION_HISTORY_FREQUENCY,
            'notification_history_size': db.notification_history_buffer_size,
        },
    }


def get_users_activity() -> dict:
    return {
        'activity': {user_id: list(activity) for user_id, activity in db.USER_ACTIVITY.items()},
        'config': {
            'timestamp_min': db.USER_ACTIVITY_TIMESPAN_MIN,
            'buffer_resolution_per_minute': db.USER_ACTIVITY_BUFFER_RESOLUTION_PER_MIN,
            'frequency': db.USER_ACTIVITY_FREQUENCY,
            'activity_buffer_size': db.user_activity_buffer_size,
        },
    }


def reset_notifications():
    db.resetNotificationMessage()
    db.resetUserNotificationMessages()


def record_notification(notification: dict):
    db.NOTIFICATION_MESSAGES.appendleft(notification)
    user_id = notification.get('user_id')
    if user_id is not None:
        db.addUserNotification(user_id, notification)


def record_notification_history(message_count: int):
    db.NOTIFICATION_HISTORY.append(message_count)


def record_user_activity(user_id: int, count: int):
    db.addUserActivity(user_id, count)


def get_user_id(data: dict):
    if 'user_id' in data:
        return int(data['user_id'])
    if 'Log' in data:
        data = data['Log']
        if 'user_id' in data:
            return int(data['user_id'])
    if 'AuditLog' in data:
        data = data['AuditLog']
        if 'user_id' in data:
            return int(data['user_id'])
    return None


def get_user_email_id_pair(data: dict):
    if 'Log' in data:
        data = data['Log']
        if 'email' in data and 'user_id' in data:
            return (int(data['user_id']), data['email'],)
    return (None, None,)


def get_user_authkey_id_pair(data: dict):
    authkey_title_regex = r".*API key.*\((\w+)\)"
    if 'Log' in data:
        data = data['Log']
        if 'user_id' in data and 'title' in data :
            if data['title'].startswith('Successful authentication using API key'):
                authkey_search = re.search(authkey_title_regex, data['title'], re.IGNORECASE)
                if authkey_search is not None:
                    authkey = authkey_search.group(1)
                    return (int(data['user_id']), authkey,)
    return (None, None,)


def is_http_request(data: dict) -> bool:
    if ('url' in data and
        'request_method' in data and
        'response_code' in data and
        'user_id' in data):
        return True
    return False


def get_content_type(data: dict) -> Union[None, str]:
    if 'request' not in data:
        return None
    request_content = data['request']
    content_type, _ = request_content.split('\n\n')
    return content_type


def clean_form_urlencoded_data(post_body_parsed: dict) -> dict:
    cleaned = {}
    for k, v in post_body_parsed.items():
        if k.startswith('data[') and not k.startswith('data[_'):
            clean_k = '.'.join([k for k in re.split(r'[\[\]]', k) if k != ''][1:])
            clean_v = v[0] if type(v) is list and len(v) == 1 else v
            cleaned[clean_k] = clean_v
    return cleaned


def get_request_post_body(data: dict) -> dict:
    if 'request' not in data:
        return {}
    request_content = data['request']
    content_type, post_body = request_content.split('\n\n')
    if content_type == 'application/json':
        try:
            post_body_parsed = json.loads(post_body) if len(post_body) > 0 else {}
        except:
            post_body_parsed = {}
        return post_body_parsed
    elif content_type == 'application/x-www-form-urlencoded':
        post_body_parsed = parse_qs(post_body)
        post_body_clean = clean_form_urlencoded_data(post_body_parsed)
        return post_body_clean
    return {}


def is_api_request(data: dict) -> bool:
    content_type = get_content_type(data)
    return content_type == 'application/json'


def get_notification_message(data: dict) -> dict:
    global NOTIFICATION_COUNT
    id = NOTIFICATION_COUNT
    NOTIFICATION_COUNT += 1
    user = db.USER_ID_TO_EMAIL_MAPPING.get(int(data['user_id']), '?')
    time = data['created'].split(' ')[1].split('.')[0]
    url = data['url']
    http_method = data.get('request_method', 'GET')
    response_code = data.get('response_code', '?')
    user_agent = data.get('user_agent', '?')
    _, action = get_scope_action_from_url(url)
    http_method = 'DELETE' if (http_method == 'POST' or http_method == 'PUT') and action == 'delete' else http_method  # small override for UI
    payload = get_request_post_body(data)
    return {
        "id": id,
        "notification_origin": "zmq",
        "user_id": int(data["user_id"]),
        "user": user,
        "time": time,
        "url": url,
        "http_method": http_method,
        "user_agent": user_agent,
        "is_api_request": is_api_request(data),
        "response_code": response_code,
        "payload": payload,
    }


def get_notification_message_for_webhook(
    user_id: int,
    target_tool: str,
    task_data: dict,
    dashboard_message=None,
    dashboard_message_variant="warning",
) -> dict:
    global NOTIFICATION_COUNT
    id = NOTIFICATION_COUNT
    NOTIFICATION_COUNT += 1
    user = db.USER_ID_TO_EMAIL_MAPPING.get(user_id, "?")
    time = datetime.datetime.now().strftime("%H:%M:%S")
    num_keys = len(task_data)
    json_size_bytes = len(json.dumps(task_data).encode("utf-8"))
    payload = f"@data - {json_size_bytes} byte(s), {num_keys} key(s)"

    notification = {
        "id": id,
        "notification_origin": "webhook",
        "target_tool": target_tool,
        "user_id": user_id,
        "user": user,
        "time": time,
        "payload": payload,
        "message": {
            "text": dashboard_message,
            "variant": dashboard_message_variant,
        },
    }
    if dashboard_message is not None:
        notification["message"] = {
            "text": dashboard_message,
            "variant": dashboard_message_variant,
        }
    return notification


def get_scope_action_from_url(url) -> Union[str, None]:
    split = url.split('/')
    if len(split) > 2:
        return (split[1], split[2],)
    else:
        return (None, None,)


def is_accepted_notification(notification) -> bool:
    global VERBOSE_MODE

    if notification['user_agent'] == 'SkillAegis': # Ignore message generated from this app
        return False
    if VERBOSE_MODE:
        return True
    if APIQUERY_MODE and not notification['is_api_request']:
        return False
    if '@' not in notification['user']: # Ignore message from system
        return False

    scope, action = get_scope_action_from_url(notification['url'])
    if scope in appConfig.live_logs_accepted_scope:
        if appConfig.live_logs_accepted_scope == '*':
            return True
        elif action in appConfig.live_logs_accepted_scope[scope]:
            return True
    return False


def is_accepted_user_activity(notification) -> bool:
    global VERBOSE_MODE

    if notification['user_agent'] == 'SkillAegis': # Ignore message generated from this app
        return False
    if '@' not in notification['user']: # Ignore message from system
        return False

    scope, action = get_scope_action_from_url(notification['url'])
    if scope in appConfig.user_activity_accepted_scope:
        if appConfig.user_activity_accepted_scope == '*':
            return True
        elif action in appConfig.user_activity_accepted_scope[scope]:
            return True
    return False
