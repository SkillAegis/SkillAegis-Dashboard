<script setup>
import { podium } from './dashboardState.js'
</script>

<template>
  <div class="sa-hof">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
      <span style="width:8px;height:8px;border-radius:2px;background:#ffcd5b;box-shadow:0 0 10px #ffcd5b;"></span>
      <span style="font-size:15px;font-weight:700;letter-spacing:2px;color:#ffe2a0;">HALL OF FAME</span>
    </div>
    <div style="display:flex;align-items:flex-end;justify-content:center;gap:14px;height:182px;">
      <div v-if="podium.length === 0" class="sa-mono" style="align-self:center;color:#6b7a93;font-size:12px;">
        No champions yet
      </div>
      <div v-for="h in podium" :key="h.id" style="width:160px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;">
        <div v-if="h.first" class="sa-crown" style="font-size:26px;line-height:1;margin-bottom:2px;filter:drop-shadow(0 3px 6px rgba(255,205,91,.5));">👑</div>
        <div
          class="sa-mono"
          style="border-radius:14px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:17px;color:#0a1322;margin-bottom:6px;"
          :style="{ width: h.badge + 'px', height: h.badge + 'px', background: h.medal, boxShadow: `0 0 18px ${h.glow}`, animation: h.badgeAnim }"
        >{{ h.initials }}</div>
        <div style="font-weight:700;color:#fff;line-height:1.1;text-align:center;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :style="{ fontSize: h.nameSize + 'px' }">{{ h.name }}</div>
        <div class="sa-mono" style="font-weight:800;margin-top:1px;" :style="{ fontSize: h.scoreSize + 'px', color: h.scoreColor }">{{ h.score }}</div>
        <div
          class="sa-mono"
          style="position:relative;overflow:hidden;width:100%;margin-top:7px;border-radius:9px 9px 0 0;display:flex;align-items:flex-start;justify-content:center;padding-top:6px;font-weight:800;font-size:18px;color:rgba(10,19,34,.55);"
          :style="{ height: h.barH + 'px', background: h.barBg }"
        >{{ h.rank }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sa-hof {
  border: 1px solid rgba(255, 205, 91, 0.28);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(38, 30, 14, 0.55), rgba(14, 18, 30, 0.85));
  padding: 12px 18px 14px;
}
</style>
