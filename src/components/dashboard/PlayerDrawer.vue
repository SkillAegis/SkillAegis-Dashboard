<script setup>
/**
 * Player drill-down drawer — a right-edge slide-over that profiles one
 * participant for the selected exercise (Variant B, signed off in Phase 0:
 * docs/PRD-player-drilldown.md, docs/mockups/player-drilldown.html).
 *
 * Phase 1 builds the interaction surface, the dimming backdrop, and the header
 * (identity + rank + score + live status chips), plus the two-column body: a
 * scrolling main column and a full-height events rail whose list stays an
 * empty-state placeholder until Phase 4 populates it. Per-task timing (Phase 2)
 * and last-seen + sparkline (Phase 3) render below the header in later slices.
 *
 * The component is a pure view over `selectedPlayer`; open/close is just setting
 * `selectedPlayerId`. `open` tracks that computed directly, so a player leaving
 * the roster closes the drawer, and the slide-out keeps its last content because
 * Vue freezes the leaving DOM rather than re-rendering it against a null player.
 */
import { computed, ref, watch, nextTick, onUnmounted } from 'vue'
import { selectedPlayer, closePlayer } from './dashboardState.js'
import { reduceMotionOn } from '@/settings.js'

const player = selectedPlayer
const open = computed(() => player.value !== null)

const drawerRef = ref(null)
const closeBtnRef = ref(null)

// Medal treatment on the rank badge only for a genuine top-3 scorer (mirrors the
// leaderboard's `top`, which requires score > 0 — so rank 1 on an empty board
// stays neutral rather than gold).
const rankClass = computed(() => {
  const p = player.value
  return p && p.top && p.rank <= 3 ? 'top' + p.rank : ''
})

// Slide from the right by default; a plain cross-fade when reduced motion is on
// (the admin toggle from Enhancements item 7). The OS-level
// prefers-reduced-motion is covered by the media query in <style> below.
const drawerTransition = computed(() => (reduceMotionOn.value ? 'sa-drawer-fade' : 'sa-drawer-slide'))

/* Accessibility: trap focus while open, dismiss on Esc, return focus to the
   originating row on close. The keydown listener is attached at the document
   level (capture) only while open, so Esc still fires if focus escapes. */
let returnFocusEl = null

function focusable() {
  const root = drawerRef.value
  if (!root) return []
  return Array.from(
    root.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
  ).filter((el) => !el.disabled && el.offsetParent !== null)
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    closePlayer()
    return
  }
  if (e.key !== 'Tab') return
  const els = focusable()
  if (!els.length) {
    e.preventDefault()
    return
  }
  const first = els[0]
  const last = els[els.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    returnFocusEl = document.activeElement
    document.addEventListener('keydown', onKeydown, true)
    nextTick(() => closeBtnRef.value?.focus())
  } else {
    document.removeEventListener('keydown', onKeydown, true)
    if (returnFocusEl && typeof returnFocusEl.focus === 'function') returnFocusEl.focus()
    returnFocusEl = null
  }
})

onUnmounted(() => document.removeEventListener('keydown', onKeydown, true))
</script>

