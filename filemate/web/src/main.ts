import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'

import './style.css'
import './workspace.css'
import './themes.css'
import { initializeAppearance } from './preferences/theme-runtime'

initializeAppearance()

const app = createApp(App)

app.use(createPinia())
app.use(router)

// Keep the public snapshot until its lazy route is ready to replace it.
router.isReady().then(() => app.mount('#app')).catch(() => app.mount('#app'))
