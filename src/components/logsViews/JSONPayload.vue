<script setup>
import { ref, computed, onMounted, watch } from 'vue'

const props = defineProps({
    payload: {
        type: [Object, String],
        required: true
    }
})
const collapsed = ref(true)
const shouldShowToggle = ref(false)
const prePayload = ref(null)
const isPayloadString = computed(() => typeof props.payload === 'string')

const prettyJson = computed(() =>
    isPayloadString.value ? props.payload : JSON.stringify(props.payload, null, 2)
)
const jsonKeyAmount = computed(() =>
    Object.keys(props.payload).length
)

// Check if content is taller than the collapsed max height
const checkOverflow = () => {
  const el = prePayload.value
  if (el) {
    // Temporarily expand to measure full height
    el.classList.remove('max-h-[6em]', 'overflow-hidden')
    const fullHeight = el.scrollHeight

    // Reset to collapsed state for measurement
    el.classList.add('max-h-[6em]', 'overflow-hidden')
    const collapsedHeight = el.clientHeight

    shouldShowToggle.value = fullHeight > collapsedHeight
  }
}

onMounted(() => {
  checkOverflow()
})

// Optional: Re-check if jsonData changes
watch(prettyJson, () => {
  checkOverflow()
})
</script>


<template>
    <div
        class="border border-slate-200 dark:border-slate-600 bg-slate-100 dark:bg-slate-600 rounded-md relative">
        <pre
            ref="prePayload"
            class="p-1 text-xs font-mono max-w-lg truncate whitespace-pre overflow-hidden"
            :class="{ 'max-h-[6rem] overflow-hidden': collapsed, 'max-h-full': !collapsed }"
            >{{ prettyJson }}</pre>
        <div
            class="absolute flex justify-center bottom-0 left-0 right-0 h-6 rounded-b-md"
            :class="{ 'backdrop-blur-sm': collapsed && shouldShowToggle }"
        >
            <button
                v-if="shouldShowToggle"
                @click="collapsed = !collapsed"
                class="text-cyan-800 text-sm hover:underline focus:outline-none font-retrogaming"
                :class="collapsed ? 'text-cyan-900 dark:text-cyan-950' : 'text-cyan-500'"
            >
                <span v-if="isPayloadString">{{ collapsed ? 'Show more' : 'Show less' }}</span>
                <span v-else>{{ collapsed ? `Show more (${jsonKeyAmount} keys)` : 'Show less' }}</span>
            </button>
        </div>
    </div>
</template>
