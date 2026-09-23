'use client'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UIState {
  sidebarOpen: boolean
  sidebarCollapsed: boolean
  theme: 'light' | 'dark' | 'system'
  selectedModelId: string | null
  selectedAgentModel: string
  toggleSidebar: () => void
  toggleCollapsed: () => void
  setTheme: (t: UIState['theme']) => void
  setModel: (id: string | null) => void
  setAgentModel: (id: string) => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      sidebarCollapsed: false,
      theme: 'system',
      selectedModelId: 'C',
      selectedAgentModel: 'deepseek-chat',
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      toggleCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setTheme: (t) => set({ theme: t }),
      setModel: (id) => set({ selectedModelId: id }),
      setAgentModel: (id) => set({ selectedAgentModel: id }),
    }),
    { name: 'wormgpt.ui' }
  )
)
