'use client'
import * as React from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  SquarePen, Search, Trash2, Pencil, Check, X, PanelLeftClose, MoreHorizontal,
  Settings, LogOut, Shield, User as UserIcon, Bot,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { ConversationRecord } from '@/lib/types'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuLabel,
} from '@/components/ui/dropdown-menu'
import { useDebounce } from 'use-debounce'
import { toast } from 'sonner'

function groupLabel(iso?: string | null): string {
  if (!iso) return 'Previous 30 Days'
  const d = new Date(iso)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const day = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.floor((today.getTime() - day.getTime()) / 86_400_000)
  if (diff <= 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  if (diff <= 7) return 'Previous 7 Days'
  return 'Previous 30 Days'
}

const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days']

export function Sidebar() {
  const router = useRouter()
  const pathname = usePathname()
  const qc = useQueryClient()
  const { user, logout } = useAuthStore()
  const collapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggleCollapsed = useUIStore((s) => s.toggleCollapsed)
  const [searchOpen, setSearchOpen] = React.useState(false)
  const [q, setQ] = React.useState('')
  const [dq] = useDebounce(q, 250)
  const [editingId, setEditingId] = React.useState<string | null>(null)
  const [editingTitle, setEditingTitle] = React.useState('')

  const convosQ = useQuery({
    queryKey: ['conversations', dq],
    queryFn: async () =>
      (await api.get<ConversationRecord[]>('/chat/conversations', { params: { q: dq || undefined } })).data,
  })

  const remove = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/chat/conversations/${id}`) },
    onSuccess: (_v, id) => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      if (pathname === `/c/${id}`) router.push('/c')
      if (pathname === `/agent/${id}`) router.push('/agent')
    },
  })

  const rename = useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) =>
      (await api.patch<ConversationRecord>(`/chat/conversations/${id}`, { title })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      setEditingId(null)
    },
    onError: () => toast.error('Rename failed'),
  })

  const grouped = React.useMemo(() => {
    const map = new Map<string, ConversationRecord[]>()
    for (const c of convosQ.data || []) {
      const label = groupLabel(c.updatedAt)
      const list = map.get(label) || []
      list.push(c)
      map.set(label, list)
    }
    return GROUP_ORDER.filter((g) => map.has(g)).map((g) => ({ label: g, items: map.get(g)! }))
  }, [convosQ.data])

  if (collapsed) return null

  return (
    <aside className="flex h-full w-[260px] shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      {/* Logo + collapse */}
      <div className="flex items-center justify-between px-2 pb-1 pt-2.5">
        <Link
          href="/c"
          className="grid h-9 w-9 place-items-center rounded-lg transition-colors hover:bg-black/5 dark:hover:bg-white/10"
          aria-label="Home"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="" className="h-6 w-6 rounded-md object-contain" />
        </Link>
        <button
          onClick={toggleCollapsed}
          className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-black/5 dark:hover:bg-white/10"
          aria-label="Close sidebar"
        >
          <PanelLeftClose className="h-5 w-5" />
        </button>
      </div>

      {/* New chat / search */}
      <div className="space-y-0.5 px-2 pt-1">
        <Link
          href="/c"
          className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-black/5 dark:hover:bg-white/10"
        >
          <SquarePen className="h-4 w-4" /> New chat
        </Link>
        <Link
          href="/agent"
          className={cn(
            'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-black/5 dark:hover:bg-white/10',
            pathname === '/agent' && 'bg-black/10 dark:bg-white/10'
          )}
        >
          <Bot className="h-4 w-4" /> Worm Agent
        </Link>
        <button
          onClick={() => setSearchOpen((v) => !v)}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-black/5 dark:hover:bg-white/10"
        >
          <Search className="h-4 w-4" /> Search chats
        </button>
        {searchOpen && (
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search…"
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring"
          />
        )}
      </div>

      {/* Conversations */}
      <div className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-2">
        {!dq && grouped.length > 0 && (
          <div className="px-2.5 pb-1.5 pt-4 text-xs font-medium text-muted-foreground">Chats</div>
        )}
        {grouped.map((group) => (
          <div key={group.label} className="pt-2">
            <div className="px-2.5 pb-1 text-xs font-medium text-muted-foreground">{group.label}</div>
            <div className="space-y-0.5">
              {group.items.map((c) => {
                const href = c.mode === 'agent' ? `/agent/${c.id}` : `/c/${c.id}`
                const active = pathname === href
                return (
                  <div
                    key={c.id}
                    className={cn(
                      'group relative rounded-lg transition-colors',
                      active ? 'bg-black/10 dark:bg-white/10' : 'hover:bg-black/5 dark:hover:bg-white/5'
                    )}
                  >
                    {editingId === c.id ? (
                      <div className="flex items-center gap-1 px-2 py-1">
                        <input
                          autoFocus
                          value={editingTitle}
                          onChange={(e) => setEditingTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && editingTitle.trim())
                              rename.mutate({ id: c.id, title: editingTitle.trim() })
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                          className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm outline-none"
                        />
                        <button
                          onClick={() => editingTitle.trim() && rename.mutate({ id: c.id, title: editingTitle.trim() })}
                          className="p-1 text-muted-foreground hover:text-foreground"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button onClick={() => setEditingId(null)} className="p-1 text-muted-foreground hover:text-foreground">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : (
                      <>
                        <Link href={href} className="block truncate px-2.5 py-2 text-sm">
                          <span className="inline-flex max-w-full items-center gap-1.5">
                            {c.mode === 'agent' && <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                            <span className="truncate">{c.title || 'New chat'}</span>
                          </span>
                        </Link>
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            className={cn(
                              'absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground transition-opacity hover:text-foreground',
                              active ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                            )}
                            aria-label="Chat options"
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="start" side="right" className="w-40">
                            <DropdownMenuItem onClick={() => { setEditingId(c.id); setEditingTitle(c.title) }}>
                              <Pencil className="h-3.5 w-3.5" /> Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => remove.mutate(c.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" /> Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
        {convosQ.data?.length === 0 && (
          <div className="px-2.5 pt-6 text-center text-xs text-muted-foreground">
            {dq ? 'No results' : 'No chats yet'}
          </div>
        )}
      </div>

      {/* Credits + user menu */}
      <div className="border-t border-black/5 p-2 dark:border-white/5">
        <div className="mb-1.5 px-2 text-center text-[10px] leading-4 text-muted-foreground/70">
          Powered by internal models —{' '}
          <a href="https://3mh.pages.dev/" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
            3MH Technologies
          </a>
          {' · '}
          <a href="https://t.me/j49_c" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
            t.me/j49_c
          </a>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-black/5 dark:hover:bg-white/10">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              {(user?.username || '?').slice(0, 1).toUpperCase()}
            </div>
            <span className="flex-1 truncate text-left">{user?.username}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" className="w-56">
            <DropdownMenuLabel className="truncate font-normal text-muted-foreground">{user?.email}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => router.push('/profile')}>
              <UserIcon className="h-4 w-4" /> Profile
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push('/settings')}>
              <Settings className="h-4 w-4" /> Settings
            </DropdownMenuItem>
            {user?.role && ['admin', 'superadmin', 'developer'].includes(user.role) && (
              <DropdownMenuItem onClick={() => router.push('/admin')}>
                <Shield className="h-4 w-4" /> Admin panel
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={async () => { await logout(); router.push('/login') }}>
              <LogOut className="h-4 w-4" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  )
}
