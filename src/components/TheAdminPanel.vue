<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import {
  faDisplay,
  faGraduationCap,
  faScrewdriverWrench,
  faSuitcaseMedical,
} from '@fortawesome/free-solid-svg-icons'

import Exercises from '@/components/adminPanel/Exercises.vue'
import ToolsDiagnostic from '@/components/adminPanel/ToolsDiagnostic.vue'
import ControlButtons from '@/components/adminPanel/ControlButtons.vue'
import { checkUserAuthenticated, userAuthenticated } from '@/socket'
import LoginForm from '@/components/adminPanel/LoginForm.vue'
import { adminPanelOpen } from '@/settings.js'

let authChecher = null
const activeTab = ref('control-panel')

onMounted(() => {
  checkUserAuthenticated()
  authChecher = setInterval(() => {
    checkUserAuthenticated()
  }, 5000)
})
onUnmounted(() => {
  clearInterval(authChecher)
})

</script>

<template>
  <div>
    <!-- Opened from the dashboard header gear icon (settings.js: adminPanelOpen) -->
    <Modal :showModal="adminPanelOpen" @modal-close="adminPanelOpen = false">
      <template #header>
        <h2 class="text-2xl font-bold">
          <FontAwesomeIcon :icon="faScrewdriverWrench" class=""></FontAwesomeIcon>
          Admin panel
        </h2>
      </template>
      <template #body>
        <div v-if="!userAuthenticated">
          <Alert variant="danger">
            You're not authenticated. Please log in to access admin settings
          </Alert>
          <LoginForm></LoginForm>
        </div>
        <div v-else class="dark:text-slate-700 text-slate-700">
          <div class="flex flex-row w-full mx-auto border border-slate-700 rounded-md">
            <div class="inline-flex flex-col bg-slate-300 border-r border-slate-700 p-3 gap-2 rounded-l-md">
                <button
                  @click="activeTab = 'control-panel'"
                  class="text-start btn btn-lg !px-5 !py-3"
                  :class="activeTab === 'control-panel' ? 'btn-primary' : '!text-slate-800 !border-0`'"
                >
                  <FontAwesomeIcon :icon="faDisplay" fixed-size class="mr-2"></FontAwesomeIcon>
                  <span>Control Panel</span>
                </button>
                <button
                  @click="activeTab = 'exercise-panel'"
                  class="text-start btn btn-lg !px-5 !py-3"
                  :class="activeTab === 'exercise-panel' ? 'btn-primary' : '!text-slate-800 !border-0'"
                >
                  <FontAwesomeIcon :icon="faGraduationCap" fixed-size class="mr-2"></FontAwesomeIcon>
                  <span>Exercises</span>
                </button>
                <button
                  @click="activeTab = 'diagnostic-panel'"
                  class="text-start btn btn-lg !px-5 !py-3"
                  :class="activeTab === 'diagnostic-panel' ? 'btn-primary' : '!text-slate-800 !border-0'"
                >
                  <FontAwesomeIcon :icon="faSuitcaseMedical" fixed-size class="mr-2"></FontAwesomeIcon>
                  <span>Diagnostic</span>
                </button>
            </div>
            <div class="p-4 grow">
              <Transition name="fade-slide" mode="out-in" appear>
                <div v-if="activeTab === 'control-panel'">
                  <ControlButtons></ControlButtons>
                </div>
                <div v-else-if="activeTab === 'exercise-panel'">
                  <Exercises></Exercises>
                </div>
                <div v-else-if="activeTab === 'diagnostic-panel'">
                  <ToolsDiagnostic></ToolsDiagnostic>
                </div>
              </Transition>
            </div>
          </div>
        </div>
      </template>
    </Modal>
  </div>

</template>

<style scoped>
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 200ms ease-out;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateX(-8px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(8px);
}
</style>