<script setup>
import { watch, onMounted } from 'vue'
import DashboardHeader from './components/dashboard/DashboardHeader.vue'
import LiveLeaderboard from './components/dashboard/LiveLeaderboard.vue'
import HallOfFame from './components/dashboard/HallOfFame.vue'
import ChampionsSlot from './components/dashboard/ChampionsSlot.vue'
import LiveFeed from './components/dashboard/LiveFeed.vue'
import { resetState, fullReload, socketConnected } from './socket'
import { shouldHideGamification } from './components/dashboard/dashboardState.js'

watch(socketConnected, (isConnected) => {
  if (isConnected) {
    resetState()
    fullReload()
  }
})

onMounted(() => {
  fullReload()
})
</script>

<template>
  <div data-sa-root class="sa-root">
    <div class="sa-grid-overlay"></div>

    <DashboardHeader />

    <div class="sa-body">
      <LiveLeaderboard />

      <aside class="sa-rail">
        <template v-if="!shouldHideGamification">
          <HallOfFame />
          <ChampionsSlot />
        </template>
        <LiveFeed />
      </aside>
    </div>
  </div>
</template>

<style scoped>
.sa-root {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  color: #cdd9ec;
  background:
    radial-gradient(1200px 700px at 18% -8%, #0d2036 0%, rgba(13, 32, 54, 0) 60%),
    radial-gradient(1100px 800px at 105% 110%, #11243b 0%, rgba(17, 36, 59, 0) 55%), #070b14;
  z-index: 0;
}
.sa-grid-overlay {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(56, 182, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 182, 255, 0.04) 1px, transparent 1px);
  background-size: 54px 54px;
  pointer-events: none;
}
.sa-body {
  position: relative;
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 620px;
  gap: 20px;
  padding: 12px 26px 14px;
}
.sa-rail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

@media (max-width: 1500px) {
  .sa-body {
    grid-template-columns: minmax(0, 1fr) 520px;
  }
}
</style>

<!-- Global helpers: animation keyframes + utility classes used by all dashboard
     child components (which are scoped and can't define these themselves). -->
<style>
.sa-mono {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
@keyframes sa-pop {
  0% { transform: scale(0.4); opacity: 0; }
  60% { transform: scale(1.15); }
  100% { transform: scale(1); opacity: 1; }
}
@keyframes sa-rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes sa-flame {
  0%, 100% { transform: scaleY(1) translateY(0); opacity: 0.9; }
  50% { transform: scaleY(1.18) translateY(-2px); opacity: 1; }
}
@keyframes sa-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
@keyframes sa-crown {
  0%, 100% { transform: translateY(0) rotate(-5deg); }
  50% { transform: translateY(-5px) rotate(5deg); }
}
@keyframes sa-gold {
  0%, 100% { box-shadow: 0 0 22px rgba(255, 205, 91, 0.5), 0 0 0 0 rgba(255, 205, 91, 0.35); }
  50% { box-shadow: 0 0 34px rgba(255, 205, 91, 0.8), 0 0 0 7px rgba(255, 205, 91, 0); }
}
.sa-rise { animation: sa-rise 0.5s ease; }
.sa-flame { animation: sa-flame 0.9s infinite; }
.sa-blink { animation: sa-blink 1.3s infinite; }
.sa-crown { animation: sa-crown 2.2s ease-in-out infinite; }
</style>