<template>
  <Transition name="sa-backdrop-fade">
    <div v-if="open" class="sa-drawer-backdrop" @click="closePlayer"></div>
  </Transition>

  <Transition :name="drawerTransition">
    <aside
      v-if="open"
      ref="drawerRef"
      class="sa-drawer"
      role="dialog"
      aria-modal="true"
      :aria-label="player ? `Participant detail — ${player.name}` : 'Participant detail'"
    >
      <div class="sa-drawer-top">
        <span class="sa-eyebrow sa-mono"><b>◧</b> PARTICIPANT · MONITOR</span>
        <span class="sa-drawer-spacer"></span>
        <button ref="closeBtnRef" class="sa-drawer-x" aria-label="Close panel" @click="closePlayer">✕</button>
      </div>

      <div v-if="player" class="sa-drawer-body">
        <div class="sa-drawer-scroll">
          <!-- header block: identity + rank + score + live status chips -->
          <div class="sa-dhead">
            <div class="sa-idrow">
              <div class="sa-rankbadge sa-mono" :class="rankClass"><span class="sa-hash">#</span>{{ player.rank }}</div>
              <div class="sa-idmeta">
                <div class="sa-idname">
                  <span v-if="player.complete" class="sa-idmedal" title="Cleared every task">🏅</span>
                  <span class="sa-nm">{{ player.name }}</span>
                </div>
                <div class="sa-idorg sa-mono">{{ player.org }}</div>
              </div>
              <div class="sa-scorebox">
                <div>
                  <span class="sa-sc-v sa-mono">{{ player.score }}</span>
                  <span class="sa-sc-m sa-mono"> / {{ player.maxScore }}</span>
                </div>
                <div class="sa-sc-lbl sa-mono">SCORE</div>
              </div>
            </div>
            <div class="sa-chips">
              <span v-for="c in player.chips" :key="c.key" class="sa-chip" :style="c.style">
                <span class="sa-chip-g">{{ c.glyph }}</span>{{ c.label }}
              </span>
              <span v-if="!player.chips.length" class="sa-chip sa-chip-none">no badges yet</span>
            </div>
          </div>
          <!-- Per-task timing (Phase 2) and last-seen + activity (Phase 3) render here. -->
        </div>

        <!-- events rail shell — populated from the per-user backend history in Phase 4 -->
        <div class="sa-erail">
          <div class="sa-erail-head">
            <span class="sa-erail-ttl">RECENT EVENTS</span>
            <span class="sa-erail-sub sa-mono">this participant</span>
          </div>
          <div class="sa-erail-list">
            <div class="sa-erail-empty sa-mono">Recent request &amp; webhook events will appear here.</div>
          </div>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
/* dimming backdrop over the board */
.sa-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(4, 8, 15, 0.62);
  backdrop-filter: blur(2px);
}

/* the drawer — two columns at ~2× width, right-edge slide-over */
.sa-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 50;
  width: min(920px, 96vw);
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(16, 25, 42, 0.985), rgba(9, 14, 25, 0.985));
  border-left: 1px solid rgba(var(--sa-cyan-rgb), 0.28);
  box-shadow: -24px 0 60px rgba(0, 0, 0, 0.55), inset 1px 0 0 rgba(var(--sa-cyan-rgb), 0.06);
}

/* top bar */
.sa-drawer-top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
  padding: 13px 20px 12px;
  border-bottom: 1px solid rgba(var(--sa-cyan-rgb), 0.1);
  background: rgba(16, 25, 42, 0.6);
}
.sa-eyebrow {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--sa-text-5);
}
.sa-eyebrow b {
  color: var(--sa-cyan);
  font-weight: 700;
}
.sa-drawer-spacer {
  flex: 1;
}
.sa-drawer-x {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--sa-text-4);
  font-size: 15px;
  line-height: 1;
  background: rgba(var(--sa-cyan-rgb), 0.06);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.18);
  transition: color 0.18s, background 0.18s, border-color 0.18s;
}
.sa-drawer-x:hover {
  color: var(--sa-cyan);
  background: rgba(var(--sa-cyan-rgb), 0.12);
  border-color: rgba(var(--sa-cyan-rgb), 0.4);
}
.sa-drawer-x:focus-visible {
  outline: 2px solid var(--sa-cyan);
  outline-offset: 2px;
}

