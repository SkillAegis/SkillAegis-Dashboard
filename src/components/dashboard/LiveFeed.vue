<script setup>
import { ref, reactive, watch, nextTick, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  feed, feedEmpty, messages, apiMessages, timeline, searchUser, searchUrl, justCleared, PAYLOAD_PREVIEW_LINES,
  verboseMode, apiQueryOnly, toggleVerbose, toggleApiQuery, userAuthenticated,
} from './dashboardState.js'

// Feed options menu (hamburger) — holds the server-side feed filters and is
// the home for future feed-scoped controls. Closes on outside-click / Escape.
const menuRef = ref(null)
const menuOpen = ref(false)
const filtersActive = computed(() => verboseMode.value || apiQueryOnly.value)
function toggleMenu() {
  menuOpen.value = !menuOpen.value
}
function onDocClick(e) {
  if (menuOpen.value && menuRef.value && !menuRef.value.contains(e.target)) menuOpen.value = false
}
function onKey(e) {
  if (e.key === 'Escape') menuOpen.value = false
}
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})

// Per-row payload expand state, keyed by stable feed id so a row stays expanded
// across re-renders (and the per-second relative-time ticks elsewhere).
const expandedRows = reactive(new Set())
const isExpanded = (id) => expandedRows.has(id)
function toggleRow(id) {
  if (expandedRows.has(id)) expandedRows.delete(id)
  else expandedRows.add(id)
}

// Animate the activity timeline as a horizontal slide rather than per-bar height
// growth. Each update shifts the series one bucket left, so we render the new
// data, snap the strip one bar-width to the right (lining it up with the previous
// frame), then ease it back to 0 — reading as a clean one-bar slide.
const slide = ref('translateX(0)')
const sliding = ref(false)

watch(
  () => timeline.value.bars,
  async () => {
    const n = timeline.value.bars.length
    if (!n) return
    sliding.value = false
    slide.value = `translateX(${100 / n}%)`
    await nextTick()
    requestAnimationFrame(() => {
      sliding.value = true
      slide.value = 'translateX(0)'
    })
  }
)
</script>

