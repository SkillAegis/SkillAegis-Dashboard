<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { registerTimerCallback, unregisterTimerCallback } from '@/utils.js'
import { userAuthenticated, setCompletedState } from '@/socket'
import CompletionBurst from './CompletionBurst.vue'
import {
  players,
  taskLabels,
  globalProgress,
  sortByScore,
  autoPaginate,
  selectedExercise,
  ROW_HEIGHT,
} from './dashboardState.js'

// Admin-only: click a task square to mark it completed / incomplete for that user.
function toggleTask(player, task) {
  if (!userAuthenticated.value || !selectedExercise.value) return
  // setCompletedState toggles based on the current completion state (task.done).
  setCompletedState(task.done, player.id, selectedExercise.value.uuid, task.uuid)
}

// Top room inside the (clipped) rows container so the "+NN" score pop, which
// floats above a row, isn't cut off for the row at the top of the board.
const PAD_TOP = 18

const rowsRef = ref(null)
const rowsPerPage = ref(14)
const currentPage = ref(0)
let timerID = null
let resizeObserver = null

const sortLabel = computed(() => (sortByScore.value ? 'RANKED BY SCORE' : 'JOIN ORDER'))

const pageCount = computed(() => {
  if (!autoPaginate.value) return 1
  return Math.max(1, Math.ceil(players.value.length / rowsPerPage.value))
})

const pageOffset = computed(() => (autoPaginate.value ? currentPage.value * rowsPerPage.value : 0))

const boardHeight = computed(
  () => (autoPaginate.value ? rowsPerPage.value : Math.max(players.value.length, 1)) * ROW_HEIGHT
)

function measure() {
  nextTick(() => {
    const el = rowsRef.value
    if (!el) return
    const h = el.getBoundingClientRect().height - PAD_TOP
    if (h > 0) rowsPerPage.value = Math.max(1, Math.floor(h / ROW_HEIGHT))
  })
}

function rotatePage() {
  if (!autoPaginate.value) {
    currentPage.value = 0
    return
  }
  currentPage.value = (currentPage.value + 1) % pageCount.value
}

function inPage(index) {
  if (!autoPaginate.value) return true
  const start = currentPage.value * rowsPerPage.value
  return index >= start && index < start + rowsPerPage.value
}

onMounted(() => {
  measure()
  setTimeout(measure, 250)
  timerID = registerTimerCallback(rotatePage)
  if (window.ResizeObserver && rowsRef.value) {
    resizeObserver = new ResizeObserver(() => measure())
    resizeObserver.observe(rowsRef.value)
  } else {
    window.addEventListener('resize', measure)
  }
})
onUnmounted(() => {
  unregisterTimerCallback(timerID)
  if (resizeObserver) resizeObserver.disconnect()
  else window.removeEventListener('resize', measure)
})
</script>

