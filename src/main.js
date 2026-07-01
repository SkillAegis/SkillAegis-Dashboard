import './assets/main.css'

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
