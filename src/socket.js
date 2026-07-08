import { reactive, computed } from 'vue'
import { io } from 'socket.io-client'
import { toast } from '@/utils'
import debounce from 'lodash.debounce'

// "undefined" means the URL will be computed from the `window.location` object
const URL = !import.meta.env.DEV ? '' : 'http://localhost:4001'
const MAX_LIVE_LOG = 30
// Per-user drawer history is a deeper ring than the global feed (mirrors the
// backend's PER_USER_NOTIFICATION_BUFFER_SIZE).
const MAX_USER_EVENTS = 50
// Per-user captured-evaluation ring (buffer A), mirroring the backend's
// ATTEMPT_BUFFER_SIZE — the "what went wrong on my last tries" store.
const MAX_USER_EVALUATIONS = 20

const initial_state = {
  notificationEvents: [],
  notificationCounter: 0,
  notificationAPICounter: 0,
  notificationHistory: [],
  notificationHistoryConfig: {},
  userActivity: {},
  userActivityConfig: {},
  exercises: [],
  selected_exercises: [],
  progresses: {},
  userTaskCheckInProgress: {},
  userStats: {},
  diagnostic: {},
  userEvents: [],
  userEvaluations: [],
}

// Which participant `state.userEvents` currently holds, so the live `notification`
// push only appends events for the open drawer's player (null when closed).
let eventsUserId = null
// Same, for `state.userEvaluations` (buffer A): the live `user_evaluation_recorded`
// push only prepends attempts for the open drawer's player (null when closed).
let evaluationsUserId = null

const state = reactive({ ...initial_state })
const connectionState = reactive({
  is_authenticated: false,
  connected: false,
  zmq_last_time: false
})


const socket = io(URL, {
  autoConnect: true,
  withCredentials: import.meta.env.DEV,
})

/* Public */
/* ------ */

export const BASE_URL = URL
export const exercises = computed(() => state.exercises)
export const selected_exercises = computed(() => state.selected_exercises)
export const active_exercises = computed(() =>
  state.exercises.filter((exercise) => state.selected_exercises.includes(exercise.uuid))
)
export const shouldHideGamification = computed(() => {
  return active_exercises.value.length >= 1 && active_exercises.value.every(exercise => exercise.gamification === false);
})
export const progresses = computed(() => state.progresses)
export const notifications = computed(() => state.notificationEvents)
export const notificationCounter = computed(() => state.notificationCounter)
export const notificationAPICounter = computed(() => state.notificationAPICounter)
export const userCount = computed(() => Object.keys(state.progresses).length)
export const diagnostic = computed(() => state.diagnostic)
export const notificationHistory = computed(() => state.notificationHistory)
export const notificationHistoryConfig = computed(() => state.notificationHistoryConfig)
export const userActivity = computed(() => state.userActivity)
export const userActivityConfig = computed(() => state.userActivityConfig)
export const socketConnected = computed(() => connectionState.connected)
export const zmqLastTime = computed(() => connectionState.zmq_last_time)
export const userAuthenticated = computed(() => connectionState.is_authenticated)
export const userTaskCheckInProgress = computed(() => state.userTaskCheckInProgress)
export const userStats = computed(() => state.userStats)
export const userEvents = computed(() => state.userEvents)
export const userEvaluations = computed(() => state.userEvaluations)

export function resetState() {
  Object.assign(state, initial_state)
}

export function fullReload() {
  getExercises()
  getSelectedExercises()
  getNotifications()
  getProgress()
  getUsersStats()
  getUsersActivity()
}

export function checkUserAuthenticated() {
  return sendCheckUserAuthenticated()
}

export async function login(payload) {
  return doLogin(payload)
}

export async function logout() {
  return doLogout()
}

export function setCompletedState(completed, user_id, exec_uuid, task_uuid) {
  const payload = {
    user_id: user_id,
    exercise_uuid: exec_uuid,
    task_uuid: task_uuid
  }
  sendCompletedState(completed, payload)
}

export function resetAllExerciseProgress() {
  sendResetAllExerciseProgress()
}

export function resetAll() {
  sendResetAll()
}

export function resetLiveLogs() {
  sendResetLiveLogs()
}

// Player drill-down drawer: seed the events rail with this participant's recent
// history (the backend `get_user_events` per-user ring, deeper than the global
// feed), then the `notification` handler live-appends new events for this player.
export function loadUserEvents(user_id) {
  eventsUserId = user_id
  state.userEvents = []
  socket.emit('get_user_events', { user_id }, (events) => {
    // Guard against a stale ack after the drawer moved to another player / closed.
    if (eventsUserId === user_id) {
      state.userEvents = Array.isArray(events) ? events : []
    }
  })
}

export function clearUserEvents() {
  eventsUserId = null
  state.userEvents = []
}

