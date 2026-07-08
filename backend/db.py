#!/usr/bin/env python3

import collections
from typing import Union

USER_ID_TO_EMAIL_MAPPING = {}
EMAIL_TO_USER_ID_MAPPING = {}
USER_ID_TO_AUTHKEY_MAPPING = {}

ALL_EXERCISES = []
SELECTED_EXERCISES = []
INJECT_BY_UUID = {}
INJECT_SEQUENCE_BY_INJECT_UUID = {}
INJECT_REQUIREMENTS_BY_INJECT_UUID = {}
EXERCISES_STATUS = {}

NOTIFICATION_BUFFER_SIZE = 30
NOTIFICATION_MESSAGES = collections.deque([], NOTIFICATION_BUFFER_SIZE)

# Per-user event history for the player drill-down drawer — a deeper ring than
# the global NOTIFICATION_MESSAGES above, kept per user_id so a trainer can
# review one participant's recent request/webhook events (get_user_events).
PER_USER_NOTIFICATION_BUFFER_SIZE = 50
USER_NOTIFICATION_MESSAGES = {}  # user_id -> deque(maxlen=…), newest first

# Per-user inject-evaluation attempts — "buffer A" of the inject-eval-provenance
# feature (PRD-inject-eval-provenance). Each incoming action that triggers an
# evaluation records ONE EvaluationAttempt (the captured {outcome, debug} trace of
# every available task it was checked against), kept newest-first per user so the
# drawer can answer "why did / didn't this count?". Bounded ring — the last X per
# user. Ephemeral: never persisted to backup.json (all eval data is memory-only).
ATTEMPT_BUFFER_SIZE = 20
USER_EVALUATION_ATTEMPTS = {}  # user_id -> deque(maxlen=ATTEMPT_BUFFER_SIZE), newest first

NOTIFICATION_HISTORY_BUFFER_RESOLUTION_PER_MIN = 12
NOTIFICATION_HISTORY_BUFFER_TIMESPAN_MIN = 20
NOTIFICATION_HISTORY_FREQUENCY = 60 / NOTIFICATION_HISTORY_BUFFER_RESOLUTION_PER_MIN
notification_history_buffer_size = NOTIFICATION_HISTORY_BUFFER_RESOLUTION_PER_MIN * NOTIFICATION_HISTORY_BUFFER_TIMESPAN_MIN
NOTIFICATION_HISTORY = collections.deque([], notification_history_buffer_size)
NOTIFICATION_HISTORY.extend([0] * notification_history_buffer_size)

USER_ACTIVITY_BUFFER_RESOLUTION_PER_MIN = 2
USER_ACTIVITY_TIMESPAN_MIN = 20
USER_ACTIVITY_FREQUENCY = 60 / USER_ACTIVITY_BUFFER_RESOLUTION_PER_MIN
USER_ACTIVITY = {}
user_activity_buffer_size = USER_ACTIVITY_BUFFER_RESOLUTION_PER_MIN * USER_ACTIVITY_TIMESPAN_MIN


def resetNotificationMessage():
   global NOTIFICATION_MESSAGES
   NOTIFICATION_MESSAGES = collections.deque([], NOTIFICATION_BUFFER_SIZE)

def resetUserNotificationMessages():
   global USER_NOTIFICATION_MESSAGES
   USER_NOTIFICATION_MESSAGES = {}

def addUserNotification(user_id: int, notification: dict):
   global USER_NOTIFICATION_MESSAGES
   if user_id not in USER_NOTIFICATION_MESSAGES:
      USER_NOTIFICATION_MESSAGES[user_id] = collections.deque([], PER_USER_NOTIFICATION_BUFFER_SIZE)
   USER_NOTIFICATION_MESSAGES[user_id].appendleft(notification)

def resetUserEvaluationAttempts():
   global USER_EVALUATION_ATTEMPTS
   USER_EVALUATION_ATTEMPTS = {}

def addUserEvaluationAttempt(user_id: int, attempt: dict):
   global USER_EVALUATION_ATTEMPTS
   if user_id not in USER_EVALUATION_ATTEMPTS:
      USER_EVALUATION_ATTEMPTS[user_id] = collections.deque([], ATTEMPT_BUFFER_SIZE)
   USER_EVALUATION_ATTEMPTS[user_id].appendleft(attempt)

def resetNotificationHistory():
   global NOTIFICATION_HISTORY
   NOTIFICATION_HISTORY = collections.deque([], notification_history_buffer_size)
   NOTIFICATION_HISTORY.extend([0] * notification_history_buffer_size)

def addUserActivity(user_id: int, count: int):
   global USER_ACTIVITY, USER_ACTIVITY_TIMESPAN_MIN

   if user_id not in USER_ACTIVITY:
      USER_ACTIVITY[user_id] = collections.deque([], user_activity_buffer_size)
      USER_ACTIVITY[user_id].extend([0] * user_activity_buffer_size)
   USER_ACTIVITY[user_id].append(count)

def resetUserActivity():
   for user_id in USER_ACTIVITY.keys():
      USER_ACTIVITY[user_id] = collections.deque([], user_activity_buffer_size)
      USER_ACTIVITY[user_id].extend([0] * user_activity_buffer_size)
