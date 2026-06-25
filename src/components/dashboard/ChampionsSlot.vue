<script setup>
import { champions, nextScene, setScene } from './dashboardState.js'
</script>

<template>
  <div
    class="sa-slot"
    :style="{ borderColor: champions.slotBorder, background: champions.slotBg }"
    role="button"
    tabindex="0"
    title="Click to switch view"
    @click="nextScene()"
    @keydown.enter.prevent="nextScene()"
    @keydown.space.prevent="nextScene()"
  >
    <!-- scene dots (click a dot to jump straight to that view) -->
    <div style="position:absolute;top:14px;right:16px;display:flex;align-items:center;gap:5px;z-index:2;">
      <div
        v-for="(d, i) in champions.sceneDots"
        :key="i"
        style="cursor:pointer;padding:6px 0;"
        @click.stop="setScene(i)"
      >
        <div :style="{ height: '6px', width: d.w + 'px', borderRadius: '3px', background: d.bg, transition: 'width .4s,background .4s' }"></div>
      </div>
    </div>

    <!-- ON FIRE -->
    <div v-if="champions.showFire" class="sa-rise">
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="sa-flame" style="font-size:16px;filter:drop-shadow(0 0 6px rgba(255,120,60,.8));">🔥</span>
        <span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#ffb993;">ON FIRE</span>
      </div>

      <!-- leader -->
      <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
        <span
          style="font-size:20px;flex:none;line-height:1;"
          :style="{ animation: champions.fireLeader.flameAnim, filter: `drop-shadow(${champions.fireLeader.glow})` }"
        >🔥</span>
        <span style="font-size:23px;font-weight:700;color:#fff;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ champions.fireLeader.name }}</span>
        <span v-if="champions.fireLeader.label" class="sa-mono sa-tier" :style="{ color: champions.fireLeader.fg, borderColor: champions.fireLeader.fg, textShadow: `0 0 8px ${champions.fireLeader.fg}` }">{{ champions.fireLeader.label }}</span>
        <span class="sa-mono" style="font-size:16px;font-weight:800;flex:none;" :style="{ color: champions.fireLeader.fg }" title="Time on fire (m:ss)">{{ champions.fireLeader.val }}</span>
      </div>
      <div style="margin-top:6px;height:6px;border-radius:4px;background:rgba(255,140,70,.12);overflow:hidden;">
        <div :style="{ height: '100%', width: champions.fireLeader.fill + '%', borderRadius: '4px', background: champions.fireLeader.bar, boxShadow: champions.fireLeader.glow, transition: 'width .8s ease' }"></div>
      </div>

      <!-- rest -->
      <div style="margin-top:9px;padding-right:14px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="(f, i) in champions.fireRest" :key="i" style="display:flex;align-items:center;gap:9px;">
          <span class="sa-mono" style="font-size:11px;color:#b07a5c;width:14px;text-align:right;flex:none;">{{ f.rank }}</span>
          <span style="font-size:13px;color:#e6d2c6;flex:none;width:74px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ f.name }}</span>
          <span v-if="f.label" class="sa-mono sa-tier-sm" :style="{ color: f.fg, borderColor: f.fg }">{{ f.label }}</span>
          <div style="flex:1;height:5px;border-radius:3px;background:rgba(255,140,70,.12);overflow:hidden;"><div :style="{ height: '100%', width: f.fill + '%', borderRadius: '3px', background: f.bar, boxShadow: f.glow }"></div></div>
          <span class="sa-mono" style="font-size:11px;flex:none;" :style="{ color: f.fg }" title="Time on fire (m:ss)">{{ f.val }}</span>
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
  cursor: pointer;
  transition: border-color 0.6s, background 0.6s;
}
.sa-slot:focus-visible {
  outline: 2px solid rgba(207, 227, 255, 0.6);
  outline-offset: 2px;
}
.sa-tier {
  flex: none;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 1px;
  padding: 2px 7px;
  border: 1px solid;
  border-radius: 999px;
}
.sa-tier-sm {
  flex: none;
  font-size: 8px;
  font-weight: 800;
  letter-spacing: 0.5px;
  padding: 1px 5px;
  border: 1px solid;
  border-radius: 999px;
}
</style>
