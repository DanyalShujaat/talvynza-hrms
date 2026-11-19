import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'
interface UiState {
  theme: Theme
  setTheme: (t: Theme) => void
}

export const applyTheme = (t: Theme) => {
  const dark = t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
}

// UI preferences only. Never business data: the database is the source of truth.
export const useUi = create<UiState>()(
  persist(
    (set) => ({
      theme: 'system',
      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },
    }),
    { name: 'talvynza-ui' },
  ),
)
