import './assets/main.css'

// Self-hosted fonts (replaces the Google Fonts CDN). Weights match prior usage:
// Space Grotesk 400/500/600/700, JetBrains Mono 400/500/700/800.
import '@fontsource/space-grotesk/400.css'
import '@fontsource/space-grotesk/500.css'
import '@fontsource/space-grotesk/600.css'
import '@fontsource/space-grotesk/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/700.css'
import '@fontsource/jetbrains-mono/800.css'

import { createApp, ref } from 'vue'
import App from './App.vue'

import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import Modal from '@/components/elements/Modal.vue'
import Loading from '@/components/elements/Loading.vue'
import Alert from '@/components/elements/Alert.vue'

document.title = import.meta.env.VITE_APP_TITLE

const app = createApp(App)
app.component('FontAwesomeIcon', FontAwesomeIcon)
app.component('Modal', Modal)
app.component('Loading', Loading)
app.component('Alert', Alert)

app.mount('#app')