<template>
  <section class="sa-board" data-sa-leaderboard>
    <div style="display:flex;align-items:center;gap:12px;padding:11px 22px 9px;">
      <span style="font-size:17px;font-weight:700;letter-spacing:2px;color:#eaf3ff;">LIVE LEADERBOARD</span>
      <span class="sa-mono" style="font-size:12px;color:#5f86b0;letter-spacing:1px;">{{ sortLabel }}</span>
    </div>

    <!-- column headers -->
    <div style="display:flex;align-items:flex-end;gap:14px;padding:0 22px 9px;border-bottom:1px solid rgba(56,210,255,.1);">
      <div class="sa-mono" style="width:46px;text-align:center;font-size:11px;color:#46607f;">#</div>
      <div class="sa-mono" style="width:236px;font-size:11px;letter-spacing:1px;color:#46607f;">PARTICIPANT · ACTIVITY</div>
      <div style="flex:1;display:flex;gap:6px;">
        <div
          v-for="(t, i) in taskLabels"
          :key="i"
          class="sa-mono"
          style="flex:1;text-align:center;font-size:10px;line-height:1.15;color:#46607f;letter-spacing:.3px;height:26px;display:flex;align-items:flex-end;justify-content:center;overflow:hidden;"
          :title="t"
        >{{ t }}</div>
      </div>
      <div class="sa-mono" style="width:150px;text-align:center;font-size:11px;color:#46607f;letter-spacing:1px;">PROGRESS</div>
      <div class="sa-mono" style="width:78px;text-align:right;font-size:11px;color:#46607f;letter-spacing:1px;">SCORE</div>
    </div>

    <!-- rows -->
    <div
      ref="rowsRef"
      :style="{
        position: 'relative',
        flex: '1',
        minHeight: '0',
        overflowX: 'hidden',
        overflowY: autoPaginate ? 'hidden' : 'auto',
        margin: '0 14px 0',
        paddingTop: PAD_TOP + 'px',
      }"
    >
      <div v-if="!selectedExercise" class="sa-empty">No exercise selected — pick one in the admin panel.</div>
      <div v-else-if="players.length === 0" class="sa-empty">No participant activity yet.</div>

      <div :style="{ position: 'relative', width: '100%', height: boardHeight + 'px' }">
        <div
          v-for="(p, idx) in players"
          :key="p.id"
          :style="{
            position: 'absolute',
            left: '0',
            right: '0',
            top: '0',
            height: ROW_HEIGHT + 'px',
            display: 'flex',
            alignItems: 'center',
            zIndex: p.justCompleted ? 30 : p.justScored ? 20 : 1,
            opacity: inPage(idx) ? p.opacity : 0,
            pointerEvents: inPage(idx) ? 'auto' : 'none',
            transform: `translateY(${(idx - pageOffset) * ROW_HEIGHT}px)`,
            transition:
              'transform .85s cubic-bezier(.6,.05,.2,1), box-shadow .5s ease, opacity .5s ease',
          }"
        >
          <div
            style="display:flex;align-items:center;gap:14px;width:100%;height:50px;padding:0 8px 0 0;border-radius:12px;"
            :style="{ border: `1px solid ${p.rowBorder}`, background: p.rowBg, boxShadow: p.glow, animation: p.rowAnim }"
          >
            <!-- rank -->
            <div style="width:46px;display:flex;align-items:center;justify-content:center;">
              <div
                class="sa-mono"
                style="width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;"
                :style="{ color: p.rankFg, background: p.rankBg, border: `1px solid ${p.rankBorder}` }"
              >{{ p.rank }}</div>
            </div>

            <!-- name + heatmap -->
            <div style="width:236px;display:flex;flex-direction:column;gap:3px;min-width:0;">
              <div style="display:flex;align-items:center;gap:7px;min-width:0;">
                <span v-if="p.complete" class="sa-medal" title="Cleared every task">🏅</span>
                <span v-if="p.isFire" class="sa-flame" style="font-size:15px;line-height:1;filter:drop-shadow(0 0 5px rgba(255,120,60,.8));">🔥</span>
                <div style="min-width:0;flex:1;">
                  <div style="font-weight:600;font-size:15px;color:#eaf3ff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.1;">{{ p.name }}</div>
                  <div class="sa-mono" style="font-size:9px;color:#5f86b0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ p.org }}</div>
                </div>
              </div>
              <div v-if="p.isFire" style="height:4px;border-radius:3px;background:rgba(255,120,60,.16);overflow:hidden;margin:0 16px 0 0;">
                <div :style="{ height: '100%', width: p.fireBarPct + '%', borderRadius: '3px', background: 'linear-gradient(90deg,#ffb24a,#ff5d3c)', transition: 'width 1s linear', boxShadow: '0 0 8px rgba(255,120,60,.7)' }"></div>
              </div>
              <div style="display:flex;gap:2px;height:8px;padding:0 16px 0 2px;">
                <div v-for="(c, ci) in p.heat" :key="ci" :style="{ flex: '1', borderRadius: '2px', background: c.bg }"></div>
              </div>
            </div>

            <!-- task strip: fuses into one bar once every task is cleared, but
                 admins keep the clickable per-task squares to toggle completion -->
            <div style="flex:1;display:flex;align-items:stretch;height:24px;">
              <div v-if="p.complete && !userAuthenticated" class="sa-clearbar" style="flex:1;position:relative;border-radius:5px;overflow:hidden;background:linear-gradient(90deg,#5be39a,#36d2ff 55%,#ffcd5b);box-shadow:0 0 12px rgba(91,227,154,.4);">
                <span class="sa-clearbar-shine"></span>
              </div>
              <div v-else style="flex:1;display:flex;gap:5px;align-items:stretch;">
                <div
                  v-for="(t, ti) in p.tasks"
                  :key="ti"
                  class="sa-task"
                  :class="{ clickable: userAuthenticated }"
                  :title="userAuthenticated ? `${t.name} — click to mark ${t.done ? 'incomplete' : 'completed'}` : t.name"
                  style="flex:1;position:relative;border-radius:5px;"
                  :style="{ background: t.bg, border: `1px solid ${t.border}`, boxShadow: t.glow }"
                  @click="toggleTask(p, t)"
                >
                  <span v-if="t.avail" class="sa-blink" style="position:absolute;top:50%;left:50%;width:5px;height:5px;margin:-2.5px 0 0 -2.5px;border-radius:50%;background:#36d2ff;"></span>
                </div>
              </div>
            </div>

            <!-- progress -->
            <div style="width:150px;display:flex;align-items:center;gap:9px;">
              <div v-if="p.complete" class="sa-cleared-pill sa-mono">✓ CLEARED</div>
              <template v-else>
                <div style="flex:1;height:9px;border-radius:6px;background:rgba(56,210,255,.1);overflow:hidden;position:relative;">
                  <div :style="{ height: '100%', width: p.barPct + '%', borderRadius: '6px', background: 'linear-gradient(90deg,#2b7bd6,#36d2ff,#5be39a)', transition: 'width .85s ease', boxShadow: '0 0 12px rgba(54,210,255,.45)' }"></div>
                </div>
                <span class="sa-mono" style="font-size:11px;color:#7e98ba;width:34px;">{{ p.doneLabel }}</span>
              </template>
            </div>

            <!-- score -->
            <div style="width:78px;text-align:right;position:relative;">
              <span class="sa-mono" style="font-size:21px;font-weight:800;transition:color .4s;" :style="{ color: p.scoreColor }">{{ p.score }}</span>
              <span v-if="p.justScored && p.gain > 0" class="sa-rise sa-mono" style="position:absolute;right:0;top:-19px;font-size:16px;font-weight:800;color:#5be39a;text-shadow:0 0 10px rgba(91,227,154,.6);">+{{ p.gain }}</span>
            </div>
          </div>
          <CompletionBurst v-if="p.justCompleted" />
        </div>
      </div>
    </div>

    <!-- global progress footer -->
    <div style="display:flex;align-items:center;gap:22px;padding:9px 22px;border-top:1px solid rgba(56,210,255,.12);background:rgba(8,14,24,.5);">
      <span style="font-size:13px;font-weight:700;letter-spacing:1.5px;color:#9fb4d0;">GLOBAL PROGRESS</span>
      <div style="flex:1;height:12px;border-radius:8px;background:rgba(56,210,255,.1);overflow:hidden;position:relative;">
        <div :style="{ height: '100%', width: globalProgress.globalPct + '%', borderRadius: '8px', background: 'linear-gradient(90deg,#2b7bd6,#36d2ff 55%,#5be39a)', transition: 'width 1s ease', boxShadow: '0 0 16px rgba(54,210,255,.4)' }"></div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;"><span class="sa-mono" style="font-size:12px;color:#5f86b0;">COLLECTIVE</span><span class="sa-mono" style="font-size:22px;font-weight:800;color:#36d2ff;">{{ globalProgress.collectiveScore }}</span></div>
      <div style="display:flex;align-items:center;gap:8px;"><span class="sa-mono" style="font-size:12px;color:#5f86b0;">TASKS</span><span class="sa-mono" style="font-size:22px;font-weight:800;color:#5be39a;">{{ globalProgress.totalCompleted }}</span></div>
    </div>
  </section>
