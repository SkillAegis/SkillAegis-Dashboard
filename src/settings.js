import { ref } from 'vue'

export const fullscreenModeOn = ref(false)

// Manual "reduce motion" override, toggled from the admin panel. Adds
// `reduce-motion` to <body> (see main.css), neutralizing animations app-wide on
// top of the OS `prefers-reduced-motion` setting.
export const reduceMotionOn = ref(false)

// Drives the admin panel modal so it can be opened from the dashboard header gear.
export const adminPanelOpen = ref(false)
export function openAdminPanel() {
  adminPanelOpen.value = true
}
