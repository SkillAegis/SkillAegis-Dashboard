<script setup>
import { computed } from 'vue'
import { taskCompletion } from './dashboardState.js'

const tasks = computed(() => taskCompletion.value.tasks)
const participants = computed(() => taskCompletion.value.participants)

// The least-cleared task still in play — the single most useful "what should I
// explain next?" callout. Fully-cleared tasks are dropped (nothing left there).
const wall = computed(() => {
  const pending = tasks.value.filter((t) => t.pct < 100)
  if (!pending.length) return null
  return pending.reduce((a, b) => (b.pct < a.pct ? b : a))
})
</script>

<template>
  <div v-if="tasks.length" class="sa-taskcomp">
    <div style="width:46px;flex:none;"></div>
    <div style="width:236px;flex:none;font-size:11px;font-weight:700;letter-spacing:1.5px;color:var(--sa-text-3);">TASK COMPLETION</div>

    <!-- compact bars: one per task, aligned under the task columns above -->
    <div v-if="participants > 0" style="flex:1;display:flex;align-items:flex-end;gap:5px;height:24px;">
      <div
        v-for="t in tasks"
        :key="t.num"
        style="flex:1;min-width:0;min-height:3px;border-radius:2px 2px 0 0;transition:height .6s ease;"
        :style="{ height: t.pct + '%', background: t.barBg, boxShadow: t.glow }"
        :title="t.title"
      ></div>
    </div>
    <div v-else class="sa-mono" style="flex:1;display:flex;align-items:center;font-size:11px;color:var(--sa-text-6);">
      Awaiting participants…
    </div>

    <!-- hardest task still in play -->
    <div style="width:150px;flex:none;display:flex;flex-direction:column;justify-content:center;">
      <template v-if="participants > 0">
        <div class="sa-mono" style="font-size:9px;letter-spacing:1px;color:var(--sa-text-6);">HARDEST</div>
        <div v-if="wall" style="display:flex;align-items:baseline;gap:6px;">
          <span class="sa-mono" style="font-size:12px;font-weight:700;color:var(--sa-text-3);">Task {{ wall.num }}</span>
          <span class="sa-mono" style="font-size:14px;font-weight:800;" :style="{ color: wall.fg }">{{ wall.pct }}%</span>
        </div>
        <div v-else class="sa-mono" style="font-size:12px;font-weight:700;color:var(--sa-mint);">All cleared 🎉</div>
      </template>
    </div>
    <div style="width:78px;flex:none;"></div>
  </div>
</template>

<style scoped>
.sa-taskcomp {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 7px 22px 8px;
  border-top: 1px solid rgba(var(--sa-cyan-rgb), 0.1);
}
</style>
