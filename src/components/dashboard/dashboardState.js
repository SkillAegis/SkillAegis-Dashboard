/**
 * Shared state + view-models for the live exercise dashboard.
 *
 * This module is the single place that turns the raw reactive state exposed by
 * `socket.js` (progresses, userStats, notifications, activity buffers, …) into
 * the shapes the dashboard design consumes (leaderboard rows, podium, rotating
 * champion scenes, live feed, activity timeline, header stats).
 *
 * It mirrors the pattern used by `socket.js`: a module-level singleton of
 * reactive state and `computed` view-models that components import directly.
 *
 * Color strings reference the .sa-root token layer (see CLAUDE.md → Conventions)
 * via `var(...)`, which resolves fine inside the inline styles these feed.
 */
import { ref, reactive, computed, watch } from 'vue'
import {
  progresses,
  userStats,
  notifications,
  notificationCounter,
  notificationAPICounter,
  userActivity,
  userActivityConfig,
  notificationHistory,
  notificationHistoryConfig,
  active_exercises,
  userCount,
  shouldHideGamification,
} from '@/socket'

/* ------------------------------------------------------------------ */
/* Tunables (kept in sync with the source design)                     */
/* ------------------------------------------------------------------ */
const ROW_HEIGHT = 58 // px, height of a single leaderboard row slot (card + vertical padding)
const SCENE_MS = 7000 // champion slot rotates between scenes this often
const ROT_MS = 4500 // champion sub-list pages rotate this often
const CHAMPION_PAGE = 4 // entries per champion sub-list page
const JUST_SCORED_MS = 1700 // how long the "+N" score pop stays visible
const BURST_MS = 1600 // how long the all-clear completion burst plays on a row
const RECENT_LIMIT = 5 // rows in the "Just Cleared" strip pinned atop the feed

export { ROW_HEIGHT }

/* ------------------------------------------------------------------ */
/* Shared UI control state (header toggles + searches)                */
/* ------------------------------------------------------------------ */
export const sortByScore = ref(true)
export const hideInactive = ref(false)
export const autoPaginate = ref(true)
export const searchUser = ref('')
export const searchUrl = ref('')
export const selectedExerciseIndex = ref(0)

export function toggleSort() {
  sortByScore.value = !sortByScore.value
}
export function toggleHide() {
  hideInactive.value = !hideInactive.value
}
export function togglePaginate() {
  autoPaginate.value = !autoPaginate.value
}
export function selectExercise(index) {
  selectedExerciseIndex.value = index
}

export const selectedExercise = computed(() => {
  const list = active_exercises.value
  if (!list.length) return null
  const idx = Math.min(selectedExerciseIndex.value, list.length - 1)
  return list[idx]
})

// Keep the selected index valid as exercises are (de)selected.
watch(active_exercises, (list) => {
  if (selectedExerciseIndex.value > list.length - 1) {
    selectedExerciseIndex.value = 0
  }
})

export { active_exercises, shouldHideGamification }

/* ------------------------------------------------------------------ */
/* A single shared clock — drives rotation, countdowns, "just scored" */
/* ------------------------------------------------------------------ */
export const now = ref(Date.now())
setInterval(() => {
  now.value = Date.now()
}, 1000)

/* ------------------------------------------------------------------ */
/* Champion slot scene control (auto-rotate, overridable by clicking)  */
/* ------------------------------------------------------------------ */
// On Fire / Speed Runner / Trophies, plus a Finishers scene that appears only
// once someone has cleared everything (`sceneCount`, defined below, grows to 4).
export const currentScene = ref(0)
// Pinning freezes the rotation on whatever scene is showing (e.g. keep Finishers
// up for the room). Manual jumps via the scene dots still work while pinned.
export const scenePinned = ref(false)
let lastSceneChange = now.value

// Auto-advance on the shared clock; a manual pick resets the dwell timer
// so the chosen scene gets a full SCENE_MS before rotation resumes. While
// pinned, hold the timer at "now" so unpinning grants a fresh full dwell.
watch(now, (t) => {
  if (scenePinned.value) {
    lastSceneChange = t
    return
  }
  if (t - lastSceneChange >= SCENE_MS) {
    currentScene.value = (currentScene.value + 1) % sceneCount.value
    lastSceneChange = t
  }
})

export function setScene(i) {
  const n = sceneCount.value
  currentScene.value = ((i % n) + n) % n
  lastSceneChange = now.value
}
export function nextScene() {
  setScene(currentScene.value + 1)
}
export function toggleScenePinned() {
  scenePinned.value = !scenePinned.value
}

