<script setup>
import { champions, nextScene, setScene, scenePinned, toggleScenePinned } from './dashboardState.js'

// Body click cycles scenes, but stays put while pinned (the dots remain the
// deliberate way to change view without unpinning).
function cycle() {
  if (!scenePinned.value) nextScene()
}
</script>

<template>
  <div
    class="sa-slot"
    :style="{ borderColor: champions.slotBorder, background: champions.slotBg }"
    role="button"
    tabindex="0"
    :title="scenePinned ? 'View pinned — use the dots to change, or unpin to resume rotation' : 'Click to switch view'"
    @click="cycle()"
    @keydown.enter.prevent="cycle()"
    @keydown.space.prevent="cycle()"
  >
    <!-- pin (freeze auto-rotate) + scene dots (click a dot to jump straight to that view) -->
    <div style="position:absolute;top:12px;right:16px;display:flex;align-items:center;gap:11px;z-index:2;">
      <div
        class="sa-pin"
        :class="{ 'sa-pin-on': scenePinned }"
        role="button"
        tabindex="0"
        :aria-pressed="scenePinned"
        :title="scenePinned ? 'Pinned — auto-rotate stopped (click to resume)' : 'Auto-rotating views — click to pin this one'"
        @click.stop="toggleScenePinned()"
        @keydown.enter.stop.prevent="toggleScenePinned()"
        @keydown.space.stop.prevent="toggleScenePinned()"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <line x1="12" y1="17" x2="12" y2="22"></line>
          <path d="M9 10.8a2 2 0 0 1-1.1 1.8l-1.8.9A2 2 0 0 0 5 15.2V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.8a2 2 0 0 0-1.1-1.7l-1.8-.9A2 2 0 0 1 15 10.8V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1Z"></path>
        </svg>
      </div>
      <div style="display:flex;align-items:center;gap:5px;">
        <div
          v-for="(d, i) in champions.sceneDots"
          :key="i"
          style="cursor:pointer;padding:6px 0;"
          @click.stop="setScene(i)"
        >
          <div :style="{ height: '6px', width: d.w + 'px', borderRadius: '3px', background: d.bg, transition: 'width .4s,background .4s' }"></div>
        </div>
      </div>
    </div>

    <!-- ON FIRE -->
    <div v-if="champions.showFire" class="sa-rise">
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="sa-flame" style="font-size:16px;filter:drop-shadow(0 0 6px rgba(var(--sa-fire-rgb),.8));">🔥</span>
        <span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#ffb993;">ON FIRE</span>
        <span class="sa-mono sa-cap">· time spent on a scoring streak</span>
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
      <div style="margin-top:6px;height:6px;border-radius:4px;background:rgba(var(--sa-fire-bright-rgb),.12);overflow:hidden;">
        <div :style="{ height: '100%', width: champions.fireLeader.fill + '%', borderRadius: '4px', background: champions.fireLeader.bar, boxShadow: champions.fireLeader.glow, transition: 'width .8s ease' }"></div>
      </div>

      <!-- rest -->
      <div style="margin-top:9px;padding-right:14px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="(f, i) in champions.fireRest" :key="i" style="display:flex;align-items:center;gap:9px;">
          <span class="sa-mono" style="font-size:11px;color:#b07a5c;width:14px;text-align:right;flex:none;">{{ f.rank }}</span>
          <span style="font-size:13px;color:#e6d2c6;flex:none;width:74px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ f.name }}</span>
          <span v-if="f.label" class="sa-mono sa-tier-sm" :style="{ color: f.fg, borderColor: f.fg }">{{ f.label }}</span>
          <div style="flex:1;height:5px;border-radius:3px;background:rgba(var(--sa-fire-bright-rgb),.12);overflow:hidden;"><div :style="{ height: '100%', width: f.fill + '%', borderRadius: '3px', background: f.bar, boxShadow: f.glow }"></div></div>
          <span class="sa-mono" style="font-size:11px;flex:none;" :style="{ color: f.fg }" title="Time on fire (m:ss)">{{ f.val }}</span>
        </div>
      </div>
    </div>

    <!-- SPEED RUNNER -->
    <div v-if="champions.showSpeed" class="sa-rise">
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:16px;filter:drop-shadow(0 0 6px rgba(var(--sa-cyan-rgb),.7));">⚡</span>
        <span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#a8e6ff;">SPEED RUNNER</span>
        <span class="sa-mono sa-cap">· 10 = perfect clean-run pace</span>
      </div>

      <!-- leader -->
      <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
        <span
          style="font-size:20px;flex:none;line-height:1;"
          :style="{ animation: champions.speedLeader.boltAnim, filter: `drop-shadow(${champions.speedLeader.glow})` }"
        >⚡</span>
        <span style="font-size:23px;font-weight:700;color:#fff;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ champions.speedLeader.name }}</span>
        <span v-if="champions.speedLeader.label" class="sa-mono sa-tier" :style="{ color: champions.speedLeader.fg, borderColor: champions.speedLeader.fg, textShadow: `0 0 8px ${champions.speedLeader.fg}` }">{{ champions.speedLeader.label }}</span>
        <span class="sa-mono" style="font-size:16px;font-weight:800;flex:none;" :style="{ color: champions.speedLeader.fg }" title="Speed Index (0–10, where 10 = full clean-run pace)">{{ champions.speedLeader.val }}<span style="font-size:10px;color:var(--sa-text-5);">/10</span></span>
      </div>
      <div style="margin-top:6px;display:flex;align-items:center;gap:3px;">
        <div
          v-for="(seg, i) in champions.speedLeader.segments"
          :key="i"
          :style="{ flex: 1, height: '8px', borderRadius: '2px', background: seg.on ? champions.speedLeader.seg : 'rgba(var(--sa-cyan-rgb),.1)', boxShadow: seg.on ? champions.speedLeader.glow : 'none', transition: 'background .5s,box-shadow .5s' }"
        ></div>
      </div>

      <!-- rest -->
      <div style="margin-top:9px;padding-right:14px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="(s, i) in champions.speedRest" :key="i" style="display:flex;align-items:center;gap:9px;">
          <span class="sa-mono" style="font-size:11px;color:var(--sa-text-5);width:14px;text-align:right;flex:none;">{{ s.rank }}</span>
          <span style="font-size:13px;color:#c7dcea;flex:none;width:74px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.name }}</span>
          <span v-if="s.label" class="sa-mono sa-tier-sm" :style="{ color: s.fg, borderColor: s.fg }">{{ s.label }}</span>
          <div style="flex:1;display:flex;align-items:center;gap:2px;">
            <div
              v-for="(seg, j) in s.segments"
              :key="j"
              :style="{ flex: 1, height: '5px', borderRadius: '2px', background: seg.on ? s.seg : 'rgba(var(--sa-cyan-rgb),.1)', boxShadow: seg.on ? s.glow : 'none' }"
            ></div>
          </div>
          <span class="sa-mono" style="font-size:11px;flex:none;" :style="{ color: s.fg }" title="Speed Index (0–10)">{{ s.val }}</span>
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

    <!-- JUST CLEARED (most recently completed tasks, newest first) -->
    <div v-if="champions.showHistory" class="sa-rise">
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:15px;filter:drop-shadow(0 0 6px rgba(var(--sa-violet-rgb),.7));">🕒</span>
        <span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#cbb8ff;">JUST CLEARED</span>
        <span class="sa-mono sa-cap">· tasks completed, newest first</span>
      </div>

      <div v-if="!champions.historyLeader" class="sa-mono" style="color:#6b7a93;font-size:12px;text-align:center;padding:18px 0;">No completions yet</div>

      <template v-else>
        <!-- most recent completion -->
        <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
          <span style="font-size:20px;flex:none;line-height:1;filter:drop-shadow(0 0 8px rgba(var(--sa-violet-rgb),.85));">🕒</span>
          <span style="font-size:20px;font-weight:700;color:#fff;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:none;max-width:210px;">{{ champions.historyLeader.name }}</span>
          <span style="font-size:14px;color:#b6a4dd;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ champions.historyLeader.taskName }}</span>
          <span class="sa-mono" style="font-size:16px;font-weight:800;flex:none;color:var(--sa-violet);" title="Time since completion">{{ champions.historyLeader.ago }}</span>
        </div>
        <div style="margin-top:6px;height:6px;border-radius:4px;background:linear-gradient(90deg,var(--sa-violet),rgba(var(--sa-violet-rgb),.12));box-shadow:0 0 10px rgba(var(--sa-violet-rgb),.45);"></div>

        <!-- earlier completions -->
        <div style="margin-top:9px;padding-right:14px;display:flex;flex-direction:column;gap:6px;">
          <div v-for="h in champions.historyRest" :key="h.id" style="display:flex;align-items:center;gap:9px;">
            <span style="flex:none;width:14px;display:flex;justify-content:center;"><span style="width:5px;height:5px;border-radius:50%;background:var(--sa-violet);box-shadow:0 0 6px rgba(var(--sa-violet-rgb),.6);"></span></span>
            <span style="font-size:13px;color:#d8d0ea;flex:none;width:110px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ h.name }}</span>
            <span style="font-size:13px;color:#9d8fc4;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ h.taskName }}</span>
            <span class="sa-mono" style="font-size:11px;flex:none;color:#b9a6e6;" title="Time since completion">{{ h.ago }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- FINISHERS (only present once someone has cleared every task) -->
    <div v-if="champions.showFinishers" class="sa-rise">
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:15px;filter:drop-shadow(0 0 6px rgba(var(--sa-gold-rgb),.7));">🏁</span>
        <span style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#bdf2cf;">FINISHERS</span>
        <span class="sa-mono" style="font-size:11px;color:var(--sa-text-4);">· {{ champions.finishersCount }} CLEARED</span>
      </div>

      <!-- first to clear -->
      <div v-if="champions.finishersLeader" style="display:flex;align-items:center;gap:10px;margin-top:8px;">
        <span style="font-size:20px;flex:none;line-height:1;filter:drop-shadow(0 0 8px rgba(var(--sa-gold-rgb),.85));">🥇</span>
        <span style="font-size:23px;font-weight:700;color:#fff;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">{{ champions.finishersLeader.name }}</span>
        <span class="sa-mono sa-tier" style="color:var(--sa-gold-bright);border-color:var(--sa-gold-bright);text-shadow:0 0 8px var(--sa-gold-bright);">FIRST TO CLEAR</span>
        <span class="sa-mono" style="font-size:16px;font-weight:800;flex:none;color:var(--sa-gold);" title="Clear time">{{ champions.finishersLeader.clear }}</span>
      </div>
      <div style="margin-top:6px;height:6px;border-radius:4px;background:linear-gradient(90deg,var(--sa-mint),var(--sa-cyan) 60%,var(--sa-gold));box-shadow:0 0 10px rgba(var(--sa-mint-rgb),.5);"></div>

      <!-- everyone else who cleared, in finish order -->
      <div style="margin-top:9px;padding-right:14px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="f in champions.finishersRest" :key="f.id" style="display:flex;align-items:center;gap:9px;">
          <span class="sa-mono" style="font-size:11px;width:14px;text-align:right;flex:none;" :style="{ color: f.medal }">{{ f.rank }}</span>
          <span style="font-size:13px;color:#dfe9d6;flex:none;width:96px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ f.name }}</span>
          <div style="flex:1;height:5px;border-radius:3px;background:rgba(var(--sa-mint-rgb),.5);box-shadow:0 0 6px rgba(var(--sa-mint-rgb),.4);"></div>
          <span class="sa-mono" style="font-size:11px;flex:none;color:#9fd9b4;" title="Clear time">{{ f.clear }}</span>
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
/* Always-on caption explaining a scene's metric — these only had tooltips,
   which never appear on a projected wall display. */
.sa-cap {
  font-size: 11px;
  letter-spacing: 0.3px;
  color: var(--sa-text-4);
  white-space: nowrap;
}
/* Pin toggle: a dim line-icon while auto-rotating, lit gold once the view is
   held. Low profile — no chrome, state reads purely from colour + a soft glow. */
.sa-pin {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3px;
  border-radius: 7px;
  color: var(--sa-text-5);
  transition: color 0.25s, background 0.25s, filter 0.25s;
}
.sa-pin:hover {
  color: var(--sa-text-3);
  background: rgba(var(--sa-cyan-rgb), 0.06);
}
.sa-pin-on {
  color: var(--sa-gold);
  filter: drop-shadow(0 0 5px rgba(var(--sa-gold-rgb), 0.5));
}
.sa-pin-on:hover {
  color: var(--sa-gold);
  background: rgba(var(--sa-gold-rgb), 0.1);
}
.sa-pin:focus-visible {
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
