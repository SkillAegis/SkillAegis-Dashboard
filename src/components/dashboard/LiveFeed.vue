<script setup>
import { ref, watch, nextTick } from 'vue'
import { feed, feedEmpty, messages, apiMessages, timeline, searchUser, searchUrl } from './dashboardState.js'

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
    </div>

    <!-- activity timeline -->
    <div style="padding:9px 16px 8px;border-bottom:1px solid rgba(var(--sa-cyan-rgb),.08);">
      <div style="display:flex;align-items:flex-end;gap:14px;">
        <span class="sa-mono" style="font-size:9px;color:var(--sa-text-6);white-space:nowrap;">-{{ timeline.windowMin }} min</span>
        <div style="flex:1;height:38px;overflow:hidden;">
          <div :style="{ display: 'flex', alignItems: 'flex-end', height: '100%', willChange: 'transform', transform: slide, transition: sliding ? 'transform .5s ease-out' : 'none' }">
            <div v-for="(b, i) in timeline.bars" :key="i" :style="{ flex: '1', height: b.h + '%', minHeight: '2px', background: b.bg }"></div>
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
          <span class="sa-mono" style="font-size:10px;font-weight:800;letter-spacing:.5px;padding:3px 7px;border-radius:5px;width:44px;text-align:center;" :style="{ color: e.methodFg, background: e.methodBg }">{{ e.method }}</span>
          <span class="sa-mono" style="font-size:12px;color:var(--sa-text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ e.url }}</span>
        </div>
        <div v-if="e.hasPayload" style="margin:7px 0 0 0;padding:7px 10px;border-radius:7px;background:rgba(var(--sa-bg-rgb),.6);border:1px solid rgba(var(--sa-cyan-rgb),.1);">
          <div v-for="(ln, li) in e.payloadLines" :key="li" class="sa-mono" style="font-size:11px;line-height:1.5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"><span style="color:var(--sa-text-5);">{{ ln.k }}</span><span style="color:var(--sa-text-4);">: </span><span style="color:#8fe3b6;">{{ ln.v }}</span></div>
          <div v-if="e.keyCount > e.payloadLines.length" class="sa-mono" style="font-size:10px;color:var(--sa-cyan);margin-top:3px;">▸ {{ e.keyCount }} keys</div>
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
</style>