/* ------------------------------------------------------------------ */
/* Helpers                                                            */
/* ------------------------------------------------------------------ */
function splitEmail(email) {
  const [local, domain] = String(email ?? '').split('@')
  return { name: local || String(email ?? ''), org: domain ? '@' + domain : '' }
}

function heatColor(v) {
  if (v <= 0) return 'rgba(var(--sa-cyan-rgb),.07)'
  if (v <= 1) return 'rgba(var(--sa-cyan-rgb),.28)'
  if (v <= 2) return 'rgba(var(--sa-cyan-rgb),.55)'
  return 'var(--sa-cyan)'
}

// Build an rgba() string from a `--x-rgb` channel-triple token and an alpha,
// e.g. alpha('var(--sa-gold-rgb)', 0.13) → "rgba(var(--sa-gold-rgb), 0.13)".
function alpha(rgbVar, a) {
  return `rgba(${rgbVar}, ${a})`
}

function fmtDur(ms) {
  if (!Number.isFinite(ms) || ms < 0) ms = 0
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const p = (x) => String(x).padStart(2, '0')
  return (h ? p(h) + ':' : '') + p(m) + ':' + p(ss)
}

// Single-unit "time ago" for a recent event: "12s" / "3m" / "1h" / "2d".
// Counts up live against the shared `now` clock — no new data needed.
function fmtAgo(ms) {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

// Compact clock for an accumulated duration in seconds: "M:SS"
// (or "H:MM:SS" past an hour). Used for "time on fire", which is a duration,
// not a decimal-minutes count.
function fmtClock(totalSeconds) {
  const s = Math.max(0, Math.round(Number(totalSeconds) || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const p = (x) => String(x).padStart(2, '0')
  return h ? `${h}:${p(m)}:${p(ss)}` : `${m}:${p(ss)}`
}

const bufferSize = computed(() => userActivityConfig.value?.activity_buffer_size || 0)

function isActive(user_id) {
  const act = userActivity.value?.[user_id]
  if (!act || !act.length || !bufferSize.value) return false
  const lastQuarter = act.slice(-parseInt(bufferSize.value / 4))
  return lastQuarter.some((a) => a > 0)
}

function taskRequirementMet(tasksCompletion, task) {
  const reqUuid = task.requirements?.inject_uuid
  if (reqUuid === undefined) return true
  return !!tasksCompletion[reqUuid]
}

/* ------------------------------------------------------------------ */
/* "Just scored" detection — flash a +N when a user's score grows     */
/* ------------------------------------------------------------------ */
const prevScores = {}
const prevDone = {}
const gains = reactive({})
// Set the instant a user's completed-task count reaches the full set, used to
// fire the one-shot all-clear burst. Only the live transition triggers it — a
// page reload onto an already-complete board stays calm (prevDone is unseeded).
const completions = reactive({})

watch(
  () => progresses.value,
  (np) => {
    const ex = selectedExercise.value
    if (!ex) return
    const tasksLen = ex.tasks.length
    for (const p of Object.values(np)) {
      const exProgress = p.exercises?.[ex.uuid]
      if (!exProgress) continue
      const key = `${p.user_id}|${ex.uuid}`
      const score = exProgress.score ?? 0
      const prevScore = prevScores[key]
      if (prevScore !== undefined && score > prevScore) {
        gains[p.user_id] = { gain: score - prevScore, at: Date.now() }
      }
      prevScores[key] = score

      const done = Object.values(exProgress.tasks_completion || {}).filter((t) => t !== false).length
      const prevD = prevDone[key]
      if (prevD !== undefined && tasksLen > 0 && prevD < tasksLen && done >= tasksLen) {
        completions[p.user_id] = { at: Date.now() }
      }
      prevDone[key] = done
    }
  },
  { deep: true }
)

/* ------------------------------------------------------------------ */
/* Leaderboard rows                                                   */
/* ------------------------------------------------------------------ */
const MEDALS = ['var(--sa-gold)', '#c7d3e6', '#e09b62']

export const players = computed(() => {
  const ex = selectedExercise.value
  if (!ex) return []
  const tasksLen = ex.tasks.length || 1
  const nowMs = now.value

  let rows = Object.values(progresses.value)
    .filter((p) => p.exercises?.[ex.uuid] !== undefined)
    .map((p, seq) => {
      const exProgress = p.exercises[ex.uuid]
      const tc = exProgress.tasks_completion || {}
      const done = Object.values(tc).filter((t) => t !== false).length
      const score = exProgress.score ?? 0
      const maxScore = exProgress.max_score ?? 0
      const { name, org } = splitEmail(p.email)

      const status = p.status || {}
      const fireInterval = status.on_fire_last_interval || null
      const fireUntil = fireInterval ? fireInterval[1] * 1000 : 0
      const fireStart = fireInterval ? fireInterval[0] * 1000 : 0
      const onFire = !!status.is_on_fire && fireUntil > nowMs
      const fireBarPct =
        onFire && fireUntil > fireStart
          ? Math.max(0, Math.min(100, Math.round(((fireUntil - nowMs) / (fireUntil - fireStart)) * 100)))
          : 0

      const g = gains[p.user_id]
      const justScored = !!g && nowMs - g.at < JUST_SCORED_MS

      const complete = ex.tasks.length > 0 && done >= ex.tasks.length
      const cmp = completions[p.user_id]
      const justCompleted = !!cmp && nowMs - cmp.at < BURST_MS

      const heatSrc = userActivity.value?.[p.user_id] || []
      const heat = heatSrc.map((v) => ({ bg: heatColor(v) }))

      const tasks = ex.tasks.map((task) => {
        const completion = tc[task.uuid]
        const isDone = completion !== undefined && completion !== false
        const avail = !isDone && taskRequirementMet(tc, task)
        return {
          uuid: task.uuid,
          name: task.name,
          done: isDone,
          avail,
          bg: isDone
            ? 'linear-gradient(180deg,var(--sa-cyan),var(--sa-mint))'
            : avail
              ? 'rgba(var(--sa-cyan-rgb),.12)'
              : 'rgba(var(--sa-cyan-rgb),.04)',
          border: isDone ? 'transparent' : avail ? 'var(--sa-cyan)' : 'rgba(110,130,160,.28)',
          glow: avail ? '0 0 7px rgba(var(--sa-cyan-rgb),.45)' : 'none',
        }
      })

      return {
        id: p.user_id,
        name,
        org,
        active: isActive(p.user_id),
        seq,
        score,
        maxScore,
        done,
        tasksLen,
        doneLabel: `${done}/${tasksLen}`,
        barPct: Math.round((done / tasksLen) * 100),
        isFire: onFire,
        fireBarPct,
        justScored,
        complete,
        justCompleted,
        gain: g?.gain ?? 0,
        heat,
        tasks,
      }
    })

  if (hideInactive.value) rows = rows.filter((r) => r.active)

  // Competitive standing by score, computed independent of the display sort
  // below — so the medal squares and the top-3 leader treatment follow the
  // actual top scorers even when the board is ordered by name / join order.
  const scoreRank = new Map()
  ;[...rows]
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
    .forEach((r, i) => scoreRank.set(r.id, i))

  rows.sort(
    sortByScore.value
      ? (a, b) => b.score - a.score || a.name.localeCompare(b.name)
      : (a, b) => a.name.localeCompare(b.name) || a.seq - b.seq
  )

  return rows.map((r, i) => {
    const sRank = scoreRank.get(r.id)
    const top = sRank < 3 && r.score > 0
    const onFire = r.isFire
    const just = r.justScored
    // Clearing every task is the headline achievement — its gold/mint treatment
    // outranks the on-fire, just-scored and top-3 row states.
    const done100 = r.complete
    return {
      ...r,
      rank: sRank + 1,
      y: i * ROW_HEIGHT,
      opacity: r.active ? 1 : 0.5,
      scoreColor: done100
        ? '#ffd970'
        : onFire
          ? 'var(--sa-fire-mid)'
          : just
            ? 'var(--sa-mint)'
            : top
              ? 'var(--sa-gold)'
              : r.score === 0
                ? 'var(--sa-text-6)'
                : 'var(--sa-text-2)',
      rankFg: top ? 'var(--sa-ink)' : 'var(--sa-text-4)',
      rankBg: top ? MEDALS[sRank] : 'rgba(var(--sa-cyan-rgb),.08)',
      rankBorder: top ? 'transparent' : 'rgba(var(--sa-cyan-rgb),.18)',
      rowBg: done100
        ? 'linear-gradient(90deg,rgba(var(--sa-mint-rgb),.12),rgba(var(--sa-gold-rgb),.07))'
        : just
          ? 'rgba(var(--sa-mint-rgb),.10)'
          : top
            ? 'rgba(var(--sa-gold-rgb),.06)'
            : 'rgba(var(--sa-cyan-rgb),.03)',
      rowBorder: done100
        ? 'rgba(var(--sa-gold-rgb),.5)'
        : top
          ? 'rgba(var(--sa-gold-rgb),.22)'
          : 'rgba(var(--sa-cyan-rgb),.08)',
      glow: done100
        ? '0 0 0 1px rgba(var(--sa-gold-rgb),.4),0 0 24px rgba(var(--sa-mint-rgb),.22)'
        : just
          ? '0 0 0 1px rgba(var(--sa-mint-rgb),.6),0 0 26px rgba(var(--sa-mint-rgb),.28)'
          : 'none',
      rowAnim: done100 ? 'sa-clear 2.6s ease-in-out infinite' : 'none',
    }
  })
})

export const taskLabels = computed(() => (selectedExercise.value?.tasks || []).map((t) => t.name))

/* ------------------------------------------------------------------ */
/* Global progress footer                                             */
/* ------------------------------------------------------------------ */
export const globalProgress = computed(() => {
  const ex = selectedExercise.value
  const usersWithEx = Object.values(progresses.value).filter((p) => p.exercises?.[ex?.uuid])
  let collectiveScore = 0
  let totalCompleted = 0
  for (const p of usersWithEx) {
    const exProgress = p.exercises[ex.uuid]
    collectiveScore += exProgress.score ?? 0
    totalCompleted += Object.values(exProgress.tasks_completion || {}).filter((t) => t !== false).length
  }
  const denom = (usersWithEx.length || 1) * (ex?.tasks.length || 1)
  const globalPct = Math.max(0, Math.min(100, Math.round((totalCompleted / denom) * 100)))
  return { collectiveScore, totalCompleted, globalPct }
})

/* ------------------------------------------------------------------ */
/* Header stats                                                       */
/* ------------------------------------------------------------------ */
export const activeCount = computed(
  () => Object.keys(progresses.value).filter((uid) => isActive(uid)).length
)
export const totalCount = computed(() => userCount.value)

export const clock = computed(() => {
  const d = new Date(now.value)
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
})

export const elapsed = computed(() => {
  const ex = selectedExercise.value
  if (!ex) return '00:00'
  let min = Infinity
  for (const p of Object.values(progresses.value)) {
    const tc = p.exercises?.[ex.uuid]?.tasks_completion
    if (!tc) continue
    for (const c of Object.values(tc)) {
      if (c && c.timestamp) min = Math.min(min, c.timestamp * 1000)
    }
  }
  if (!Number.isFinite(min)) return '00:00'
  return fmtDur(now.value - min)
})

/* ------------------------------------------------------------------ */
/* Hall of Fame podium (top 3, arranged 2nd · 1st · 3rd)              */
/* ------------------------------------------------------------------ */
export const podium = computed(() => {
  const ranked = (userStats.value?.hall_of_fame || []).slice(0, 3)
  // arrange as [2nd, 1st, 3rd] for the classic podium silhouette
  return [1, 0, 2]
    .map((r) => (ranked[r] ? { entry: ranked[r], r } : null))
    .filter(Boolean)
    .map(({ entry, r }) => {
      const first = r === 0
      const { name } = splitEmail(entry.email)
      // Badge: the digits embedded in a participant's name (e.g. trainee07 → 07),
      // falling back to the first two letters when the name has no digits.
      const digits = name.replace(/\D/g, '').slice(0, 2)
      return {
        id: entry.user_id,
        name,
        score: entry.score,
        rank: r + 1,
        initials: digits ? digits.padStart(2, '0') : name.slice(0, 2).toUpperCase(),
        first,
        medal: MEDALS[r],
        glow: first ? 'rgba(var(--sa-gold-rgb),.6)' : 'rgba(199,211,230,.3)',
        scoreColor: MEDALS[r],
        badge: first ? 60 : 42,
        nameSize: first ? 19 : 14,
        scoreSize: first ? 24 : 16,
        badgeAnim: first ? 'sa-gold 2s ease-in-out infinite' : 'sa-pop .5s ease',
        barH: first ? 74 : r === 1 ? 48 : 34,
        barBg: first
          ? 'linear-gradient(180deg,var(--sa-gold),rgba(var(--sa-gold-rgb),.06))'
          : `linear-gradient(180deg,${MEDALS[r]},rgba(199,211,230,.04))`,
      }
    })
})

/* ------------------------------------------------------------------ */
/* Finishers honor roll (everyone who cleared every task)             */
/* ------------------------------------------------------------------ */
// Finish order is by the timestamp of a participant's final completed task;
// "clear time" is measured from the exercise start (the earliest completion
// across all participants — the same anchor used by `elapsed`).
export const finishers = computed(() => {
  const ex = selectedExercise.value
  if (!ex) return []
  const tasksLen = ex.tasks.length
  if (!tasksLen) return []

  let start = Infinity
  const cleared = []
  for (const p of Object.values(progresses.value)) {
    const tc = p.exercises?.[ex.uuid]?.tasks_completion
    if (!tc) continue
    let last = 0
    let count = 0
    for (const c of Object.values(tc)) {
      if (c === false) continue
      count++
      const ts = (c && c.timestamp ? c.timestamp : 0) * 1000
      if (ts) {
        last = Math.max(last, ts)
        start = Math.min(start, ts)
      }
    }
    if (count >= tasksLen) cleared.push({ user_id: p.user_id, email: p.email, finishedAt: last })
  }
  if (!Number.isFinite(start)) start = 0

  cleared.sort((a, b) => a.finishedAt - b.finishedAt || String(a.email).localeCompare(String(b.email)))
  return cleared.map((d, i) => {
    const { name, org } = splitEmail(d.email)
    return {
      id: d.user_id,
      name,
      org,
      rank: i + 1,
      first: i === 0,
      medal: MEDALS[i] || 'var(--sa-text-3)',
      clear: d.finishedAt ? fmtDur(d.finishedAt - start) : '—',
    }
  })
})

/* ------------------------------------------------------------------ */
/* Recent completions ("Just Cleared" — what just got finished)        */
/* ------------------------------------------------------------------ */
// Every completed task across all participants for the selected exercise,
// newest first. Timestamps only (no `now`), so it recomputes on progress
// changes, not every tick; the "ago" label is stamped on top against `now`.
const recentCompletions = computed(() => {
  const ex = selectedExercise.value
  if (!ex) return []
  const taskName = {}
  for (const t of ex.tasks) taskName[t.uuid] = t.name

  const items = []
  for (const p of Object.values(progresses.value)) {
    const tc = p.exercises?.[ex.uuid]?.tasks_completion
    if (!tc) continue
    for (const [taskUuid, c] of Object.entries(tc)) {
      if (!c || c === false || !c.timestamp) continue
      items.push({ user_id: p.user_id, email: p.email, taskUuid, at: c.timestamp * 1000 })
    }
  }
  items.sort((a, b) => b.at - a.at)
  return items.slice(0, RECENT_LIMIT).map((it) => {
    const { name, org } = splitEmail(it.email)
    return {
      id: `${it.user_id}|${it.taskUuid}`,
      taskName: taskName[it.taskUuid] || '—',
      name,
      org,
      at: it.at,
    }
  })
})

// Render-ready rows for the "Just Cleared" strip pinned atop the Live Feed:
// recentCompletions with a live "ago" stamped against the shared clock, the
// most recent flagged `top` for a subtle emphasis. Lives beside the raw feed
// (not in the champion rotation) so "what just happened" is always on screen.
export const justCleared = computed(() => {
  const nowMs = now.value
  return recentCompletions.value.map((it, i) => ({
    id: it.id,
    name: it.name,
    taskName: it.taskName,
    ago: fmtAgo(nowMs - it.at),
    top: i === 0,
  }))
})

// On Fire / Speed / Trophies, plus a fourth Finishers scene once at least one
// participant has cleared everything. Drives the champion slot's rotation.
export const sceneCount = computed(() => (finishers.value.length ? 4 : 3))

/* ------------------------------------------------------------------ */
/* Rotating champion slot (On Fire / Speed Runner / Trophies)         */
/* ------------------------------------------------------------------ */
function buildCard(ranked, fmt, fracOf) {
  const rot = Math.floor(now.value / ROT_MS)
  const leader = ranked[0]
    ? { name: splitEmail(ranked[0].email).name, val: fmt(ranked[0].v), v: ranked[0].v }
    : { name: '—', val: fmt(0), v: 0 }
  const rest = ranked.slice(1, 9)
  const pages = Math.max(1, Math.ceil(rest.length / CHAMPION_PAGE))
  const cur = rot % pages
  const page = rest.slice(cur * CHAMPION_PAGE, cur * CHAMPION_PAGE + CHAMPION_PAGE).map((e, i) => ({
    rank: cur * CHAMPION_PAGE + i + 2,
    name: splitEmail(e.email).name,
    val: fmt(e.v),
    v: e.v,
    frac: Math.max(0, Math.min(100, Math.round(fracOf(e.v) * 100))),
  }))
  return { leader, page, pages, cur }
}

const TROPHY_GLYPHS = {
  grinder: { icon: '⛏', c: 'var(--sa-gold)', rgb: 'var(--sa-gold-rgb)' },
  'bounce-back': { icon: '↺', c: 'var(--sa-mint)', rgb: 'var(--sa-mint-rgb)' },
  messenger: { icon: '✉', c: 'var(--sa-cyan)', rgb: 'var(--sa-cyan-rgb)' },
  spammer: { icon: '◎', c: 'var(--sa-violet)', rgb: 'var(--sa-violet-rgb)' },
}

const DEFAULT_FIRE_WINDOW_SEC = 240

// Heat tiers keyed on fraction of max earnable time-on-fire; named tiers are
// reserved for high performers, < 25% stays the unlabelled "Warm" baseline.
const FIRE_TIERS = [
  {
    min: 0.75,
    label: 'INFERNO',
    fg: 'var(--sa-gold-bright)',
    bar: 'linear-gradient(90deg,var(--sa-fire-deep),#ffb24a 55%,#fff6d8)',
    glow: '0 0 16px rgba(var(--sa-fire-deep-rgb),.85)',
    flameAnim: 'sa-flame .45s infinite',
  },
  {
    min: 0.5,
    label: 'BLAZING',
    fg: '#ff9a5c',
    bar: 'linear-gradient(90deg,#ff7a3c,var(--sa-fire-deep))',
    glow: '0 0 12px rgba(var(--sa-fire-deep-rgb),.6)',
    flameAnim: 'sa-flame .75s infinite',
  },
  {
    min: 0.25,
    label: 'HOT',
    fg: 'var(--sa-fire-mid)',
    bar: 'linear-gradient(90deg,rgba(var(--sa-fire-mid-rgb),.55),var(--sa-fire-mid))',
    glow: '0 0 8px rgba(var(--sa-fire-mid-rgb),.5)',
    flameAnim: 'sa-flame 1.1s infinite',
  },
  {
    min: 0,
    label: '',
    fg: '#e0a06a',
    bar: 'linear-gradient(90deg,rgba(255,178,74,.35),#ffb24a)',
    glow: 'none',
    flameAnim: 'sa-flame 1.7s infinite',
  },
]

function fireTier(fill) {
  return FIRE_TIERS.find((t) => fill >= t.min) || FIRE_TIERS[FIRE_TIERS.length - 1]
}

const SPEED_SEGMENTS = 10

// Speed tiers keyed on the 0-10 Speed Index as a fraction of its ceiling; named
// tiers are reserved for high performers, < 25% stays the unlabelled baseline.
// Mirror of the on-fire heat tiers, in a cyan→white-hot palette with a ⚡ pulse
// that quickens with the tier.
const SPEED_TIERS = [
  {
    min: 0.75,
    label: 'BLITZ',
    fg: '#eaffff',
    seg: '#cdf4ff',
    glow: '0 0 9px rgba(150,235,255,.95)',
    boltAnim: 'sa-bolt .5s infinite',
  },
  {
    min: 0.5,
    label: 'TURBO',
    fg: '#7fe7ff',
    seg: '#4fd8ff',
    glow: '0 0 7px rgba(79,216,255,.7)',
    boltAnim: 'sa-bolt .8s infinite',
  },
  {
    min: 0.25,
    label: 'BRISK',
    fg: 'var(--sa-cyan)',
    seg: 'var(--sa-cyan)',
    glow: '0 0 5px rgba(var(--sa-cyan-rgb),.5)',
    boltAnim: 'sa-bolt 1.2s infinite',
  },
  {
    min: 0,
    label: '',
    fg: '#6fa8c8',
    seg: '#3f7d9c',
    glow: 'none',
    boltAnim: 'sa-bolt 1.8s infinite',
  },
]

function speedTier(frac) {
  return SPEED_TIERS.find((t) => frac >= t.min) || SPEED_TIERS[SPEED_TIERS.length - 1]
}

export const champions = computed(() => {
  const scenes = sceneCount.value
  const scene = currentScene.value % scenes

  // On fire — accumulated time-on-fire (seconds), shown as an m:ss clock.
  // Heat tier = fraction of the max earnable fire (totalTasks × fireWindow).
  const fireWindowSec =
    userStats.value?.settings?.time_on_fire_window_sec || DEFAULT_FIRE_WINDOW_SEC
  const totalFireTasks = active_exercises.value.reduce((s, ex) => s + (ex.tasks?.length || 0), 0)
  const maxEarnableFire = Math.max(1, totalFireTasks * fireWindowSec)
  const fireRanked = (userStats.value?.time_on_fire || [])
    .filter((e) => e.time_on_fire > 0)
    .map((e) => ({ email: e.email, v: e.time_on_fire }))
  const fireCard = buildCard(fireRanked, (v) => fmtClock(v), (v) => v / maxEarnableFire)
  const decorateFire = (item) => {
    const fill = Math.max(0, Math.min(1, item.v / maxEarnableFire))
    return { ...item, fill: Math.round(fill * 100), ...fireTier(fill) }
  }
  const fireLeader = decorateFire(fireCard.leader)
  const fireRest = fireCard.page.map(decorateFire)

  // Speed runner — 0-10 Speed Index = speedrunner_score / perfect-run ceiling.
  // This IS the ranking quantity (monotonic with speedrunner_score), so the
  // column tracks the leaderboard order — unlike the old avg-points-per-task
  // value, which was mislabelled "seconds" and didn't track rank.
  const speedRanked = (userStats.value?.speed_runner || [])
    .filter((e) => (e.speedrunner_score ?? 0) > 0)
    .map((e) => ({ email: e.email, v: e.speedrunner_score }))
  const speedCeiling = Math.max(
    1e-6,
    userStats.value?.settings?.speedrunner_score_ceiling || speedRanked[0]?.v || 1
  )
  const speedIndex = (v) => Math.max(0, Math.min(10, (v / speedCeiling) * 10))
  const speedCard = buildCard(speedRanked, (v) => speedIndex(v).toFixed(1), (v) => v / speedCeiling)
  const decorateSpeed = (item) => {
    const idx = speedIndex(item.v)
    const lit = Math.round(idx)
    return {
      ...item,
      fill: Math.round((idx / 10) * 100),
      segments: Array.from({ length: SPEED_SEGMENTS }, (_, i) => ({ on: i < lit })),
      ...speedTier(idx / 10),
    }
  }
  const speedLeader = decorateSpeed(speedCard.leader)
  const speedRest = speedCard.page.map(decorateSpeed)

  // Trophies — up to 4 holders
  const trophyObj = userStats.value?.trophies || {}
  const trophies = Object.entries(trophyObj).map(([id, t]) => {
    const glyph = TROPHY_GLYPHS[id] || { icon: '🏆', c: 'var(--sa-gold)', rgb: 'var(--sa-gold-rgb)' }
    const winners = (t.users || []).map((u) => splitEmail(u.email).name)
    const holder =
      winners.length === 0 ? '—' : winners.length <= 2 ? winners.join(', ') : `${winners[0]} +${winners.length - 1}`
    return {
      id,
      name: t.metadata?.name || id,
      icon: glyph.icon,
      fg: glyph.c,
      bg: alpha(glyph.rgb, 0.13),
      border: alpha(glyph.rgb, 0.4),
      holder,
    }
  })

  const finishersList = finishers.value

  return {
    scene,
    showFire: scene === 0,
    showSpeed: scene === 1,
    showTrophies: scene === 2,
    showFinishers: scene === 3,
    sceneDots: Array.from({ length: scenes }, (_, i) => ({
      bg: i === scene ? 'var(--sa-text-2)' : 'rgba(120,140,170,.3)',
      w: i === scene ? 18 : 6,
    })),
    slotBorder:
      scene === 0
        ? 'rgba(var(--sa-fire-bright-rgb),.32)'
        : scene === 1
          ? 'rgba(var(--sa-cyan-rgb),.32)'
          : scene === 2
            ? 'rgba(var(--sa-gold-rgb),.26)'
            : 'rgba(var(--sa-mint-rgb),.34)',
    slotBg:
      scene === 0
        ? 'linear-gradient(150deg,rgba(48,20,12,.6),rgba(var(--sa-bg-deep-rgb),.9))'
        : scene === 1
          ? 'linear-gradient(150deg,rgba(12,34,52,.6),rgba(var(--sa-bg-deep-rgb),.9))'
          : scene === 2
            ? 'linear-gradient(180deg,rgba(38,30,14,.45),rgba(var(--sa-bg-deep-rgb),.9))'
            : 'linear-gradient(150deg,rgba(16,42,30,.55),rgba(var(--sa-bg-deep-rgb),.9))',
    fireLeader,
    fireRest,
    speedLeader,
    speedRest,
    trophies,
    finishersCount: finishersList.length,
    finishersLeader: finishersList[0] || null,
    finishersRest: finishersList.slice(1, 5),
  }
})

/* ------------------------------------------------------------------ */
/* Live feed                                                          */
/* ------------------------------------------------------------------ */
function methodStyle(m) {
  if (m === 'GET') return ['var(--sa-cyan)', 'rgba(var(--sa-cyan-rgb),.16)']
  if (m === 'POST') return ['var(--sa-mint)', 'rgba(var(--sa-mint-rgb),.16)']
  if (m === 'DELETE') return ['var(--sa-danger)', 'rgba(var(--sa-danger-rgb),.16)']
  return ['var(--sa-gold)', 'rgba(var(--sa-gold-rgb),.16)'] // PUT / other
}

function isDisplayablePayload(payload) {
  if (typeof payload === 'string') return payload.length > 0
  if (payload === null || payload === undefined) return false
  if (typeof payload === 'object' && Object.keys(payload).length === 0) return false
  return true
}

// Rows in the Live Feed show this many payload lines collapsed; the rest are
// revealed by the per-row expand toggle (see LiveFeed.vue).
export const PAYLOAD_PREVIEW_LINES = 2

function payloadToLines(payload) {
  if (typeof payload === 'string') {
    return { keyCount: 1, isString: true, lines: [{ k: 'raw', v: payload }] }
  }
  const entries = Object.entries(payload)
  return {
    keyCount: entries.length,
    isString: false,
    lines: entries.map(([k, v]) => ({ k, v: typeof v === 'object' ? JSON.stringify(v) : String(v) })),
  }
}

export const feed = computed(() => {
  const su = searchUser.value.trim().toLowerCase()
  const sl = searchUrl.value.trim().toLowerCase()

  let src = notifications.value
  if (su) src = src.filter((e) => (e.user || '').toLowerCase().includes(su))
  if (sl)
    src = src.filter((e) => {
      const inUrl = (e.url || '').toLowerCase().includes(sl)
      const inTool = (e.target_tool || '').toLowerCase().includes(sl)
      const inPayload =
        e.payload && typeof e.payload === 'object'
          ? Object.entries(e.payload).some(([k, v]) => `${k}${v}`.toLowerCase().includes(sl))
          : typeof e.payload === 'string'
            ? e.payload.toLowerCase().includes(sl)
            : false
      return inUrl || inTool || inPayload
    })

  return src.map((e, i) => {
    const isWebhook = e.notification_origin === 'webhook'
    const method = isWebhook ? 'HOOK' : e.http_method
    const [fg, bg] = methodStyle(e.http_method)
    const hasPayload = isDisplayablePayload(e.payload)
    const { name } = splitEmail(e.user)
    const pl = hasPayload ? payloadToLines(e.payload) : { keyCount: 0, isString: false, lines: [] }
    const expandable = pl.lines.length > PAYLOAD_PREVIEW_LINES || pl.lines.some((l) => l.v.length > 60)
    return {
      id: e.id,
      user: name,
      method,
      methodFg: isWebhook ? 'var(--sa-violet)' : fg,
      methodBg: isWebhook ? 'rgba(var(--sa-violet-rgb),.16)' : bg,
      url: isWebhook ? e.target_tool : e.url,
      rowBg: i === 0 ? 'rgba(var(--sa-cyan-rgb),.06)' : 'rgba(var(--sa-cyan-rgb),.02)',
      rowBorder: i === 0 ? 'rgba(var(--sa-cyan-rgb),.18)' : 'rgba(var(--sa-cyan-rgb),.06)',
      hasPayload,
      keyCount: pl.keyCount,
      payloadLines: pl.lines,
      payloadIsString: pl.isString,
      expandable,
    }
  })
})

export const feedEmpty = computed(() => feed.value.length === 0)
export const messages = notificationCounter
export const apiMessages = notificationAPICounter

/* ------------------------------------------------------------------ */
/* 20-min activity timeline                                           */
/* ------------------------------------------------------------------ */
export const timeline = computed(() => {
  // One bar per history bucket (5s each), so the chart advances in lockstep with
  // the data — each update shifts every bar one slot left, a clean 20-min slide.
  const buckets = Array.from(notificationHistory.value || [])
  const tlMax = Math.max(1, ...buckets)
  // Soft bars: a top-down cyan gradient per bucket, a faint stub for empty ones,
  // and a brighter glowing bar at the leading (now) edge.
  const bars = buckets.map((v, i) => {
    const isNow = i === buckets.length - 1
    return {
      h: Math.round((v / tlMax) * 100),
      bg: isNow
        ? 'linear-gradient(180deg,var(--sa-cyan),rgba(var(--sa-cyan-rgb),.45))'
        : v === 0
          ? 'rgba(var(--sa-cyan-rgb),.1)'
          : 'linear-gradient(180deg,rgba(var(--sa-cyan-rgb),.85),rgba(var(--sa-cyan-rgb),.22))',
      glow: isNow ? '0 0 7px rgba(var(--sa-cyan-rgb),.75)' : 'none',
    }
  })
  return {
    bars,
    tlNow: buckets[buckets.length - 1] || 0,
    tlMax,
    windowMin: notificationHistoryConfig.value?.buffer_timestamp_min || 20,
  }
})
