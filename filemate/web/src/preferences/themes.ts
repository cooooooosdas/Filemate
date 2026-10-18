export type ThemeId = 'blue-gray' | 'mist' | 'graphite' | 'midnight'
export type ThemePreference = ThemeId | 'system'
export interface Theme { id: ThemeId; name: string; description: string; dark: boolean; colors: Record<string, string> }

const base = {
  'bg-base': '#c1cddd', 'workspace-background': '#c1cddd', 'bg-surface': '#f0f3f8',
  'bg-reading': '#f0f3f8', 'bg-elevated': '#e8edf5', 'bg-hover': '#dbe4f2',
  'text-primary': '#16243b', 'text-secondary': '#34465f', 'text-muted': '#45556d',
  'accent': '#254bc3', 'accent-hover': '#19388f', 'accent-soft': '#dfe7fa', 'accent-border': '#8fa5d8',
  'action-fill': '#254bc3', 'action-hover': '#19388f',
  'success': '#235c3f', 'warning': '#72460e', 'danger': '#8b3034',
  'border-subtle': '#a5b3c8', 'border-default': '#7b8da9', 'border-strong': '#7b8da9',
  'panel-tint': '#d2deef', 'hero-background': '#183a7e', 'hero-highlight': '#bdd3fb',
  'hero-ink': '#f4f7fd', 'hero-copy': '#e0e8fb', 'header-surface': '#cdd7e5',
  'sidebar-surface': '#14243e', 'sidebar-hover': '#243c5e', 'sidebar-ink': '#f4f7fd',
  'sidebar-secondary': '#e1e8f5', 'sidebar-muted': '#becce0', 'sidebar-line': '#405474',
}
export const themes: Theme[] = [
  { id: 'blue-gray', name: '蓝灰工作台', description: '有层次的蓝灰，清晰沉稳', dark: false, colors: { ...base } },
  { id: 'mist', name: '晴空浅蓝', description: '明亮蓝白，适合白天阅读', dark: false, colors: {
    ...base, 'bg-base': '#e4ebf5', 'workspace-background': '#e4ebf5', 'bg-surface': '#ffffff', 'bg-reading': '#ffffff',
    'bg-elevated': '#edf2fa', 'bg-hover': '#dae5f6', 'header-surface': '#edf2fa', 'panel-tint': '#dbe7f8',
    'hero-background': '#244b8b', 'sidebar-surface': '#1b3355', 'sidebar-hover': '#2c4b72',
  } },
  { id: 'graphite', name: '石墨灰蓝', description: '低饱和灰蓝，减少色彩干扰', dark: false, colors: {
    ...base, 'bg-base': '#cbd0d8', 'workspace-background': '#cbd0d8', 'bg-surface': '#f2f3f5', 'bg-reading': '#f2f3f5',
    'bg-elevated': '#e7eaef', 'bg-hover': '#dbe0e8', 'panel-tint': '#d9dfe9', 'header-surface': '#dadee5',
    'hero-background': '#354963', 'hero-highlight': '#c5d5ec', 'sidebar-surface': '#252f40', 'sidebar-hover': '#38485e',
    'accent': '#294f86', 'accent-hover': '#193b69', 'action-fill': '#294f86', 'action-hover': '#193b69', 'accent-soft': '#dce4f0',
  } },
  { id: 'midnight', name: '午夜深蓝', description: '深色工作区，适合夜间使用', dark: true, colors: {
    ...base, 'bg-base': '#101a2c', 'workspace-background': '#101a2c', 'bg-surface': '#1b2940', 'bg-reading': '#1b2940',
    'bg-elevated': '#24354e', 'bg-hover': '#304665', 'header-surface': '#17243a', 'panel-tint': '#283c59',
    'text-primary': '#edf3ff', 'text-secondary': '#cedaec', 'text-muted': '#b4c5dd',
    'accent': '#a9c9ff', 'accent-hover': '#d2e1ff', 'accent-soft': '#293c58', 'accent-border': '#708fbe',
    'action-fill': '#3158b9', 'action-hover': '#274ba4',
    'success': '#9ee0bb', 'warning': '#f0cf99', 'danger': '#ffb8ba',
    'border-subtle': '#516584', 'border-default': '#7086a7', 'border-strong': '#7086a7',
    'hero-background': '#203b6d', 'sidebar-surface': '#101b2e',
  } },
]

export function normalizeTheme(value: unknown): ThemePreference {
  return value === 'system' || themes.some(theme => theme.id === value) ? value as ThemePreference : 'blue-gray'
}

interface Media { readonly matches: boolean; addEventListener(type: 'change', listener: () => void): void; removeEventListener(type: 'change', listener: () => void): void }
export function createThemeController(storage: Pick<Storage, 'getItem' | 'setItem'>, media: Media, apply: (theme: Theme, preference: ThemePreference) => void) {
  let preference: ThemePreference = 'blue-gray'
  try { preference = normalizeTheme(storage.getItem('filemate-appearance')) } catch { /* Storage may be disabled by the browser. */ }
  const render = () => apply(themes.find(theme => theme.id === (preference === 'system' ? (media.matches ? 'midnight' : 'blue-gray') : preference))!, preference)
  render()
  media.addEventListener('change', render)
  return {
    select(value: unknown): boolean {
      preference = normalizeTheme(value); render()
      try { storage.setItem('filemate-appearance', preference); return true } catch { return false }
    },
    sync(value: unknown): void { preference = normalizeTheme(value); render() },
    dispose(): void { media.removeEventListener('change', render) },
  }
}
