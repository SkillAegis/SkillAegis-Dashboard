<script setup>
/*
 * EvaluationDebug — the shared, read-only renderer of a captured evaluation.
 *
 * Shows ONE check (one task's evaluation) exactly as it was captured at the moment
 * of the triggering action — deliberately not re-run — as an Outcome pill followed
 * by a numbered, colour-grouped step timeline (one group per evaluation parameter),
 * per-step success/fail/error pills, extracted-data dumps with a size/shape header,
 * and — for the `python` strategy — a Status/Exit/Duration table + STDOUT/STDERR.
 *
 * Renders as an overlay (Teleport to body → escapes any transformed ancestor), so
 * it defines the design tokens it needs itself rather than inheriting them from a
 * `.sa-root` ancestor. Emits `close` on ✕ / backdrop / Esc. Opened from the Live
 * Feed pip, the drawer's "View evaluation", and the event-history "Debug".
 */
import { computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  // The check to render — one task's evaluation attempt:
  // { inject_name, result_label, join_type, outcome:1|2, evaluations:[
  //     { evaluation_strategy, result_label, outcome:1|2, score_range, debug } ] }
  check: { type: Object, required: true },
  // The captured Live-Feed reference, for the "as it happened" banner:
  // { origin, time, http_method, url, target_tool }
  trigger: { type: Object, default: null },
  // 'MISP' | 'webhook' — shown in the banner.
  targetTool: { type: String, default: '' },
  // False when the full step trace has rolled out of the retention buffer and
  // only the compact recorded outcome survives — the Debug section then says so
  // instead of showing an empty timeline as if the action ran no checks.
  traceRetained: { type: Boolean, default: true },
})

const emit = defineEmits(['close'])

const OUTCOME_SUCCESS = 1

// Per-step pill glyph/label for success/fail/error steps.
const SPILL = {
  success: { icon: '✓', label: 'Success' },
  fail: { icon: '⚠', label: 'Fail' },
  error: { icon: 'ⓘ', label: 'Error' },
}

const isSuccess = computed(() => props.check?.outcome === OUTCOME_SUCCESS)

const outcome = computed(() =>
  isSuccess.value
    ? { cls: 'ed-outcome-success', icon: '✓', title: 'Successful' }
    : { cls: 'ed-outcome-fail', icon: '⚠', title: 'Failed' },
)

const isHook = computed(
  () => props.trigger?.http_method === 'HOOK' || props.trigger?.origin === 'webhook',
)

// query_mirror has no native trace — one is synthesized. Flag it so the Debug
// header can note as much (honest about the difference).
const hasSynthesized = computed(() =>
  (props.check?.evaluations || []).some((e) => e.evaluation_strategy === 'query_mirror'),
)

// Flatten every evaluation's debug (a list-of-groups) into a single numbered,
// colour-cycled timeline. A python evaluation's group is the raw sandbox result
// (`[{status,exit_code,stdout,stderr,duration}]`, no message/style) — carried
// through with its strategy so the template renders the table instead of steps.
const groups = computed(() => {
  const out = []
  let n = 0
  for (const ev of props.check?.evaluations || []) {
    for (const steps of ev.debug || []) {
      n += 1
      out.push({ n, colorIndex: ((n - 1) % 6) + 1, strategy: ev.evaluation_strategy, steps })
    }
  }
  return out
})

function numStyle(i) {
  return {
    background: `rgb(var(--ed-${i}-rgb))`,
    boxShadow: `0 0 12px rgba(var(--ed-${i}-rgb), .5)`,
  }
}
function hueStyle(i) {
  return { color: `rgb(var(--ed-${i}-rgb))` }
}

