<script setup>
import logoUrl from '@/assets/skillaegis-logo.svg'
import { openAdminPanel } from '@/settings.js'
import {
  active_exercises,
  selectedExercise,
  selectedExerciseIndex,
  selectExercise,
  sortByScore,
  hideInactive,
  autoPaginate,
  toggleSort,
  toggleHide,
  togglePaginate,
  activeCount,
  totalCount,
  elapsed,
  clock,
} from './dashboardState.js'

function pill(active, rgb) {
  // rgb = "r,g,b"; the .sa-ctl class supplies the `1px solid` border width.
  return {
    borderColor: active ? `rgba(${rgb},.45)` : 'rgba(56,210,255,.12)',
    background: active ? `rgba(${rgb},.16)` : 'rgba(56,210,255,.04)',
    color: active ? `rgb(${rgb})` : '#5f86b0',
  }
}

function goFullscreen() {
  const el = document.querySelector('[data-sa-leaderboard]') || document.documentElement
  if (el.requestFullscreen) el.requestFullscreen().catch(() => {})
  else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen()
}
</script>

<template>
  <header class="sa-header">
    <div style="display:flex;align-items:center;gap:14px;">
      <img :src="logoUrl" alt="SkillAegis" class="sa-logo" />
      <div>
        <div class="sa-mono" style="font-size:11px;letter-spacing:3px;color:#5f86b0;">SKILLAEGIS // LIVE EXERCISE</div>
        <div style="font-size:23px;font-weight:700;letter-spacing:.2px;color:#eaf3ff;line-height:1.15;">
          {{ selectedExercise ? selectedExercise.name : 'No exercise selected' }}
        </div>
      </div>

      <!-- scenario switcher (only when more than one exercise is selected) -->
      <div v-if="active_exercises.length > 1" style="display:flex;gap:6px;margin-left:8px;">
        <span
          v-for="(ex, i) in active_exercises"
          :key="ex.uuid"
          @click="selectExercise(i)"
          class="sa-scenario-tab sa-mono"
          :style="{
            color: i === selectedExerciseIndex ? '#36d2ff' : '#5f86b0',
            borderColor: i === selectedExerciseIndex ? 'rgba(54,210,255,.45)' : 'rgba(56,210,255,.12)',
            background: i === selectedExerciseIndex ? 'rgba(54,210,255,.12)' : 'rgba(56,210,255,.03)',
          }"
        >{{ ex.name }}</span>
      </div>
    </div>

    <div style="flex:1;"></div>

    <!-- control panel -->
    <div style="display:flex;align-items:center;gap:9px;">
      <div @click="toggleSort" class="sa-ctl" :style="pill(sortByScore, '54,210,255')">
        <span style="font-size:13px;">⇅</span><span class="sa-mono sa-ctl-label">SORT BY SCORE</span>
      </div>
      <div @click="toggleHide" class="sa-ctl" :style="pill(hideInactive, '255,205,91')">
        <span style="font-size:13px;">◴</span><span class="sa-mono sa-ctl-label">HIDE INACTIVE</span>
      </div>
      <div @click="togglePaginate" class="sa-ctl" :style="pill(autoPaginate, '91,227,154')">
        <span style="font-size:13px;">⊞</span><span class="sa-mono sa-ctl-label">AUTO PAGINATE</span>
      </div>
      <div @click="goFullscreen" class="sa-ctl" style="border:1px solid rgba(56,210,255,.18);background:rgba(56,210,255,.05);">
        <span style="font-size:13px;">⤢</span><span class="sa-mono sa-ctl-label" style="color:#9fb4d0;">FULLSCREEN</span>
      </div>
    </div>

    <div style="width:1px;height:42px;background:rgba(56,210,255,.16);"></div>

    <div style="display:flex;align-items:center;gap:12px;">
      <div class="sa-stat-pill" style="border-color:rgba(56,210,255,.22);background:rgba(56,210,255,.06);">
        <span class="sa-mono" style="font-size:11px;color:#5f86b0;letter-spacing:1px;">PLAYERS</span>
        <span class="sa-mono" style="font-size:17px;font-weight:800;color:#36d2ff;">{{ activeCount }}<span style="color:#3c536f;font-size:13px;">/{{ totalCount }}</span></span>
      </div>
      <div class="sa-stat-pill" style="border-color:rgba(255,205,91,.25);background:rgba(255,205,91,.06);">
        <span class="sa-mono" style="font-size:11px;color:#5f86b0;letter-spacing:1px;">ELAPSED</span>
        <span class="sa-mono" style="font-size:17px;font-weight:800;color:#ffcd5b;">{{ elapsed }}</span>
      </div>
      <div class="sa-mono" style="font-size:17px;font-weight:700;color:#9fb4d0;padding:9px 13px;border:1px solid rgba(56,210,255,.14);border-radius:10px;">{{ clock }}</div>
      <div title="Admin settings" @click="openAdminPanel" class="sa-gear">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
      </div>
    </div>
  </header>
</template>

<style scoped>
.sa-header {
  position: relative;
  height: 90px;
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 0 26px;
  border-bottom: 1px solid rgba(56, 210, 255, 0.16);
  background: linear-gradient(180deg, rgba(12, 26, 44, 0.9), rgba(8, 14, 24, 0.4));
}
.sa-logo {
  width: 50px;
  height: 50px;
  display: block;
  filter: drop-shadow(0 0 16px rgba(54, 210, 255, 0.5));
}
.sa-scenario-tab {
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 6px 11px;
  border-radius: 9px;
  border: 1px solid;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sa-ctl {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 13px;
  border-radius: 10px;
  border: 1px solid transparent;
  transition: background 0.25s, border-color 0.25s, color 0.25s;
}
.sa-ctl-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.sa-stat-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  border: 1px solid;
  border-radius: 10px;
}
.sa-gear {
  cursor: pointer;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: #243a55;
  opacity: 0.6;
  transition: opacity 0.25s, color 0.25s, background 0.25s;
}
.sa-gear:hover {
  opacity: 1;
  color: #36d2ff;
  background: rgba(56, 210, 255, 0.08);
}
</style>