<template>
  <div class="sa-feed">
    <div style="display:flex;align-items:center;gap:12px;padding:11px 16px 9px;border-bottom:1px solid rgba(var(--sa-cyan-rgb),.1);">
      <span style="font-size:14px;font-weight:700;letter-spacing:1.5px;color:var(--sa-text-2);">LIVE FEED</span>
      <span class="sa-blink" style="width:8px;height:8px;border-radius:50%;background:var(--sa-mint);box-shadow:0 0 8px var(--sa-mint);"></span>
      <div style="flex:1;"></div>
      <div style="display:flex;align-items:center;gap:7px;padding:5px 10px;border-radius:8px;background:rgba(var(--sa-cyan-rgb),.1);border:1px solid rgba(var(--sa-cyan-rgb),.2);">
        <span class="sa-mono" style="font-size:10px;color:var(--sa-text-4);">MESSAGES</span>
        <span class="sa-mono" style="font-size:14px;font-weight:800;color:var(--sa-cyan);">{{ messages }}</span>
      </div>
      <div style="display:flex;align-items:center;gap:7px;padding:5px 10px;border-radius:8px;background:rgba(var(--sa-mint-rgb),.1);border:1px solid rgba(var(--sa-mint-rgb),.2);">
        <span style="font-size:11px;">🔒</span><span class="sa-mono" style="font-size:10px;color:var(--sa-text-4);">API</span>
        <span class="sa-mono" style="font-size:14px;font-weight:800;color:var(--sa-mint);">{{ apiMessages }}</span>
      </div>

      <!-- feed options menu -->
      <div ref="menuRef" class="sa-menu-wrap">
        <button
          type="button"
          class="sa-menu-btn"
          :class="{ open: menuOpen, active: filtersActive }"
          aria-label="Feed options"
          :aria-expanded="menuOpen"
          @click="toggleMenu"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
          <span v-if="filtersActive" class="sa-menu-dot"></span>
        </button>

        <div v-if="menuOpen" class="sa-menu" @click.stop>
          <div class="sa-menu-title sa-mono">FEED OPTIONS</div>

          <button
            type="button"
            class="sa-menu-item"
            :class="{ disabled: !userAuthenticated }"
            :disabled="!userAuthenticated"
            :title="!userAuthenticated ? 'Log in (admin) to change feed filters' : ''"
            @click="toggleVerbose"
          >
            <span class="sa-switch" :class="{ on: verboseMode }"><span class="sa-switch-knob"></span></span>
            <span class="sa-menu-text">
              <span class="sa-menu-label">Verbose mode</span>
              <span class="sa-menu-hint">Show all traffic, unfiltered</span>
            </span>
          </button>

          <button
            type="button"
            class="sa-menu-item"
            :class="{ disabled: !userAuthenticated }"
            :disabled="!userAuthenticated"
            :title="!userAuthenticated ? 'Log in (admin) to change feed filters' : ''"
            @click="toggleApiQuery"
          >
            <span class="sa-switch sa-switch--mint" :class="{ on: apiQueryOnly }"><span class="sa-switch-knob"></span></span>
            <span class="sa-menu-text">
              <span class="sa-menu-label">🔒 API queries only</span>
              <span class="sa-menu-hint">Hide non-API requests</span>
            </span>
          </button>

          <div v-if="!userAuthenticated" class="sa-menu-foot sa-mono">Admin login required</div>
        </div>
      </div>
    </div>

    <!-- Just Cleared — task completions pinned above the raw stream: the
         curated "what just happened" companion to the HTTP feed below. -->
    <div style="padding:10px 16px 9px;border-bottom:1px solid rgba(var(--sa-violet-rgb),.16);background:rgba(var(--sa-violet-rgb),.045);">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
        <span style="font-size:13px;filter:drop-shadow(0 0 5px rgba(var(--sa-violet-rgb),.7));">🕒</span>
        <span style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#cbb8ff;">JUST CLEARED</span>
        <span class="sa-mono" style="font-size:10px;color:var(--sa-text-5);">· tasks completed, newest first</span>
      </div>
      <div v-if="justCleared.length === 0" class="sa-mono" style="font-size:11px;color:var(--sa-text-6);padding:3px 0 2px;">No completions yet</div>
      <div v-else style="display:flex;flex-direction:column;gap:4px;">
        <div v-for="c in justCleared" :key="c.id" class="sa-rise" style="display:flex;align-items:center;gap:9px;">
          <span style="flex:none;width:6px;height:6px;border-radius:50%;" :style="{ background: c.top ? 'var(--sa-violet)' : 'rgba(var(--sa-violet-rgb),.4)', boxShadow: c.top ? '0 0 6px rgba(var(--sa-violet-rgb),.7)' : 'none' }"></span>
          <span style="font-size:12px;font-weight:600;flex:none;width:84px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" :style="{ color: c.top ? '#fff' : '#d8d0ea' }">{{ c.name }}</span>
          <span style="font-size:12px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" :style="{ color: c.top ? '#c5b3ee' : '#9d8fc4' }">{{ c.taskName }}</span>
          <span class="sa-mono" style="font-size:11px;font-weight:700;flex:none;" :style="{ color: c.top ? 'var(--sa-violet)' : '#b9a6e6' }" title="Time since completion">{{ c.ago }}</span>
        </div>
      </div>
    </div>

    <!-- activity timeline -->
    <div style="padding:9px 16px 8px;border-bottom:1px solid rgba(var(--sa-cyan-rgb),.08);">
      <div style="display:flex;align-items:flex-end;gap:14px;">
        <span class="sa-mono" style="font-size:9px;color:var(--sa-text-6);white-space:nowrap;">-{{ timeline.windowMin }} min</span>
        <div style="flex:1;height:38px;overflow:hidden;">
          <div :style="{ display: 'flex', alignItems: 'flex-end', gap: '1px', height: '100%', willChange: 'transform', transform: slide, transition: sliding ? 'transform .5s ease-out' : 'none' }">
            <div v-for="(b, i) in timeline.bars" :key="i" :style="{ flex: '1', height: b.h + '%', minHeight: '2px', borderRadius: '1.5px 1.5px 0 0', background: b.bg, boxShadow: b.glow }"></div>
          </div>
        </div>
        <div style="text-align:right;min-width:54px;">
          <div class="sa-mono" style="font-size:10px;color:var(--sa-text-4);">now <span style="color:var(--sa-cyan);font-weight:800;">{{ timeline.tlNow }}</span></div>
          <div class="sa-mono" style="font-size:10px;color:var(--sa-text-4);">max <span style="color:var(--sa-text-3);font-weight:800;">{{ timeline.tlMax }}</span></div>
        </div>
      </div>
    </div>

    <!-- search -->
    <div style="display:flex;gap:10px;padding:9px 16px;">
      <div style="flex:1;display:flex;align-items:center;gap:8px;padding:7px 11px;border-radius:9px;background:rgba(var(--sa-bg-rgb),.7);border:1px solid rgba(var(--sa-cyan-rgb),.16);">
        <span style="font-size:12px;color:var(--sa-text-6);">⌕</span>
        <input v-model="searchUser" placeholder="Find user" class="sa-input" />
      </div>
      <div style="flex:1.4;display:flex;align-items:center;gap:8px;padding:7px 11px;border-radius:9px;background:rgba(var(--sa-bg-rgb),.7);border:1px solid rgba(var(--sa-cyan-rgb),.16);">
        <span style="font-size:12px;color:var(--sa-text-6);">⌕</span>
        <input v-model="searchUrl" placeholder="Find URL or payload" class="sa-input" />
      </div>
    </div>

    <!-- feed list -->
    <div style="flex:1;min-height:0;overflow-y:auto;padding:2px 10px 8px;">
      <div v-for="e in feed" :key="e.id" class="sa-rise" style="border-radius:10px;margin-bottom:6px;padding:8px 10px;" :style="{ background: e.rowBg, border: `1px solid ${e.rowBorder}` }">
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="sa-mono" style="font-size:13px;font-weight:600;color:var(--sa-text-2);width:70px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ e.user }}</span>
          <span class="sa-mono" style="font-size:10px;font-weight:800;letter-spacing:.5px;padding:3px 7px;border-radius:5px;min-width:44px;text-align:center;white-space:nowrap;" :style="{ color: e.methodFg, background: e.methodBg }">{{ e.method }}</span>
          <span class="sa-mono" style="font-size:12px;color:var(--sa-text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ e.url }}</span>
        </div>
        <div v-if="e.hasPayload" style="margin:7px 0 0 0;padding:7px 10px;border-radius:7px;background:rgba(var(--sa-bg-rgb),.6);border:1px solid rgba(var(--sa-cyan-rgb),.1);">
          <div
            v-for="(ln, li) in (isExpanded(e.id) ? e.payloadLines : e.payloadLines.slice(0, PAYLOAD_PREVIEW_LINES))"
            :key="li"
            class="sa-mono"
            style="font-size:11px;line-height:1.5;"
            :style="isExpanded(e.id) ? { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' } : { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }"
          ><span style="color:var(--sa-text-5);">{{ ln.k }}</span><span style="color:var(--sa-text-4);">: </span><span style="color:#8fe3b6;">{{ ln.v }}</span></div>
          <button
            v-if="e.expandable"
            type="button"
            class="sa-mono sa-payload-toggle"
            @click="toggleRow(e.id)"
          >{{ isExpanded(e.id) ? '▾' : '▸' }} <template v-if="e.payloadIsString">{{ isExpanded(e.id) ? 'show less' : 'show full' }}</template><template v-else>{{ e.keyCount }} key{{ e.keyCount === 1 ? '' : 's' }}</template></button>
        </div>
      </div>
      <div v-if="feedEmpty" class="sa-mono" style="text-align:center;padding:24px;font-size:12px;color:var(--sa-text-6);">No matching activity</div>
    </div>
  </div>
