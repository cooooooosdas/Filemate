import { ref, shallowRef } from 'vue'
import { createThemeController, themes, type ThemePreference } from './themes'

export const themePreference = ref<ThemePreference>('blue-gray')
export const currentTheme = shallowRef(themes[0]!)
let controller: ReturnType<typeof createThemeController> | undefined

export function initializeAppearance(): void {
  if (controller) return
  const storage = { getItem: (key: string) => window.localStorage.getItem(key), setItem: (key: string, value: string) => window.localStorage.setItem(key, value) }
  controller = createThemeController(storage, window.matchMedia('(prefers-color-scheme: dark)'), (theme, preference) => {
    themePreference.value = preference; currentTheme.value = theme
    const root = document.documentElement
    for (const [key, value] of Object.entries(theme.colors)) root.style.setProperty(`--${key}`, value)
    root.dataset.theme = theme.id
    root.style.colorScheme = theme.dark ? 'dark' : 'light'
  })
  window.addEventListener('storage', event => { if (event.key === 'filemate-appearance' || event.key === null) controller?.sync(event.newValue) })
}

export function selectAppearance(value: ThemePreference): boolean {
  initializeAppearance()
  return controller!.select(value)
}
