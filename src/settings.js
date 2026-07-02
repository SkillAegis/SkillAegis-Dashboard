import { ref } from 'vue'

export const fullscreenModeOn = ref(false)

// Drives the admin panel modal so it can be opened from the dashboard header gear.
export const adminPanelOpen = ref(false)
export function openAdminPanel() {
  adminPanelOpen.value = true
}