/* two-column body: scrolling main column + full-height events rail */
.sa-drawer-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.sa-drawer-scroll {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.sa-drawer-scroll::-webkit-scrollbar {
  width: 9px;
}
.sa-drawer-scroll::-webkit-scrollbar-thumb {
  background: rgba(var(--sa-cyan-rgb), 0.18);
  border-radius: 6px;
}

/* header block */
.sa-dhead {
  padding: 18px 24px;
}
.sa-idrow {
  display: flex;
  align-items: center;
  gap: 14px;
}
.sa-rankbadge {
  width: 48px;
  height: 48px;
  flex: none;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 21px;
  background: rgba(var(--sa-cyan-rgb), 0.08);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.2);
  color: var(--sa-text-3);
}
.sa-rankbadge.top1 {
  background: var(--sa-gold);
  color: var(--sa-ink);
  border-color: transparent;
  box-shadow: 0 0 20px rgba(var(--sa-gold-rgb), 0.45);
}
.sa-rankbadge.top2 {
  background: #c7d3e6;
  color: var(--sa-ink);
  border-color: transparent;
}
.sa-rankbadge.top3 {
  background: #e09b62;
  color: var(--sa-ink);
  border-color: transparent;
}
.sa-hash {
  font-size: 11px;
  opacity: 0.6;
  margin-right: 1px;
}
.sa-idmeta {
  min-width: 0;
  flex: 1;
}
.sa-idname {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sa-nm {
  font-size: 25px;
  font-weight: 700;
  color: var(--sa-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.3px;
}
.sa-idmedal {
  flex: none;
  font-size: 18px;
  filter: drop-shadow(0 0 5px rgba(var(--sa-gold-rgb), 0.8));
}
.sa-idorg {
  font-size: 11px;
  color: var(--sa-text-5);
  margin-top: 2px;
}
.sa-scorebox {
  text-align: right;
  flex: none;
}
.sa-sc-v {
  font-size: 32px;
  font-weight: 800;
  color: var(--sa-cyan);
  line-height: 1;
}
.sa-sc-m {
  font-size: 14px;
  color: var(--sa-text-5);
}
.sa-sc-lbl {
  font-size: 9px;
  letter-spacing: 1.5px;
  color: var(--sa-text-6);
  margin-top: 3px;
}
.sa-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}
.sa-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px 5px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
  white-space: nowrap;
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.3);
  background: rgba(var(--sa-cyan-rgb), 0.1);
  color: var(--sa-text-2);
}
.sa-chip-g {
  font-size: 12px;
  line-height: 1;
}
.sa-chip-none {
  border-color: rgba(110, 130, 160, 0.28);
  background: rgba(var(--sa-bg-rgb), 0.5);
  color: var(--sa-text-5);
}

/* events rail */
.sa-erail {
  flex: none;
  width: 372px;
  border-left: 1px solid rgba(var(--sa-cyan-rgb), 0.14);
  background: rgba(var(--sa-bg-rgb), 0.5);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sa-erail-head {
  flex: none;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 15px 16px 12px;
  border-bottom: 1px solid rgba(var(--sa-cyan-rgb), 0.1);
}
.sa-erail-ttl {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.6px;
  color: var(--sa-text-3);
}
.sa-erail-sub {
  font-size: 10px;
  color: var(--sa-text-6);
  margin-left: auto;
}
.sa-erail-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 12px 14px;
}
.sa-erail-list::-webkit-scrollbar {
  width: 9px;
}
.sa-erail-list::-webkit-scrollbar-thumb {
  background: rgba(var(--sa-cyan-rgb), 0.18);
  border-radius: 6px;
}
.sa-erail-empty {
  font-size: 11px;
  color: var(--sa-text-6);
  text-align: center;
  padding: 24px 8px;
  line-height: 1.5;
}

/* transitions — slide (default) / fade (reduced motion) + backdrop fade */
.sa-drawer-slide-enter-active,
.sa-drawer-slide-leave-active {
  transition: transform 0.34s cubic-bezier(0.6, 0.05, 0.2, 1);
}
.sa-drawer-slide-enter-from,
.sa-drawer-slide-leave-to {
  transform: translateX(100%);
}
.sa-drawer-fade-enter-active,
.sa-drawer-fade-leave-active {
  transition: opacity 0.2s ease;
}
.sa-drawer-fade-enter-from,
.sa-drawer-fade-leave-to {
  opacity: 0;
}
.sa-backdrop-fade-enter-active,
.sa-backdrop-fade-leave-active {
  transition: opacity 0.32s ease;
}
.sa-backdrop-fade-enter-from,
.sa-backdrop-fade-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .sa-drawer-slide-enter-active,
  .sa-drawer-slide-leave-active,
  .sa-drawer-fade-enter-active,
  .sa-drawer-fade-leave-active,
  .sa-backdrop-fade-enter-active,
  .sa-backdrop-fade-leave-active {
    transition: none;
  }
  .sa-drawer-slide-enter-from,
  .sa-drawer-slide-leave-to {
    transform: none;
  }
}
</style>