// Player drill-down drawer: seed buffer A (this participant's ring of captured
// EvaluationAttempts) so the drawer's completed-task "View evaluation" (Phase 4)
// and event-history outcomes (Phase 5) have the full traces; the
// `user_evaluation_recorded` handler then live-prepends new attempts for them.
export function loadUserEvaluations(user_id) {
  evaluationsUserId = user_id
  state.userEvaluations = []
  socket.emit('get_user_evaluations', { user_id }, (evals) => {
    // Guard against a stale ack after the drawer moved to another player / closed.
    if (evaluationsUserId === user_id) {
      state.userEvaluations = Array.isArray(evals) ? evals : []
    }
  })
}

export function clearUserEvaluations() {
  evaluationsUserId = null
  state.userEvaluations = []
}

export function reloadFromDisk() {
  sendReloadFromDisk()
}

export function changeExerciseSelection(exec_uuid, state_enabled) {
  const payload = {
    exercise_uuid: exec_uuid,
    selected: state_enabled
  }
  sendChangeExerciseSelection(payload)
}

export function toggleVerboseMode(enabled) {
  sendToggleVerboseMode(enabled)
}

export function toggleApiQueryMode(enabled) {
  sendToggleApiQueryMode(enabled)
}

export function remediateSetting(setting) {
  sendRemediateSetting(setting, (result) => {
    if (result.success) {
      state.diagnostic['settings'][setting].value =
        state.diagnostic['settings'][setting].expected_value
    } else {
      state.diagnostic['settings'][setting].error = true
      state.diagnostic['settings'][setting].errorMessage = result.message
    }
  })
}

export const debouncedGetProgress = debounce(getProgress, 200, { leading: true })
export const debouncedGetDiagnostic = debounce(getDiagnostic, 1000, { leading: true })

/* Private */
/* ------- */

function emitReplyHandler(reply) {
  if (reply !== undefined && reply['error'] !== undefined) {
    toast({
      variant: 'danger',
      message: reply['error'],
      title: 'Error from server'
    })
  }
}

function getExercises() {
  socket.emit('get_exercises', (all_exercises) => {
    state.exercises = all_exercises
  })
}

function getSelectedExercises() {
  socket.emit('get_selected_exercises', (all_selected_exercises) => {
    state.selected_exercises = all_selected_exercises
  })
}

function getNotifications() {
  socket.emit('get_notifications', (all_notifications) => {
    state.notificationEvents = all_notifications
  })
}

function getProgress() {
  socket.emit('get_progress', (all_progress) => {
    // all_progress = Array(20).fill().map(item => (all_progress[1]))
    state.progresses = all_progress
    updateTaskCheckInProgress()
  })
}

function updateTaskCheckInProgress() {
  Object.keys(state.progresses).forEach(user_id => {
    Object.values(state.progresses[user_id].exercises).forEach(exercise => {
      Object.keys(exercise.tasks_completion).forEach(inject_uuid => {
        const key = `${user_id}_${inject_uuid}`
        if (state.userTaskCheckInProgress[key] === undefined) {
          state.userTaskCheckInProgress[key] = false
        }
      });
    });
  });
}

function getUsersActivity() {
  socket.emit('get_users_activity', (user_activity_bundle) => {
    state.userActivity = user_activity_bundle.activity
    state.userActivityConfig = user_activity_bundle.config
  })
}

function getUsersStats() {
  socket.emit('get_users_stats', (user_stats) => {
    state.userStats = user_stats
  })
}

function getDiagnostic() {
  state.diagnostic = {}
  socket.emit('get_diagnostic', (diagnostic) => {
    state.diagnostic = diagnostic
  })
}

function sendCheckUserAuthenticated() {
  socket.emit('check_user_authenticated', (status) => {
    connectionState.is_authenticated = status?.success === true
  })
}

