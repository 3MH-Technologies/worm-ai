'use client'
import * as React from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronDown, LogOut, User as UserIcon, Settings, Sun, Moon, Laptop,
  PanelLeftOpen, SquarePen, Share2, Bot,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useUIStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem,
} from '@/components/ui/dropdown-menu'
import { ModelRecord, AgentModelRecord } from '@/lib/types'
import { toast } from 'sonner'

export function TopBar() {
  const router = useRouter()
  const pathname = usePathname()
  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)
  const selectedModelId = useUIStore((s) => s.selectedModelId)
  const setModel = useUIStore((s) => s.setModel)
  const selectedAgentModel = useUIStore((s) => s.selectedAgentModel)
  const setAgentModel = useUIStore((s) => s.setAgentModel)
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggleCollapsed = useUIStore((s) => s.toggleCollapsed)
  const { user, logout } = useAuthStore()

  const inAgent = (pathname || '').startsWith('/agent')

  const modelsQ = useQuery({
    queryKey: ['models'],
    queryFn: async () => (await api.get<ModelRecord[]>('/models')).data,
    staleTime: 60_000,
    enabled: !inAgent,
  })

  const agentModelsQ = useQuery({
    queryKey: ['agent-models'],
    queryFn: async () => (await api.get<AgentModelRecord[]>('/agent/models')).data,
    staleTime: 60_000,
    enabled: inAgent,
  })

  const models = modelsQ.data || []
  const selected =
    models.find((m) => m.id === selectedModelId) || models.find((m) => m.id === 'C') || models[0]
  const agentModels = agentModelsQ.data || []
  const selectedAgent =
    agentModels.find((m) => m.id === selectedAgentModel) || agentModels[0]
  const inConversation = /^\/(c|agent)\/.+/.test(pathname || '')

  async function shareChat() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      toast.success('Link copied to clipboard')
    } catch {
      toast.error('Could not copy link')
    }
  }

  return (
    <header className="relative z-10 flex h-14 shrink-0 items-center justify-between px-3">
      <div className="flex items-center gap-1">
        {sidebarCollapsed && (
          <>
            <button
              onClick={toggleCollapsed}
              className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent"
              aria-label="Open sidebar"
            >
              <PanelLeftOpen className="h-5 w-5" />
            </button>
            <button
              onClick={() => router.push('/c')}
              className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent"
              aria-label="New chat"
            >
              <SquarePen className="h-5 w-5" />
            </button>
          </>
        )}

        {/* Model picker — ChatGPT style for chat, Worm Agent picker in agent mode */}
        {inAgent ? (
          <DropdownMenu>
            <DropdownMenuTrigger className="flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-lg font-semibold transition-colors hover:bg-accent focus-visible:outline-none">
              <Bot className="h-5 w-5" />
              <span>{selectedAgent?.name || 'Worm Agent'}</span>
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-80 rounded-2xl p-1.5">
              <DropdownMenuRadioGroup value={selectedAgent?.id || ''} onValueChange={(v) => setAgentModel(v)}>
                {agentModels.map((m) => (
                  <DropdownMenuRadioItem
                    key={m.id}
                    value={m.id}
                    className="flex items-start gap-2 rounded-xl px-3 py-2.5"
                  >
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="text-sm font-medium">{m.name}</span>
                      {m.description && (
                        <span className="text-xs text-muted-foreground">{m.description}</span>
                      )}
                    </div>
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
              {agentModels.length === 0 && (
                <div className="px-3 py-4 text-center text-sm text-muted-foreground">Loading…</div>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <DropdownMenu>
            <DropdownMenuTrigger className="flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-lg font-semibold transition-colors hover:bg-accent focus-visible:outline-none">
              <span>{selected?.displayName || selected?.name || 'Worm Core'}</span>
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-80 rounded-2xl p-1.5">
              <DropdownMenuRadioGroup value={selected?.id || ''} onValueChange={(v) => setModel(v)}>
                {models.map((m) => (
                  <DropdownMenuRadioItem
                    key={m.id}
                    value={m.id}
                    className="flex items-start gap-2 rounded-xl px-3 py-2.5"
                  >
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="text-sm font-medium">{m.displayName || m.name}</span>
                      {m.description && (
                        <span className="text-xs text-muted-foreground">{m.description}</span>
                      )}
                    </div>
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
              {models.length === 0 && (
                <div className="px-3 py-4 text-center text-sm text-muted-foreground">Loading models…</div>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <div className="flex items-center gap-2">
        {inConversation && (
          <button
            onClick={shareChat}
            className="flex items-center gap-1.5 rounded-full border border-border px-3.5 py-1.5 text-sm font-medium transition-colors hover:bg-accent"
          >
            <Share2 className="h-4 w-4" /> Share
          </button>
        )}

        {/* Avatar menu */}
        <DropdownMenu>
          <DropdownMenuTrigger className="grid h-9 w-9 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground focus-visible:outline-none">
            {(user?.username || '?').slice(0, 1).toUpperCase()}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60 rounded-2xl p-1.5">
            <DropdownMenuLabel className="truncate px-3 py-2 font-normal text-muted-foreground">
              {user?.email}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => router.push('/profile')} className="rounded-lg px-3 py-2">
              <UserIcon className="h-4 w-4" /> Profile
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push('/settings')} className="rounded-lg px-3 py-2">
              <Settings className="h-4 w-4" /> Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="px-3 py-1 text-xs text-muted-foreground">Theme</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as any)}>
              <DropdownMenuRadioItem value="light" className="rounded-lg px-3 py-2">
                <Sun className="h-4 w-4" /> Light
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark" className="rounded-lg px-3 py-2">
                <Moon className="h-4 w-4" /> Dark
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system" className="rounded-lg px-3 py-2">
                <Laptop className="h-4 w-4" /> System
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={async () => { await logout(); router.push('/login') }}
              className="rounded-lg px-3 py-2"
            >
              <LogOut className="h-4 w-4" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
