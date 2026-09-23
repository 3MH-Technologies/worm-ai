'use client'
import * as React from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Search as SearchIcon, MessageSquare, FileText, Bot, User as UserIcon, Hash, NotebookPen } from 'lucide-react'
import { useDebounce } from 'use-debounce'
import { api } from '@/lib/api'
import { SearchHit, SearchResponse } from '@/lib/types'
import { Sidebar } from '@/components/layout/sidebar'
import { TopBar } from '@/components/layout/topbar'

const ICONS: Record<SearchHit['kind'], any> = {
  conversation: MessageSquare,
  message: MessageSquare,
  model: Bot,
  canvas: FileText,
  memory: NotebookPen,
  user: UserIcon,
}

export default function SearchPage() {
  const [q, setQ] = React.useState('')
  const [dq] = useDebounce(q, 200)
  const sQ = useQuery<SearchResponse>({
    queryKey: ['search', dq],
    queryFn: async () => (await api.get('/search', { params: { q: dq } })).data,
    enabled: dq.length >= 2,
  })

  return (
    <>
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar />
        <div className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-2xl">
            <h1 className="mb-3 text-xl font-semibold">Search</h1>
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search everything…" className="h-11 pl-9" />
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              {sQ.data && `${sQ.data.hits.length} results in ${sQ.data.took_ms}ms`}
            </div>
            <div className="mt-3 space-y-2">
              {(sQ.data?.hits || []).map((h) => {
                const Icon = ICONS[h.kind] || Hash
                const href =
                  h.kind === 'conversation' ? `/c/${h.id}` :
                  h.kind === 'message' ? `/c/${h.extra.conversationId}` :
                  h.kind === 'canvas' ? `/canvas/${h.id}` :
                  h.kind === 'model' ? '/c' :
                  h.kind === 'user' ? `/admin/users?q=${encodeURIComponent(h.title)}` :
                  '/settings'
                return (
                  <Link key={h.kind + h.id} href={href}>
                    <Card className="transition-colors hover:bg-accent/40">
                      <CardContent className="flex items-start gap-3 p-3">
                        <Icon className="mt-0.5 h-4 w-4 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="truncate text-sm font-medium">{h.title}</span>
                            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">{h.kind}</span>
                          </div>
                          <p className="line-clamp-2 text-xs text-muted-foreground">{h.snippet}</p>
                        </div>
                        <span className="text-[10px] text-muted-foreground">{(h.score * 100).toFixed(0)}%</span>
                      </CardContent>
                    </Card>
                  </Link>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
