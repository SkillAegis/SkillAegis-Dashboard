import random
import string
from backend.config import admin_email, admin_password

live_logs_accepted_scope = {
    'events': ['add', 'edit', 'delete', 'restSearch',],
    'attributes': ['add', 'add_attachment', 'edit', 'revise_object', 'delete', 'restSearch',],
    'eventReports': ['add', 'edit', 'delete',],
    'tags': '*',
}

user_activity_accepted_scope = {
    'events': ['view', 'add', 'edit', 'delete', 'restSearch',],
    'attributes': ['add', 'add_attachment', 'edit', 'delete', 'restSearch',],
    'objects': ['add', 'edit', 'revise_object', 'delete',],
    'eventReports': ['view', 'add', 'edit', 'delete',],
    'tags': '*',
}

misp_settings = {
    'Plugin.ZeroMQ_enable': True,
    'Plugin.ZeroMQ_audit_notifications_enable': True,
    'Plugin.ZeroMQ_event_notifications_enable': True,
    'Plugin.ZeroMQ_attribute_notifications_enable': True,
    'MISP.log_paranoid': True,
    'MISP.log_paranoid_skip_db': True,
    'MISP.log_paranoid_include_post_body': True,
    'MISP.log_auth': True,
    'Security.allow_unsafe_cleartext_apikey_logging': True,
}

leaderboard_settings = {
    "time_one_fire_window_sec": 60 * 4,
    "speedrunner_volume_boost": 1.5,
    "speedrunner_speed_boost": 0.7,
}

length = 16
random_string = "".join(random.choices(string.ascii_letters + string.digits, k=length))
admin_settings = {
    "credentials": {
        "username": "admin@admin.test" if admin_email is None else admin_email,
        "password": random_string if admin_password is None else admin_password,
    }
}

import logging
logger = logging.getLogger('SkillAegis')
format = '[%(levelname)s] %(asctime)s - %(message)s'
formatter = logging.Formatter(format)
logging.basicConfig(filename='SkillAegis.log', encoding='utf-8', level=logging.DEBUG, format=format)
# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logging.getLogger().addHandler(ch)

logging.info(f"Administrator credentials: {admin_settings['credentials']}")