<script setup>
import { feed, feedEmpty, messages, apiMessages, timeline, searchUser, searchUrl } from './dashboardState.js'
</script>

<template>
  <div class="sa-feed">
    <div style="display:flex;align-items:center;gap:12px;padding:11px 16px 9px;border-bottom:1px solid rgba(56,210,255,.1);">
      <span style="font-size:14px;font-weight:700;letter-spacing:1.5px;color:#cfe3ff;">LIVE FEED</span>
      <span class="sa-blink" style="width:8px;height:8px;border-radius:50%;background:#5be39a;box-shadow:0 0 8px #5be39a;"></span>
      <div style="flex:1;"></div>
      <div style="display:flex;align-items:center;gap:7px;padding:5px 10px;border-radius:8px;background:rgba(54,210,255,.1);border:1px solid rgba(54,210,255,.2);">
        <span class="sa-mono" style="font-size:10px;color:#7e98ba;">MESSAGES</span>
        <span class="sa-mono" style="font-size:14px;font-weight:800;color:#36d2ff;">{{ messages }}</span>
      </div>
      <div style="display:flex;align-items:center;gap:7px;padding:5px 10px;border-radius:8px;background:rgba(91,227,154,.1);border:1px solid rgba(91,227,154,.2);">
        <span style="font-size:11px;">🔒</span><span class="sa-mono" style="font-size:10px;color:#7e98ba;">API</span>
        <span class="sa-mono" style="font-size:14px;font-weight:800;color:#5be39a;">{{ apiMessages }}</span>
      </div>
    </div>

    <!-- activity timeline -->
    <div style="padding:9px 16px 8px;border-bottom:1px solid rgba(56,210,255,.08);">
      <div style="display:flex;align-items:flex-end;gap:14px;">
        <span class="sa-mono" style="font-size:9px;color:#46607f;white-space:nowrap;">-{{ timeline.windowMin }} min</span>
        <div style="flex:1;display:flex;align-items:flex-end;gap:2px;height:38px;">
          <div v-for="(b, i) in timeline.bars" :key="i" :style="{ flex: '1', height: b.h + '%', minHeight: '2px', borderRadius: '2px', background: b.bg, transition: 'height .4s ease' }"></div>
        </div>
        <div style="text-align:right;min-width:54px;">
          <div class="sa-mono" style="font-size:10px;color:#7e98ba;">now <span style="color:#36d2ff;font-weight:800;">{{ timeline.tlNow }}</span></div>
          <div class="sa-mono" style="font-size:10px;color:#7e98ba;">max <span style="color:#9fb4d0;font-weight:800;">{{ timeline.tlMax }}</span></div>
        </div>
      </div>
    </div>

    <!-- search -->
    <div style="display:flex;gap:10px;padding:9px 16px;">
      <div style="flex:1;display:flex;align-items:center;gap:8px;padding:7px 11px;border-radius:9px;background:rgba(8,14,24,.7);border:1px solid rgba(56,210,255,.16);">
        <span style="font-size:12px;color:#46607f;">⌕</span>
        <input v-model="searchUser" placeholder="Find user" class="sa-input" />
      </div>
      <div style="flex:1.4;display:flex;align-items:center;gap:8px;padding:7px 11px;border-radius:9px;background:rgba(8,14,24,.7);border:1px solid rgba(56,210,255,.16);">
        <span style="font-size:12px;color:#46607f;">⌕</span>
        <input v-model="searchUrl" placeholder="Find URL or payload" class="sa-input" />
      </div>
    </div>

    <!-- feed list -->
    <div style="flex:1;min-height:0;overflow-y:auto;padding:2px 10px 8px;">
      <div v-for="e in feed" :key="e.id" class="sa-rise" style="border-radius:10px;margin-bottom:6px;padding:8px 10px;" :style="{ background: e.rowBg, border: `1px solid ${e.rowBorder}` }">
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="sa-mono" style="font-size:13px;font-weight:600;color:#cfe3ff;width:70px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ e.user }}</span>
          <span class="sa-mono" style="font-size:10px;font-weight:800;letter-spacing:.5px;padding:3px 7px;border-radius:5px;width:44px;text-align:center;" :style="{ color: e.methodFg, background: e.methodBg }">{{ e.method }}</span>
          <span class="sa-mono" style="font-size:12px;color:#9fb4d0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ e.url }}</span>
        </div>
        <div v-if="e.hasPayload" style="margin:7px 0 0 0;padding:7px 10px;border-radius:7px;background:rgba(8,14,24,.6);border:1px solid rgba(56,210,255,.1);">
          <div v-for="(ln, li) in e.payloadLines" :key="li" class="sa-mono" style="font-size:11px;line-height:1.5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"><span style="color:#5f86b0;">{{ ln.k }}</span><span style="color:#7e98ba;">: </span><span style="color:#8fe3b6;">{{ ln.v }}</span></div>
          <div v-if="e.keyCount > e.payloadLines.length" class="sa-mono" style="font-size:10px;color:#36d2ff;margin-top:3px;">▸ {{ e.keyCount }} keys</div>
        </div>
      </div>
      <div v-if="feedEmpty" class="sa-mono" style="text-align:center;padding:24px;font-size:12px;color:#46607f;">No matching activity</div>
    </div>
  </div>
</template>

<style scoped>
.sa-feed {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(56, 210, 255, 0.16);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(14, 22, 38, 0.92), rgba(9, 15, 26, 0.92));
  overflow: hidden;
}
.sa-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #cfe3ff;
  font-size: 12px;
  width: 100%;
  font-family: 'JetBrains Mono', monospace;
}
.sa-input::placeholder {
  color: #3c536f;
}
</style>
