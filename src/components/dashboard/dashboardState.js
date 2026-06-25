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
/* Helpers                                                            */
/* ------------------------------------------------------------------ */
function splitEmail(email) {
  const [local, domain] = String(email ?? '').split('@')
  return { name: local || String(email ?? ''), org: domain ? '@' + domain : '' }
}

function heatColor(v) {
  if (v <= 0) return 'rgba(56,210,255,.07)'
  if (v <= 1) return 'rgba(56,210,255,.28)'
  if (v <= 2) return 'rgba(56,210,255,.55)'
  return '#36d2ff'
}

function tint(hex, a) {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
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
const gains = reactive({})

watch(
  () => progresses.value,
  (np) => {
    const ex = selectedExercise.value
    if (!ex) return
    for (const p of Object.values(np)) {
      const exProgress = p.exercises?.[ex.uuid]
      if (!exProgress) continue
      const key = `${p.user_id}|${ex.uuid}`
      const score = exProgress.score ?? 0
      const prev = prevScores[key]
      if (prev !== undefined && score > prev) {
        gains[p.user_id] = { gain: score - prev, at: Date.now() }
      }
      prevScores[key] = score
    }
  },
  { deep: true }
)

/* ------------------------------------------------------------------ */
/* Leaderboard rows                                                   */
/* ------------------------------------------------------------------ */
const MEDALS = ['#ffcd5b', '#c7d3e6', '#e09b62']

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
            ? 'linear-gradient(180deg,#36d2ff,#5be39a)'
            : avail
              ? 'rgba(56,210,255,.12)'
              : 'rgba(56,210,255,.04)',
          border: isDone ? 'transparent' : avail ? '#36d2ff' : 'rgba(110,130,160,.28)',
          glow: avail ? '0 0 7px rgba(54,210,255,.45)' : 'none',
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
        gain: g?.gain ?? 0,
        heat,
        tasks,
      }
    })

  if (hideInactive.value) rows = rows.filter((r) => r.active)

  rows.sort(
    sortByScore.value
      ? (a, b) => b.score - a.score || a.name.localeCompare(b.name)
      : (a, b) => a.seq - b.seq || a.name.localeCompare(b.name)
  )

  return rows.map((r, rank) => {
    const top = sortByScore.value && rank < 3 && r.score > 0
    const onFire = r.isFire
    const just = r.justScored
    return {
      ...r,
      rank: rank + 1,
      y: rank * ROW_HEIGHT,
      opacity: r.active ? 1 : 0.5,
      scoreColor: onFire
        ? '#ff8a3c'
        : just
          ? '#5be39a'
          : top
            ? '#ffcd5b'
            : r.score === 0
              ? '#46607f'
              : '#cfe3ff',
      rankFg: top ? '#0a1322' : '#7e98ba',
      rankBg: top ? MEDALS[rank] : 'rgba(56,210,255,.08)',
      rankBorder: top ? 'transparent' : 'rgba(56,210,255,.18)',
      rowBg: onFire
        ? 'rgba(255,120,60,.09)'
        : just
          ? 'rgba(91,227,154,.10)'
          : top
            ? 'rgba(255,205,91,.06)'
            : 'rgba(56,210,255,.03)',
      rowBorder: onFire
        ? 'rgba(255,140,70,.4)'
        : top
          ? 'rgba(255,205,91,.22)'
          : 'rgba(56,210,255,.08)',
      glow: onFire
        ? '0 0 0 1px rgba(255,140,70,.5),0 0 28px rgba(255,120,60,.3)'
        : just
          ? '0 0 0 1px rgba(91,227,154,.6),0 0 26px rgba(91,227,154,.28)'
          : 'none',
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
      return {
        id: entry.user_id,
        name,
        score: entry.score,
        rank: r + 1,
        initials: name.replace(/\D/g, '').slice(0, 2).padStart(2, '0') || name.slice(0, 2).toUpperCase(),
        first,
        medal: MEDALS[r],
        glow: first ? 'rgba(255,205,91,.6)' : 'rgba(199,211,230,.3)',
        scoreColor: MEDALS[r],
        badge: first ? 60 : 42,
        nameSize: first ? 19 : 14,
        scoreSize: first ? 24 : 16,
        badgeAnim: first ? 'sa-gold 2s ease-in-out infinite' : 'sa-pop .5s ease',
        barH: first ? 74 : r === 1 ? 48 : 34,
        barBg: first
          ? 'linear-gradient(180deg,#ffcd5b,rgba(255,205,91,.06))'
          : `linear-gradient(180deg,${MEDALS[r]},rgba(199,211,230,.04))`,
      }
    })
})

/* ------------------------------------------------------------------ */
/* Rotating champion slot (On Fire / Speed Runner / Trophies)         */
/* ------------------------------------------------------------------ */
function buildCard(ranked, fmt, fracOf) {
  const rot = Math.floor(now.value / ROT_MS)
  const leader = ranked[0]
    ? { name: splitEmail(ranked[0].email).name, val: fmt(ranked[0].v) }
    : { name: '—', val: fmt(0) }
  const rest = ranked.slice(1, 9)
  const pages = Math.max(1, Math.ceil(rest.length / CHAMPION_PAGE))
  const cur = rot % pages
  const page = rest.slice(cur * CHAMPION_PAGE, cur * CHAMPION_PAGE + CHAMPION_PAGE).map((e, i) => ({
    rank: cur * CHAMPION_PAGE + i + 2,
    name: splitEmail(e.email).name,
    val: fmt(e.v),
    frac: Math.max(0, Math.min(100, Math.round(fracOf(e.v) * 100))),
  }))
  return { leader, page, pages, cur }
}

