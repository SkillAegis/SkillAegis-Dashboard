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
    radial-gradient(1100px 800px at 105% 110%, #11243b 0%, rgba(17, 36, 59, 0) 55%), var(--sa-bg-base);
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

<!-- Global helpers: color tokens + animation keyframes + utility classes used by
     all dashboard child components (which are scoped and can't define these
     themselves). Custom properties inherit through the DOM to every child. -->
<style>
/* Dashboard color tokens — see CLAUDE.md (Conventions). Channel-triple tokens
   (--*-rgb) feed rgba(var(--x-rgb), <alpha>); solid accents derive from them so
   each hue has a single source of truth. The hex/rgb in comments is the literal
   each token replaced. */
.sa-root {
  /* accent channel triples */
  --sa-cyan-rgb: 54, 210, 255; /* #36d2ff (also unifies stray 56,210,255) */
  --sa-mint-rgb: 91, 227, 154; /* #5be39a */
  --sa-gold-rgb: 255, 205, 91; /* #ffcd5b */
  --sa-gold-bright-rgb: 255, 224, 138; /* #ffe08a */
  --sa-fire-rgb: 255, 120, 60; /* primary flame glow */
  --sa-fire-mid-rgb: 255, 138, 60; /* #ff8a3c — solid "ON FIRE" orange */
  --sa-fire-bright-rgb: 255, 140, 70;
  --sa-fire-deep-rgb: 255, 93, 60; /* #ff5d3c */
  --sa-violet-rgb: 176, 139, 255; /* #b08bff */
  --sa-danger-rgb: 255, 107, 107; /* #ff6b6b */

  /* solid accents (derived from the triples above) */
  --sa-cyan: rgb(var(--sa-cyan-rgb));
  --sa-mint: rgb(var(--sa-mint-rgb));
  --sa-gold: rgb(var(--sa-gold-rgb));
  --sa-gold-bright: rgb(var(--sa-gold-bright-rgb));
  --sa-fire-mid: rgb(var(--sa-fire-mid-rgb));
  --sa-fire-deep: rgb(var(--sa-fire-deep-rgb));
  --sa-violet: rgb(var(--sa-violet-rgb));
  --sa-danger: rgb(var(--sa-danger-rgb));

  /* text ramp (brightest → dimmest) */
  --sa-text-1: #eaf3ff;
  --sa-text-2: #cfe3ff;
  --sa-text-3: #9fb4d0;
  --sa-text-4: #7e98ba;
  --sa-text-5: #5f86b0;
  --sa-text-6: #46607f;

  /* dark surface ramp */
  --sa-bg-rgb: 8, 14, 24; /* panel fill */
  --sa-bg-deep-rgb: 14, 18, 30; /* gradient floor / deeper panel */
  --sa-bg-base: #070b14; /* page base */
  --sa-ink: #0a1322; /* dark text on bright badges */
}
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
  0%, 100% { box-shadow: 0 0 22px rgba(var(--sa-gold-rgb), 0.5), 0 0 0 0 rgba(var(--sa-gold-rgb), 0.35); }
  50% { box-shadow: 0 0 34px rgba(var(--sa-gold-rgb), 0.8), 0 0 0 7px rgba(var(--sa-gold-rgb), 0); }
}
@keyframes sa-bolt {
  0%, 100% { transform: scale(1); opacity: 0.85; }
  45% { transform: scale(1.18); opacity: 1; }
  55% { transform: scale(1.04); opacity: 0.7; }
}
@keyframes sa-clear {
  0%, 100% { box-shadow: 0 0 0 1px rgba(var(--sa-gold-rgb), 0.35), 0 0 18px rgba(var(--sa-mint-rgb), 0.18); }
  50% { box-shadow: 0 0 0 1px rgba(var(--sa-gold-rgb), 0.6), 0 0 30px rgba(var(--sa-mint-rgb), 0.34); }
}
.sa-rise { animation: sa-rise 0.5s ease; }
.sa-flame { animation: sa-flame 0.9s infinite; }
.sa-bolt { animation: sa-bolt 0.9s infinite; }
.sa-blink { animation: sa-blink 1.3s infinite; }
.sa-crown { animation: sa-crown 2.2s ease-in-out infinite; }
</style>
