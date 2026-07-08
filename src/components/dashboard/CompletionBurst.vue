<script setup>
import { ref } from 'vue'

// One-shot, palette-matched "all clear" burst, scoped to a single leaderboard
// row. Mounted while `player.justCompleted` holds, then unmounted — so the CSS
// animations play exactly once. Emits from the row centre: an expanding ring,
// a left-to-right finish-line sweep, and a squashed radial spray of glints.
const COLORS = ['var(--sa-mint)', 'var(--sa-cyan)', 'var(--sa-gold)', '#a8e6ff', 'var(--sa-gold-bright)', '#fff6d8']
const COUNT = 22

const particles = ref(
  Array.from({ length: COUNT }, (_, i) => {
    const angle = (Math.PI * 2 * i) / COUNT + (Math.random() - 0.5) * 0.6
    const dist = 70 + Math.random() * 110
    return {
      dx: Math.round(Math.cos(angle) * dist) + 'px',
      dy: Math.round(Math.sin(angle) * dist * 0.5) + 'px', // squashed — the row is short
      color: COLORS[i % COLORS.length],
      size: 4 + Math.round(Math.random() * 4),
      delay: (Math.random() * 0.08).toFixed(3) + 's'
    }
  })
)
</script>

<template>
  <div class="sa-burst">
    <span class="sa-burst-sweep"></span>
    <span class="sa-burst-ring"></span>
    <span
      v-for="(p, i) in particles"
      :key="i"
      class="sa-burst-dot"
      :style="{
        '--dx': p.dx,
        '--dy': p.dy,
        width: p.size + 'px',
        height: p.size + 'px',
        background: p.color,
        boxShadow: `0 0 6px ${p.color}`,
        animationDelay: p.delay
      }"
    ></span>
  </div>
</template>

<style scoped>
.sa-burst {
  position: absolute;
  inset: 0;
  border-radius: 12px;
  overflow: hidden;
  pointer-events: none;
  z-index: 5;
}
.sa-burst-sweep {
  position: absolute;
  top: 0;
  left: -55%;
  width: 55%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.32),
    rgba(var(--sa-mint-rgb), 0.25),
    transparent
  );
  animation: sa-burst-sweep 1.1s ease-out forwards;
}
.sa-burst-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 26px;
  height: 26px;
  margin: -13px 0 0 -13px;
  border-radius: 50%;
  border: 2px solid rgba(var(--sa-gold-rgb), 0.85);
  animation: sa-burst-ring 1s ease-out forwards;
}
.sa-burst-dot {
  position: absolute;
  top: 50%;
  left: 50%;
  border-radius: 50%;
  animation: sa-burst-dot 1.15s ease-out forwards;
}
@keyframes sa-burst-sweep {
  from {
    left: -55%;
    opacity: 1;
  }
  to {
    left: 125%;
    opacity: 0;
  }
}
@keyframes sa-burst-ring {
  from {
    transform: scale(0.2);
    opacity: 0.9;
  }
  to {
    transform: scale(3.6);
    opacity: 0;
  }
}
@keyframes sa-burst-dot {
  0% {
    transform: translate(-50%, -50%) translate(0, 0) scale(1);
    opacity: 1;
  }
  100% {
    transform: translate(-50%, -50%) translate(var(--dx), var(--dy)) scale(0.35);
    opacity: 0;
  }
}
</style>