</template>

<style scoped>
.sa-feed {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.16);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(14, 22, 38, 0.92), rgba(9, 15, 26, 0.92));
  overflow: hidden;
}
.sa-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--sa-text-2);
  font-size: 12px;
  width: 100%;
  font-family: 'JetBrains Mono', monospace;
}
.sa-input::placeholder {
  color: #3c536f;
}
.sa-payload-toggle {
  display: inline-block;
  margin-top: 3px;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 10px;
  color: var(--sa-cyan);
}
.sa-payload-toggle:hover {
  text-decoration: underline;
}
.sa-payload-toggle:focus-visible {
  outline: 1px solid var(--sa-cyan);
  outline-offset: 2px;
  border-radius: 3px;
}

/* Feed options menu (hamburger) */
.sa-menu-wrap {
  position: relative;
}
.sa-menu-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 30px;
  padding: 0;
  border-radius: 8px;
  cursor: pointer;
  color: var(--sa-text-4);
  background: rgba(var(--sa-cyan-rgb), 0.06);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.18);
  transition: color 0.2s, background 0.2s, border-color 0.2s;
}
.sa-menu-btn:hover,
.sa-menu-btn.open {
  color: var(--sa-cyan);
  background: rgba(var(--sa-cyan-rgb), 0.12);
  border-color: rgba(var(--sa-cyan-rgb), 0.4);
}
.sa-menu-btn.active {
  color: var(--sa-cyan);
  border-color: rgba(var(--sa-cyan-rgb), 0.4);
}
.sa-menu-btn:focus-visible {
  outline: 1px solid var(--sa-cyan);
  outline-offset: 2px;
}
.sa-menu-dot {
  position: absolute;
  top: -3px;
  right: -3px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sa-mint);
  box-shadow: 0 0 6px var(--sa-mint);
}
.sa-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 20;
  width: 246px;
  padding: 7px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(18, 28, 46, 0.98), rgba(11, 18, 31, 0.98));
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.22);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.5);
  animation: sa-menu-in 0.14s ease-out;
}
@keyframes sa-menu-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
}
.sa-menu-title {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: var(--sa-text-5);
  padding: 4px 8px 7px;
}
.sa-menu-item {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  text-align: left;
  padding: 9px 8px;
  border: none;
  border-radius: 9px;
  background: transparent;
  cursor: pointer;
  transition: background 0.18s;
}
.sa-menu-item:hover:not(.disabled) {
  background: rgba(var(--sa-cyan-rgb), 0.08);
}
.sa-menu-item.disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
.sa-menu-item:focus-visible {
  outline: 1px solid var(--sa-cyan);
  outline-offset: -1px;
}
.sa-menu-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.sa-menu-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--sa-text-2);
}
.sa-menu-hint {
  font-size: 10px;
  color: var(--sa-text-5);
}
.sa-menu-foot {
  font-size: 9px;
  letter-spacing: 0.5px;
  color: var(--sa-gold);
  padding: 6px 8px 3px;
  text-align: center;
  opacity: 0.8;
}
/* toggle switch */
.sa-switch {
  flex: none;
  position: relative;
  width: 34px;
  height: 18px;
  border-radius: 9px;
  background: rgba(var(--sa-cyan-rgb), 0.12);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.25);
  transition: background 0.2s, border-color 0.2s;
}
.sa-switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--sa-text-4);
  transition: transform 0.2s, background 0.2s;
}
.sa-switch.on {
  background: rgba(var(--sa-cyan-rgb), 0.35);
  border-color: var(--sa-cyan);
}
.sa-switch.on .sa-switch-knob {
  transform: translateX(16px);
  background: var(--sa-cyan);
}
.sa-switch--mint.on {
  background: rgba(var(--sa-mint-rgb), 0.35);
  border-color: var(--sa-mint);
}
.sa-switch--mint.on .sa-switch-knob {
  background: var(--sa-mint);
}
</style>
