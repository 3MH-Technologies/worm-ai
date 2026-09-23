'use client'
import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useRouter } from 'next/navigation'
import { api, getAccessToken } from '@/lib/api'
import { Sidebar } from '@/components/layout/sidebar'
import { TopBar } from '@/components/layout/topbar'
import { Composer, ComposerAttachment } from '@/components/chat/composer'
import { MessageBubble } from '@/components/chat/message'
import { ConversationRecord, ConversationWithMessages, MessageRecord } from '@/lib/types'
import { ArrowDown, Bot, AlertTriangle } from 'lucide-react'
import { useUIStore } from '@/stores/ui'
import { toast } from 'sonner'

interface LiveTool {
  id: string
  name: string
  summary: string
  ok: boolean
  running: boolean
}

export default function AgentPage() {
  const params = useParams<{ id?: string }>()
  const router = useRouter()
  const id = params?.id
  const qc = useQueryClient()
  const selectedAgentModel = useUIStore((s) => s.selectedAgentModel)
  const scrollRef = React.useRef<HTMLDivElement>(null)
  const abortRef = React.useRef<AbortController | null>(null)
  const [streaming, setStreaming] = React.useState(false)
  const [streamText, setStreamText] = React.useState('')
  const [streamThinking, setStreamThinking] = React.useState('')
  const [liveTools, setLiveTools] = React.useState<LiveTool[]>([])
  const [autoScroll, setAutoScroll] = React.useState(true)
  const [composerValue, setComposerValue] = React.useState('')

  const convQ = useQuery({
    queryKey: ['conversation', id],
    queryFn: async () => (await api.get<ConversationWithMessages>(`/chat/conversations/${id}`)).data,
    enabled: !!id,
  })

  const statusQ = useQuery({
    queryKey: ['agent-status'],
    queryFn: async () => (await api.get<{ configured: boolean }>('/agent/status')).data,
    staleTime: 60_000,
  })

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight
    setAutoScroll(dist < 80)
  }

  React.useEffect(() => {
    if (autoScroll) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: streaming ? 'auto' : 'smooth' })
  }, [convQ.data?.messages, streamText, liveTools, autoScroll, streaming])

  function readCsrfToken(): string | null {
    if (typeof document === 'undefined') return null
    const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
    return match ? decodeURIComponent(match[1]) : null
  }

  async function sendMessage(content: string, opts: { attachments?: ComposerAttachment[]; regenerate?: boolean } = {}) {
    if (!id) return
    const isRegen = !!opts.regenerate
    if (!isRegen && !content.trim()) return
    setAutoScroll(true)
    if (!isRegen) {
      const userMsg: MessageRecord = {
        id: `tmp-${Date.now()}`, conversationId: id, role: 'user', content,
        metadata: {}, createdAt: new Date().toISOString(),
        tokens: null, model: null, reaction: null, parentId: null,
      }
      qc.setQueryData<ConversationWithMessages>(['conversation', id], (prev) =>
        prev ? { ...prev, messages: [...prev.messages, userMsg] } : prev
      )
    } else {
      qc.setQueryData<ConversationWithMessages>(['conversation', id], (prev) => {
        if (!prev) return prev
        const msgs = [...prev.messages]
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'assistant') { msgs.splice(i, 1); break }
        }
        return { ...prev, messages: msgs }
      })
    }
    setStreamText('')
    setStreamThinking('')
    setLiveTools([])
    setStreaming(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const token = getAccessToken()
      const csrf = readCsrfToken()
      const res = await fetch(`/api/v1/agent/conversations/${id}/stream`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(csrf ? { 'x-csrf-token': csrf } : {}),
        },
        body: JSON.stringify({
          content,
          modelId: selectedAgentModel,
          role: 'user',
          regenerate: isRegen,
        }),
      })
      if (!res.ok || !res.body) {
        let msg = `HTTP ${res.status}`
        try {
          const d = await res.json()
          msg = d?.error || d?.detail || msg
        } catch { /* ignore */ }
        throw new Error(msg)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''
        for (const evt of events) {
          const lines = evt.split('\n')
          let event = ''
          let data = ''
          for (const line of lines) {
            if (line.startsWith('event:')) {
              event = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              data = line.slice(5).trim()
            }
          }
          if (!event && !data) continue
          try {
            const payload = data ? JSON.parse(data) : {}
            if (event === 'delta' && payload.text) {
              setStreamText((t) => t + payload.text)
            } else if (event === 'thinking' && payload.text) {
              setStreamThinking((t) => t + payload.text)
            } else if (event === 'tool') {
              setLiveTools((prev) => [
                ...prev,
                { id: payload.id || String(prev.length), name: payload.name || 'tool', summary: 'running…', ok: true, running: true },
              ])
            } else if (event === 'tool_result') {
              setLiveTools((prev) =>
                prev.map((t) =>
                  t.id === payload.id
                    ? { ...t, summary: payload.summary || '', ok: payload.ok !== false, running: false }
                    : t
                )
              )
            } else if (event === 'error') {
              toast.error(payload.message || 'agent error')
            }
          } catch { /* malformed JSON, skip */ }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        toast.error(e?.message || 'agent stream failed')
      }
    } finally {
      abortRef.current = null
      setStreaming(false)
      setStreamText('')
      setStreamThinking('')
      setLiveTools([])
      qc.invalidateQueries({ queryKey: ['conversation', id] })
      qc.invalidateQueries({ queryKey: ['conversations'] })
      qc.invalidateQueries({ queryKey: ['canvases'] })
    }
  }

  // Chat-mode conversations belong on the /c route
  React.useEffect(() => {
    if (id && convQ.data?.mode && convQ.data.mode !== 'agent') {
      router.replace(`/c/${id}`)
    }
  }, [id, convQ.data?.mode, router])

  // Handle auto-starting an agent run via ?init= query param
  React.useEffect(() => {
    if (id && typeof window !== 'undefined') {
      const searchParams = new URLSearchParams(window.location.search)
      const init = searchParams.get('init')
      if (init) {
        window.history.replaceState({}, '', window.location.pathname)
        sendMessage(init)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  async function startNewAgentChat(content: string) {
    try {
      const c = (await api.post<ConversationRecord>('/chat/conversations', {
        mode: 'agent',
        modelId: selectedAgentModel,
      })).data
      qc.invalidateQueries({ queryKey: ['conversations'] })
      router.push(`/agent/${c.id}?init=${encodeURIComponent(content)}`)
    } catch {
      toast.error('Failed to start agent')
    }
  }

  async function regenerate() {
    if (!id || streaming) return
    sendMessage('', { regenerate: true })
  }


  const messages = convQ.data?.messages || []
  const pendingMessage: MessageRecord | null = streaming
    ? ({
        id: 'pending', conversationId: id || '', role: 'assistant', content: streamText,
        metadata: { tools: liveTools.map((t) => ({ name: t.name, summary: t.summary, ok: t.ok })) },
        createdAt: new Date().toISOString(), tokens: null, model: null, reaction: null, parentId: null,
      } as MessageRecord)
    : null
  const visibleMessages: MessageRecord[] = pendingMessage ? [...messages, pendingMessage] : messages

  const showEmptyState = !id || (messages.length === 0 && !streaming && !convQ.isLoading)
  const notConfigured = statusQ.data && !statusQ.data.configured

  return (
    <>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col bg-background">
        <TopBar />

        {notConfigured && (
          <div className="mx-4 mt-1 flex items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Worm Agent is not configured. Add <code className="rounded bg-amber-500/10 px-1.5 py-0.5 text-xs">DEEPSEEK_TOKEN=...</code> to the server .env and restart.
          </div>
        )}

        {showEmptyState ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4 pb-16">
            <div className="mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-primary text-primary-foreground">
              <Bot className="h-7 w-7" />
            </div>
            <h1 className="mb-1 text-center text-3xl font-semibold tracking-tight">Worm Agent</h1>
            <p className="mb-2 text-center text-sm text-muted-foreground">
              Your coding agent — builds files in your workspace, searches the web, and ships complete projects.
            </p>
            <p className="mb-8 text-center text-xs text-muted-foreground/80">
              Powered by internal models ·{' '}
              <a href="https://3mh.pages.dev/" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
                3MH Technologies
              </a>
              {' · '}
              <a href="https://t.me/j49_c" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
                t.me/j49_c
              </a>
            </p>
            <div className="w-full max-w-3xl">
              <Composer
                onSend={(msg) => (id ? sendMessage(msg) : startNewAgentChat(msg))}
                value={composerValue}
                onChange={setComposerValue}
                placeholder="Ask Worm Agent to build something…"
              />
            </div>
          </div>
        ) : (
          <>
            <div className="relative flex-1 overflow-hidden">
              <div ref={scrollRef} onScroll={handleScroll} className="scrollbar-thin h-full overflow-y-auto">
                <div className="mx-auto max-w-3xl pb-12 pt-4">
                  {convQ.isLoading && (
                    <div className="px-4 py-12 text-center text-sm text-muted-foreground">Loading…</div>
                  )}
                  {visibleMessages.map((m, i) => (
                    <MessageBubble
                      key={m.id}
                      message={m}
                      conversationId={id!}
                      isLast={i === visibleMessages.length - 1}
                      isStreaming={streaming && m.id === 'pending'}
                      onRegenerate={
                        m.role === 'assistant' && i === visibleMessages.length - 1 && !streaming
                          ? regenerate
                          : undefined
                      }
                    />
                  ))}
                  {streaming && streamThinking && (
                    <div className="px-4 py-1.5">
                      <div className="max-h-24 overflow-hidden whitespace-pre-wrap rounded-xl bg-secondary/40 px-3 py-2 text-xs italic leading-relaxed text-muted-foreground">
                        {streamThinking.length > 700 ? '…' + streamThinking.slice(-700) : streamThinking}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              {!autoScroll && (
                <button
                  onClick={() => { setAutoScroll(true); scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }}
                  className="absolute bottom-4 left-1/2 z-10 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border border-border bg-background shadow-md transition-colors hover:bg-accent"
                  aria-label="Scroll to bottom"
                >
                  <ArrowDown className="h-4 w-4" />
                </button>
              )}
            </div>

            <div className="shrink-0 pb-2">
              <Composer
                onSend={sendMessage}
                value={composerValue}
                onChange={setComposerValue}
                streaming={streaming}
                onStop={() => { abortRef.current?.abort() }}
                placeholder="Ask Worm Agent…"
              />
            </div>
          </>
        )}
      </div>
    </>
  )
}