</template>

<style scoped>
.sa-board {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(56, 210, 255, 0.14);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(14, 22, 38, 0.92), rgba(9, 15, 26, 0.92));
  overflow: hidden;
  min-height: 0;
}
.sa-board:fullscreen {
  border: none;
  border-radius: 0;
  background: #070b14;
}
.sa-task {
  transition: filter 0.15s ease, transform 0.1s ease;
}
.sa-task.clickable {
  cursor: pointer;
}
.sa-task.clickable:hover {
  filter: brightness(1.35);
  transform: scaleY(1.18);
}
.sa-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #46607f;
  z-index: 1;
}
/* all-clear: a gold seal by the name, a pill in the progress column, and a
   slow sheen sweeping the fused task bar */
.sa-medal {
  flex: none;
  font-size: 15px;
  line-height: 1;
  filter: drop-shadow(0 0 5px rgba(255, 205, 91, 0.8));
}
.sa-cleared-pill {
  flex: 1;
  text-align: center;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1px;
  color: #ffe08a;
  padding: 4px 0;
  border-radius: 999px;
  border: 1px solid rgba(255, 205, 91, 0.55);
  background: rgba(255, 205, 91, 0.1);
  box-shadow: 0 0 12px rgba(255, 205, 91, 0.2);
}
.sa-clearbar-shine {
  position: absolute;
  top: 0;
  left: -40%;
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent);
  animation: sa-shine 2.8s ease-in-out infinite;
}
@keyframes sa-shine {
  0% {
    left: -40%;
  }
  60%,
  100% {
    left: 120%;
  }
}
</style>