const TROPHY_GLYPHS = {
  grinder: { icon: '⛏', c: '#ffcd5b' },
  'bounce-back': { icon: '↺', c: '#5be39a' },
  messenger: { icon: '✉', c: '#36d2ff' },
  spammer: { icon: '◎', c: '#b08bff' },
}

export const champions = computed(() => {
  const scene = Math.floor(now.value / SCENE_MS) % 3

  // On fire — minutes spent on fire
  const fireRanked = (userStats.value?.time_on_fire || [])
    .filter((e) => e.time_on_fire > 0)
    .map((e) => ({ email: e.email, v: e.time_on_fire / 60 }))
  const fireMax = fireRanked[0]?.v || 1
  const fireCard = buildCard(fireRanked, (v) => v.toFixed(1), (v) => v / fireMax)

  // Speed runner — average seconds per task (lower is better)
  const speedRanked = (userStats.value?.speed_runner || []).map((e) => ({
    email: e.email,
    v: e.avg_time_per_tasks ?? 0,
  }))
  const speedBest = speedRanked[0]?.v || 1
  const speedCard = buildCard(speedRanked, (v) => Math.round(v), (v) => (v ? speedBest / v : 0))

  // Trophies — up to 4 holders
  const trophyObj = userStats.value?.trophies || {}
  const trophies = Object.entries(trophyObj).map(([id, t]) => {
    const glyph = TROPHY_GLYPHS[id] || { icon: '🏆', c: '#ffcd5b' }
    const winners = (t.users || []).map((u) => splitEmail(u.email).name)
    const holder =
      winners.length === 0 ? '—' : winners.length <= 2 ? winners.join(', ') : `${winners[0]} +${winners.length - 1}`
    return {
      id,
      name: t.metadata?.name || id,
      icon: glyph.icon,
      fg: glyph.c,
      bg: tint(glyph.c, 0.13),
      border: tint(glyph.c, 0.4),
      holder,
    }
  })

  return {
    scene,
    showFire: scene === 0,
    showSpeed: scene === 1,
    showTrophies: scene === 2,
    sceneDots: [0, 1, 2].map((i) => ({
      bg: i === scene ? '#cfe3ff' : 'rgba(120,140,170,.3)',
      w: i === scene ? 18 : 6,
    })),
    slotBorder:
      scene === 0 ? 'rgba(255,140,70,.32)' : scene === 1 ? 'rgba(54,210,255,.32)' : 'rgba(255,205,91,.26)',
    slotBg:
      scene === 0
        ? 'linear-gradient(150deg,rgba(48,20,12,.6),rgba(14,18,30,.9))'
        : scene === 1
          ? 'linear-gradient(150deg,rgba(12,34,52,.6),rgba(14,18,30,.9))'
          : 'linear-gradient(180deg,rgba(38,30,14,.45),rgba(14,18,30,.9))',
    fireLeader: fireCard.leader,
    fireRest: fireCard.page,
    speedLeader: speedCard.leader,
    speedRest: speedCard.page,
    trophies,
  }
})

/* ------------------------------------------------------------------ */
/* Live feed                                                          */
/* ------------------------------------------------------------------ */
function methodStyle(m) {
  if (m === 'GET') return ['#36d2ff', 'rgba(54,210,255,.16)']
  if (m === 'POST') return ['#5be39a', 'rgba(91,227,154,.16)']
  if (m === 'DELETE') return ['#ff6b6b', 'rgba(255,107,107,.16)']
  return ['#ffcd5b', 'rgba(255,205,91,.16)'] // PUT / other
}

function isDisplayablePayload(payload) {
  if (typeof payload === 'string') return payload.length > 0
  if (payload === null || payload === undefined) return false
  if (typeof payload === 'object' && Object.keys(payload).length === 0) return false
  return true
}

function payloadToLines(payload) {
  if (typeof payload === 'string') {
    return { keyCount: 1, lines: [{ k: 'raw', v: payload }] }
  }
  const entries = Object.entries(payload)
  return {
    keyCount: entries.length,
    lines: entries.slice(0, 2).map(([k, v]) => ({ k, v: typeof v === 'object' ? JSON.stringify(v) : String(v) })),
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
    const pl = hasPayload ? payloadToLines(e.payload) : { keyCount: 0, lines: [] }
    return {
      id: e.id,
      user: name,
      method,
      methodFg: isWebhook ? '#b08bff' : fg,
      methodBg: isWebhook ? 'rgba(176,139,255,.16)' : bg,
      url: isWebhook ? e.target_tool : e.url,
      rowBg: i === 0 ? 'rgba(54,210,255,.06)' : 'rgba(56,210,255,.02)',
      rowBorder: i === 0 ? 'rgba(54,210,255,.18)' : 'rgba(56,210,255,.06)',
      hasPayload,
      keyCount: pl.keyCount,
      payloadLines: pl.lines,
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
  const buckets = Array.from(notificationHistory.value || [])
  const tlMax = Math.max(1, ...buckets)
  const bars = buckets.map((v, i) => ({
    h: Math.round((v / tlMax) * 100),
    bg: i === buckets.length - 1 ? '#36d2ff' : v === 0 ? 'rgba(56,210,255,.08)' : 'rgba(54,210,255,.45)',
  }))
  return {
    bars,
    tlNow: buckets[buckets.length - 1] || 0,
    tlMax,
    windowMin: notificationHistoryConfig.value?.buffer_timestamp_min || 20,
  }
})
