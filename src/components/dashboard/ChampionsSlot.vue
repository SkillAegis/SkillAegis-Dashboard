<script setup>
import { champions } from './dashboardState.js'
</script>

<template>
  <div
    class="sa-slot"
    :style="{ borderColor: champions.slotBorder, background: champions.slotBg }"
  >
    <!-- scene dots -->
    <div style="position:absolute;top:14px;right:16px;display:flex;align-items:center;gap:5px;z-index:2;">
      <div v-for="(d, i) in champions.sceneDots" :key="i" :style="{ height: '6px', width: d.w + 'px', borderRadius: '3px', background: d.bg, transition: 'width .4s,background .4s' }"></div>
    </div>

    <!-- ON FIRE -->
    <div v-if="champions.showFire" class="sa-rise">
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="sa-flame" style="font-size:16px;filter:drop-shadow(0 0 6px rgba(255,120,60,.8));">🔥</span>
        <span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#ffb993;">ON FIRE</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
        <span class="sa-mono" style="font-size:13px;font-weight:800;color:#ff8a3c;flex:none;">1</span>
        <span style="font-size:24px;font-weight:700;color:#fff;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ champions.fireLeader.name }}</span>
        <span class="sa-mono" style="font-size:16px;font-weight:800;color:#ff8a3c;flex:none;">{{ champions.fireLeader.val }}<span style="font-size:10px;color:#5f86b0;">m</span></span>
      </div>
      <div style="margin-top:10px;padding-right:14px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="(f, i) in champions.fireRest" :key="i" style="display:flex;align-items:center;gap:9px;">
          <span class="sa-mono" style="font-size:11px;color:#b07a5c;width:14px;text-align:right;flex:none;">{{ f.rank }}</span>
          <span style="font-size:13px;color:#e6d2c6;flex:none;width:84px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ f.name }}</span>
          <div style="flex:1;height:5px;border-radius:3px;background:rgba(255,140,70,.12);overflow:hidden;"><div :style="{ height: '100%', width: f.frac + '%', borderRadius: '3px', background: 'linear-gradient(90deg,rgba(255,140,70,.5),#ff8a3c)' }"></div></div>
          <span class="sa-mono" style="font-size:11px;color:#c79a86;flex:none;">{{ f.val }}m</span>
        </div>
      </div>
    </div>

    <!-- SPEED RUNNER -->
    <div v-if="champions.showSpeed" class="sa-rise">
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:16px;filter:drop-shadow(0 0 6px rgba(54,210,255,.7));">⚡</span>
        <span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#a8e6ff;">SPEED RUNNER</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
        <span class="sa-mono" style="font-size:13px;font-weight:800;color:#36d2ff;flex:none;">1</span>
        <span style="font-size:24px;font-weight:700;color:#fff;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ champions.speedLeader.name }}</span>
        <span class="sa-mono" style="font-size:16px;font-weight:800;color:#36d2ff;flex:none;">{{ champions.speedLeader.val }}<span style="font-size:10px;color:#5f86b0;">s</span></span>
      </div>
      <div style="margin-top:10px;padding-right:14px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="(s, i) in champions.speedRest" :key="i" style="display:flex;align-items:center;gap:9px;">
          <span class="sa-mono" style="font-size:11px;color:#5f86b0;width:14px;text-align:right;flex:none;">{{ s.rank }}</span>
          <span style="font-size:13px;color:#c7dcea;flex:none;width:84px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.name }}</span>
          <div style="flex:1;height:5px;border-radius:3px;background:rgba(54,210,255,.1);overflow:hidden;"><div :style="{ height: '100%', width: s.frac + '%', borderRadius: '3px', background: 'linear-gradient(90deg,rgba(54,210,255,.45),#36d2ff)' }"></div></div>
          <span class="sa-mono" style="font-size:11px;color:#8fb6d2;flex:none;">{{ s.val }}s</span>
        </div>
      </div>
    </div>

    <!-- TROPHIES -->
    <div v-if="champions.showTrophies" class="sa-rise">
      <div style="display:flex;align-items:center;gap:9px;margin-bottom:11px;"><span style="font-size:14px;">🏆</span><span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#ffe2a0;">TROPHIES</span></div>
      <div v-if="champions.trophies.length === 0" class="sa-mono" style="color:#6b7a93;font-size:12px;text-align:center;padding:18px 0;">No trophies for this scenario</div>
      <div v-else style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">
        <div v-for="tr in champions.trophies" :key="tr.id" style="display:flex;flex-direction:column;align-items:center;text-align:center;gap:4px;padding:12px 6px;border-radius:11px;" :style="{ background: tr.bg, border: `1px solid ${tr.border}` }">
          <span style="font-size:20px;line-height:1;" :style="{ color: tr.fg }">{{ tr.icon }}</span>
          <span class="sa-mono" style="font-size:10px;letter-spacing:.5px;color:#8aa3c0;text-transform:uppercase;white-space:nowrap;">{{ tr.name }}</span>
          <span style="font-size:15px;font-weight:800;color:#fff;line-height:1.2;max-width:100%;word-break:break-word;">{{ tr.holder }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sa-slot {
  position: relative;
  overflow: hidden;
  border: 1px solid;
  border-radius: 16px;
  padding: 13px 16px;
  height: 188px;
  transition: border-color 0.6s, background 0.6s;
}
</style>
