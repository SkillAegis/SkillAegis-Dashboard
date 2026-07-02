<script setup>
import { onMounted } from 'vue'
import TheAdminPanel from './components/TheAdminPanel.vue'
import TheDahboard from './TheDahboard.vue'
import Toaster from '@/components/elements/Toaster.vue'
import { socketConnected, checkUserAuthenticated } from './socket'

onMounted(() => {
  checkUserAuthenticated()
})
</script>

<template>
  <main>
    <div class="background-logo"></div>
    <div class="absolute top-0 right-0 z-10">
      <TheAdminPanel></TheAdminPanel>
    </div>
    <div>
      <TheDahboard></TheDahboard>
    </div>
    <Toaster></Toaster>
  </main>
</template>

<style>
body {
  @apply bg-slate-200;
  @apply dark:bg-gray-700;
  @apply text-slate-400;
  @apply dark:text-slate-300;
}

@font-face {
  font-family: retrogaming;
  src: url('@/assets/fonts/Retro Gaming.ttf');
}

@font-face {
  font-family: Xolonium-Bold;
  src: url('@/assets/fonts/Xolonium-Bold.otf');
}

.background-logo {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background-image: url(@/assets/skillaegis-logo.svg);
  background-size: 90vh;
  background-repeat: no-repeat;
  background-position-x: center;
  background-position-y: center;
  filter: grayscale(50%) drop-shadow(5px 5px 5px #000);;
  opacity: 0.25;
  z-index: -1;
}
</style>