async function doLogin(payload) {
  try {
    const response = await fetch(`${URL}/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: import.meta.env.DEV ? "include" : "same-origin",
      body: JSON.stringify(payload)
    })

    if (response.status === 401) {
      connectionState.is_authenticated = false
      return { success: false, message: 'Invalid email or password.' }
    }

    if (!response.ok) {
      connectionState.is_authenticated = false
      return { success: false, message: `Login failed: ${response.status}` }
    }

    const data = await response.json()
    connectionState.is_authenticated = true

    // Reconnect client to bind its socketio state to aiohttp.request's state
    socket.disconnect()
    socket.connect()
    return { success: true, message: 'Sucessfully logged in', data: data }
  } catch (error) {
    connectionState.is_authenticated = false
    return { success: false, message: 'Network error. Please try again.' }
  }
}

async function doLogout() {
  try {
    const response = await fetch(`${URL}/logout`, {
      method: 'POST',
      credentials: import.meta.env.DEV ? "include" : "same-origin"
    })

    // Drop client auth state regardless, then reconnect so the socket's
    // handshake session no longer carries the (now invalidated) auth — mirrors
    // doLogin's rebind.
    connectionState.is_authenticated = false
    socket.disconnect()
    socket.connect()

    if (!response.ok) {
      return { success: false, message: `Logout failed: ${response.status}` }
    }
    return { success: true, message: 'Successfully logged out' }
  } catch (error) {
    connectionState.is_authenticated = false
    return { success: false, message: 'Network error during logout.' }
  }
}

function sendCompletedState(completed, payload) {
  if (!userAuthenticated.value)
    return
  const event_name = !completed ? 'mark_task_completed' : 'mark_task_incomplete'
  socket.emit(event_name, payload, (reply) => {
    emitReplyHandler(reply)
    getProgress()
  })
}

function sendResetAllExerciseProgress() {
  if (!userAuthenticated.value)
    return
  socket.emit('reset_all_exercise_progress', (reply) => {
    emitReplyHandler(reply)
    getProgress()
    getSelectedExercises()
  })
}

function sendResetAll() {
  if (!userAuthenticated.value)
    return
  socket.emit('reset_all', (reply) => {
    emitReplyHandler(reply)
    getProgress()
    getSelectedExercises()
  })
}

function sendResetLiveLogs() {
  if (!userAuthenticated.value)
    return
  socket.emit('reset_notifications', (reply) => {
    emitReplyHandler(reply)
    getNotifications()
  })
}

function sendReloadFromDisk() {
  if (!userAuthenticated.value)
    return
  socket.emit('reload_from_disk', (reply) => {
    emitReplyHandler(reply)
    getExercises()
    getSelectedExercises()
  })
}

function sendChangeExerciseSelection(payload) {
  if (!userAuthenticated.value)
    return
  socket.emit('change_exercise_selection', payload, (reply) => {
    emitReplyHandler(reply)
    getSelectedExercises()
  })
}

function sendToggleVerboseMode(enabled) {
  if (!userAuthenticated.value)
    return
  const payload = {
    verbose: enabled
  }
  socket.emit('toggle_verbose_mode', payload, (reply) => {
    emitReplyHandler(reply)
  })
}

function sendToggleApiQueryMode(enabled) {
  if (!userAuthenticated.value)
    return
  const payload = {
    apiquery: enabled
  }
  socket.emit('toggle_apiquery_mode', payload, (reply) => {
    emitReplyHandler(reply)
  })
}

function sendRemediateSetting(setting, cb) {
  if (!userAuthenticated.value)
    return
  const payload = {
    name: setting
  }
  socket.emit('remediate_setting', payload, (result) => {
    emitReplyHandler(result)
    cb(result)
  })
}

/* Event listener */
socket.on('connect', () => {
  connectionState.connected = true
})

socket.on('disconnect', () => {
  connectionState.connected = false
})

socket.on('notification', (message) => {
  state.notificationCounter += 1
  if (message.is_api_request) {
    state.notificationAPICounter += 1
  }
  addLimited(state.notificationEvents, message, MAX_LIVE_LOG)
  // Live-append to the open drawer's events rail, this player's events only.
  if (eventsUserId !== null && message.user_id === eventsUserId) {
    addLimited(state.userEvents, message, MAX_USER_EVENTS)
  }
})

socket.on('new_user', (new_user) => {
  debouncedGetProgress()
})

socket.on('refresh_score', () => {
  debouncedGetProgress()
})

socket.on('keep_alive', (keep_alive) => {
  connectionState.zmq_last_time = keep_alive['zmq_last_time']
})

socket.on('update_notification_history', (notification_history_bundle) => {
  state.notificationHistory = notification_history_bundle.history
  state.notificationHistoryConfig = notification_history_bundle.config
})

socket.on('update_users_activity', (user_activity_bundle) => {
  state.userActivity = user_activity_bundle.activity
  state.userActivityConfig = user_activity_bundle.config
})

socket.on('update_progress', (all_progress) => {
  state.progresses = all_progress
  updateTaskCheckInProgress()
})

socket.on('update_statistics', (user_stats) => {
  state.userStats = user_stats
})


socket.on('user_task_check_in_progress', ({ user_id, inject_uuid }) => {
  state.userTaskCheckInProgress[`${user_id}_${inject_uuid}`] = true
  setTimeout(() => {
    state.userTaskCheckInProgress[`${user_id}_${inject_uuid}`] = false
  }, 3000);
})

// Emitted after an evaluation that cleared a task, carrying the id of the feed
// row that triggered it (the feed is completed-only — nothing is pushed for
// actions that cleared nothing). Merge the cleared tasks onto the already-
// rendered feed row so LiveFeed can light its completion pip; best-effort, so a
// row that has scrolled out of the ring simply goes unmarked.
socket.on('notification_outcome', ({ notification_id, completed_tasks }) => {
  const row = state.notificationEvents.find((n) => n.id === notification_id)
  if (row) {
    row.completed_tasks = Array.isArray(completed_tasks) ? completed_tasks : []
  }
})

// A newly captured evaluation attempt (buffer A). Live-prepend to the open
// drawer's evaluation ring for this player only, so its "View evaluation" traces
// stay current as completions happen while the drawer is open — mirrors how
// `notification` feeds `userEvents`.
socket.on('user_evaluation_recorded', ({ user_id, attempt }) => {
  if (evaluationsUserId !== null && user_id === evaluationsUserId && attempt) {
    addLimited(state.userEvaluations, attempt, MAX_USER_EVALUATIONS)
  }
})

function addLimited(target, message, maxCount) {
  target.unshift(message)
  if (target.length > maxCount) {
    target.length = maxCount
  }
}