// Split a message on backtick-delimited spans so jq paths render monospace (e.g.
// "Testing `.Event.Attribute[]…`"). Backticks are kept for the reader.
function msgSegments(msg) {
  if (!msg) return []
  return String(msg)
    .split(/(`[^`]*`)/)
    .filter((p) => p !== '')
    .map((p) => ({ text: p, mono: p.length >= 2 && p.startsWith('`') && p.endsWith('`') }))
}

// A step's `data` is worth dumping when it's a primitive or a non-empty
// object/array (`{}` on primary/success steps is skipped).
function hasData(step) {
  const d = step?.data
  if (d === null || d === undefined) return false
  if (typeof d === 'object') return Object.keys(d).length > 0
  return true
}

// Over-cap dumps arrive pre-truncated as a raw preview *string* (already JSON text,
// sliced at capture) — show it verbatim. Everything else is a live value → pretty
// JSON.
function dumpText(step) {
  if (step?.data_meta?.truncated) {
    return typeof step.data === 'string' ? step.data : String(step.data)
  }
  try {
    return JSON.stringify(step.data, null, 2)
  } catch {
    return String(step.data)
  }
}

function humanBytes(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return ''
  if (n < 1024) return `${Math.round(n)} B`
  let v = n / 1024
  for (const unit of ['KB', 'MB', 'GB']) {
    if (v < 1024 || unit === 'GB') return `${v.toFixed(1)} ${unit}`
    v /= 1024
  }
  return `${v.toFixed(1)} GB`
}

function pyStatusClass(status) {
  return status === 'success' ? 'ed-pystat-success' : 'ed-pystat-failure'
}

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.body.style.overflow = 'hidden'
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div class="ed-overlay" @click.self="emit('close')">
      <div class="ed-panel" role="dialog" aria-modal="true" aria-label="Captured evaluation">
        <div class="ed-top">
          <span class="ed-eyebrow"><b>◧</b> EVALUATION · CAPTURED ATTEMPT</span>
          <button class="ed-x" type="button" aria-label="Close" @click="emit('close')">✕</button>
        </div>

        <div class="ed-body">
          <!-- captured-context banner: what makes this read-only "as it happened" -->
          <div v-if="trigger" class="ed-trigger">
            <span class="mth" :class="{ 'mth-hook': isHook }">{{ trigger.http_method }}</span>
            <span class="u">{{ trigger.url }}</span>
            <span class="meta">
              · {{ trigger.time }}<template v-if="targetTool"> · {{ targetTool }}</template>
              <template v-if="check.inject_name"> · “{{ check.inject_name }}”</template>
            </span>
            <span class="cap">READ-ONLY · AS CAPTURED</span>
          </div>

          <!-- Outcome pill -->
          <div class="ed-outcome-row">
            <span class="ed-outcome-lbl">Outcome</span>
            <span class="ed-outcome" :class="outcome.cls">
              <span class="ic">{{ outcome.icon }}</span> {{ outcome.title }}
            </span>
          </div>

          <div class="ed-debug-lbl">
            Debug
            <span v-if="!traceRetained" class="ed-note"
              >· full step trace no longer retained — showing the recorded outcome</span
            >
            <span v-else-if="hasSynthesized" class="ed-note"
              >· synthesized — <span class="sa-mono">query_mirror</span> is a pure equality check
              with no native trace</span
            >
          </div>

          <!-- debug timeline: one group per evaluation parameter -->
          <div v-for="g in groups" :key="g.n" class="ed-group">
            <div class="ed-conn"></div>

            <!-- python: raw sandbox result → Status/Exit/Duration + STDOUT/STDERR -->
            <template v-if="g.strategy === 'python'">
              <div class="ed-step">
                <span class="ed-num" :style="numStyle(g.colorIndex)">{{ g.n }}</span>
                <div class="ed-primary" :style="hueStyle(g.colorIndex)">Run python evaluation</div>
                <table class="ed-pytable">
                  <tbody>
                    <tr>
                      <th>Status:</th>
                      <td :class="pyStatusClass(g.steps[0].status)">{{ g.steps[0].status }}</td>
                    </tr>
                    <tr>
                      <th>Exit code:</th>
                      <td>{{ g.steps[0].exit_code }}</td>
                    </tr>
                    <tr>
                      <th>Duration:</th>
                      <td>{{ Number(g.steps[0].duration).toFixed(2) }}s</td>
                    </tr>
                  </tbody>
                </table>
                <div class="ed-std">
                  <span class="h">STDOUT:</span>
                  <pre :class="{ empty: !(g.steps[0].stdout || '').trim() }">{{
                    (g.steps[0].stdout || '').trim() || '(no output)'
                  }}</pre>
                </div>
                <div class="ed-std">
                  <span class="h">STDERR:</span>
                  <pre class="err" :class="{ empty: !(g.steps[0].stderr || '').trim() }">{{
                    (g.steps[0].stderr || '').trim() || '(no output)'
                  }}</pre>
                </div>
              </div>
            </template>

            <!-- data_filtering / query_mirror: {message,data,style} steps -->
            <template v-else>
              <div v-for="(step, si) in g.steps" :key="si" class="ed-step">
                <!-- first step carries the number + the colour-grouped heading -->
                <template v-if="si === 0">
                  <span class="ed-num" :style="numStyle(g.colorIndex)">{{ g.n }}</span>
                  <div
                    v-if="step.style === 'primary'"
                    class="ed-primary"
                    :style="hueStyle(g.colorIndex)"
                  >
                    <template v-for="(seg, k) in msgSegments(step.message)" :key="k"
                      ><span v-if="seg.mono" class="sa-mono">{{ seg.text }}</span
                      ><span v-else>{{ seg.text }}</span></template
                    >
                  </div>
                  <div v-else class="ed-msg">
                    <span v-if="SPILL[step.style]" class="ed-spill" :class="`ed-spill-${step.style}`"
                      >{{ SPILL[step.style].icon }} {{ SPILL[step.style].label }}</span
                    >
                    <span :class="{ 'ed-msg-muted': !step.style }">{{ step.message }}</span>
                  </div>
                </template>

                <!-- subsequent steps: message + optional data dump -->
                <template v-else>
                  <div class="ed-msg">
                    <span v-if="SPILL[step.style]" class="ed-spill" :class="`ed-spill-${step.style}`"
                      >{{ SPILL[step.style].icon }} {{ SPILL[step.style].label }}</span
                    >
                    <span :class="{ 'ed-msg-muted': !step.style }">{{ step.message }}</span>
                  </div>

                  <!-- size & shape header for the extracted data -->
                  <div v-if="step.data_meta" class="ed-meta">
                    <template v-if="step.data_meta.truncated">
                      ↳ <span class="big">{{ humanBytes(step.data_meta.bytes) }}</span> ·
                      {{ step.data_meta.shape }} · <b>{{ step.data_meta.count_label }}</b> — over
                      cap, previewed
                    </template>
                    <template v-else>
                      ↳ {{ humanBytes(step.data_meta.bytes) }} · {{ step.data_meta.shape }} ·
                      {{ step.data_meta.count_label }} — <b>shown in full</b>
                    </template>
                  </div>

                  <pre v-if="hasData(step)" class="ed-pre">{{ dumpText(step) }}</pre>

                  <!-- truncated-at-capture note, or the expected/comparison footnote -->
                  <div v-if="step.data_meta && step.data_meta.truncated" class="ed-trunc warn">
                    ▤ {{ step.data_meta.note }}
                  </div>
                  <div
                    v-else-if="step.expected !== undefined || step.comparison !== undefined"
                    class="ed-trunc"
                  >
                    <template v-if="step.expected !== undefined"
                      >expected one of:
                      <span class="sa-mono">{{ JSON.stringify(step.expected) }}</span></template
                    >
                    <template v-if="step.comparison !== undefined">
                      · comparison: <span class="sa-mono">{{ step.comparison }}</span></template
                    >
                  </div>
                </template>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Design tokens. The overlay teleports to <body>, escaping the dashboard's
   `.sa-root`, so it carries its own token set. The `--sa-*` values match
   src/TheDahboard.vue verbatim; the six `--ed-*` hues are the debug-group cycle
   (cyan/amber/blue/pink/violet/green). */
.ed-overlay {
  --sa-cyan-rgb: 54, 210, 255;
  --sa-mint-rgb: 91, 227, 154;
  --sa-gold-rgb: 255, 205, 91;
  --sa-gold-bright-rgb: 255, 224, 138;
  --sa-violet-rgb: 176, 139, 255;
  --sa-danger-rgb: 255, 107, 107;
  --sa-cyan: rgb(var(--sa-cyan-rgb));
  --sa-mint: rgb(var(--sa-mint-rgb));
  --sa-gold: rgb(var(--sa-gold-rgb));
  --sa-gold-bright: rgb(var(--sa-gold-bright-rgb));
  --sa-violet: rgb(var(--sa-violet-rgb));
  --sa-danger: rgb(var(--sa-danger-rgb));
  --sa-text-1: #eaf3ff;
  --sa-text-2: #cfe3ff;
  --sa-text-3: #9fb4d0;
  --sa-text-4: #7e98ba;
  --sa-text-5: #5f86b0;
  --sa-text-6: #46607f;
  --sa-bg-rgb: 8, 14, 24;
  --sa-ink: #0a1322;
  --ed-1-rgb: 54, 210, 255; /* cyan  */
  --ed-2-rgb: 255, 205, 91; /* amber */
  --ed-3-rgb: 91, 155, 255; /* blue  */
  --ed-4-rgb: 255, 126, 182; /* pink  */
  --ed-5-rgb: 176, 139, 255; /* violet*/
  --ed-6-rgb: 91, 227, 154; /* green */

  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 5vh 20px;
  overflow-y: auto;
  background: rgba(4, 8, 14, 0.72);
  backdrop-filter: blur(4px);
  font-family: 'Space Grotesk', system-ui, sans-serif;
  color: #cdd9ec;
  -webkit-font-smoothing: antialiased;
}
.ed-overlay * {
  box-sizing: border-box;
}
.sa-mono {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}

.ed-panel {
  width: 100%;
  max-width: 960px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  overflow: hidden;
  background: linear-gradient(180deg, rgba(16, 25, 42, 0.99), rgba(9, 14, 25, 0.99));
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.28);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
}
.ed-top {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 20px;
  border-bottom: 1px solid rgba(var(--sa-cyan-rgb), 0.12);
  background: rgba(16, 25, 42, 0.6);
}
.ed-eyebrow {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--sa-text-5);
  font-family: 'JetBrains Mono', monospace;
}
.ed-eyebrow b {
  color: var(--sa-cyan);
}
.ed-x {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--sa-text-4);
  font-size: 14px;
  background: rgba(var(--sa-cyan-rgb), 0.06);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.18);
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s;
}
.ed-x:hover {
  background: rgba(var(--sa-cyan-rgb), 0.14);
  color: var(--sa-text-2);
}

.ed-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 22px 24px;
}

/* captured-context banner */
.ed-trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 10px 13px;
  border-radius: 10px;
  background: rgba(var(--sa-bg-rgb), 0.55);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.12);
}
.ed-trigger .mth {
  font-size: 10px;
  font-weight: 800;
  padding: 3px 7px;
  border-radius: 5px;
  color: var(--sa-mint);
  background: rgba(var(--sa-mint-rgb), 0.14);
  font-family: 'JetBrains Mono', monospace;
}
.ed-trigger .mth-hook {
  color: #d9c690;
  background: rgba(var(--sa-violet-rgb), 0.16);
}
.ed-trigger .u {
  font-size: 12px;
  color: var(--sa-text-2);
  font-family: 'JetBrains Mono', monospace;
}
.ed-trigger .meta {
  font-size: 10.5px;
  color: var(--sa-text-5);
  font-family: 'JetBrains Mono', monospace;
}
.ed-trigger .cap {
  margin-left: auto;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--sa-text-6);
  font-family: 'JetBrains Mono', monospace;
}

/* Outcome pill */
.ed-outcome-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 20px;
}
.ed-outcome-lbl {
  font-size: 13px;
  font-weight: 700;
  color: var(--sa-text-3);
  width: 74px;
}
.ed-outcome {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  padding: 6px 14px;
  border-radius: 10px;
}
.ed-outcome .ic {
  font-size: 14px;
}
.ed-outcome-success {
  color: #d7f7e6;
  background: rgba(var(--sa-mint-rgb), 0.16);
  border: 1px solid rgba(var(--sa-mint-rgb), 0.45);
  box-shadow: 0 0 16px rgba(var(--sa-mint-rgb), 0.15);
}
.ed-outcome-fail {
  color: #ffdede;
  background: rgba(var(--sa-danger-rgb), 0.16);
  border: 1px solid rgba(var(--sa-danger-rgb), 0.45);
  box-shadow: 0 0 16px rgba(var(--sa-danger-rgb), 0.12);
}

/* debug timeline */
.ed-debug-lbl {
  font-size: 13px;
  font-weight: 700;
  color: var(--sa-text-3);
  margin-bottom: 14px;
}
.ed-note {
  margin-left: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: var(--sa-text-5);
}
.ed-note .sa-mono {
  color: var(--sa-gold-bright);
}
.ed-group {
  position: relative;
  margin-bottom: 22px;
}
.ed-group:last-child {
  margin-bottom: 0;
}
.ed-step {
  position: relative;
  padding-left: 48px;
}
.ed-step + .ed-step {
  margin-top: 6px;
}
/* vertical connector between a group's steps */
.ed-group .ed-conn {
  position: absolute;
  left: 15px;
  top: 8px;
  bottom: -14px;
  width: 2px;
  background: rgba(var(--sa-cyan-rgb), 0.18);
}
.ed-group:last-child .ed-conn {
  bottom: 6px;
}
.ed-num {
  position: absolute;
  left: 4px;
  top: 2px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
  color: var(--sa-ink);
  font-family: 'JetBrains Mono', monospace;
  z-index: 1;
}
.ed-primary {
  font-size: 13px;
  font-weight: 700;
}
.ed-msg {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--sa-text-2);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ed-msg-muted {
  color: var(--sa-text-4);
  font-weight: 500;
}
.ed-spill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.3px;
}
.ed-spill-success {
  color: #d7f7e6;
  background: rgba(var(--sa-mint-rgb), 0.16);
  border: 1px solid rgba(var(--sa-mint-rgb), 0.45);
}
.ed-spill-fail,
.ed-spill-error {
  color: #ffdede;
  background: rgba(var(--sa-danger-rgb), 0.16);
  border: 1px solid rgba(var(--sa-danger-rgb), 0.45);
}
.ed-pre {
  margin: 8px 0 0;
  padding: 9px 11px;
  border-radius: 8px;
  font-size: 11px;
  line-height: 1.55;
  font-family: 'JetBrains Mono', monospace;
  color: #8fe3b6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: rgba(var(--sa-bg-rgb), 0.7);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.12);
  max-height: 190px;
  overflow-y: auto;
}
.ed-trunc {
  font-size: 9.5px;
  color: var(--sa-text-6);
  font-family: 'JetBrains Mono', monospace;
  margin-top: 6px;
}
.ed-trunc.warn {
  color: var(--sa-gold);
}
.ed-trunc.warn b {
  color: var(--sa-gold-bright);
}
/* size & shape header above a data dump */
.ed-meta {
  margin: 8px 0 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--sa-text-5);
  padding: 3px 9px;
  border-radius: 6px;
  background: rgba(var(--sa-bg-rgb), 0.55);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.12);
}
.ed-meta b {
  color: var(--sa-text-3);
  font-weight: 700;
}
.ed-meta .big {
  color: var(--sa-gold);
  font-weight: 800;
  letter-spacing: 0.3px;
}
.ed-meta + .ed-pre {
  margin-top: 5px;
}

/* python Status/Exit/Duration table + STDOUT/STDERR */
.ed-pytable {
  margin: 6px 0 10px;
  border-collapse: collapse;
  font-family: 'JetBrains Mono', monospace;
}
.ed-pytable th {
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--sa-text-5);
  padding: 2px 14px 2px 0;
}
.ed-pytable td {
  text-align: right;
  font-size: 11px;
  font-weight: 700;
  color: var(--sa-text-2);
}
.ed-pystat-success {
  color: var(--sa-mint);
}
.ed-pystat-failure {
  color: var(--sa-danger);
}
.ed-std {
  margin-top: 8px;
}
.ed-std .h {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.5px;
  color: var(--sa-text-4);
  font-family: 'JetBrains Mono', monospace;
}
.ed-std pre {
  margin: 4px 0 0;
  padding: 8px 10px;
  border-radius: 7px;
  font-size: 11px;
  line-height: 1.5;
  font-family: 'JetBrains Mono', monospace;
  white-space: pre-wrap;
  max-height: 130px;
  overflow-y: auto;
  background: rgba(var(--sa-bg-rgb), 0.7);
  border: 1px solid rgba(var(--sa-cyan-rgb), 0.1);
  color: var(--sa-text-3);
}
.ed-std pre.err {
  color: #ffc9c9;
  border-color: rgba(var(--sa-danger-rgb), 0.2);
}
.ed-std pre.empty {
  color: var(--sa-text-6);
  font-style: italic;
}

::-webkit-scrollbar {
  width: 9px;
  height: 9px;
}
::-webkit-scrollbar-thumb {
  background: rgba(var(--sa-cyan-rgb), 0.18);
  border-radius: 6px;
}
@media (prefers-reduced-motion: reduce) {
  .ed-x {
    transition: none;
  }
}
</style>
