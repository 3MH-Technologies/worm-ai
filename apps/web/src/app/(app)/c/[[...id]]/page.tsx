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
import { ArrowDown } from 'lucide-react'
import { useUIStore } from '@/stores/ui'
import { toast } from 'sonner'

export default function ConversationPage() {
  const params = useParams<{ id?: string }>()
  const router = useRouter()
  const id = params?.id
  const qc = useQueryClient()
  const selectedModelId = useUIStore((s) => s.selectedModelId)
  const scrollRef = React.useRef<HTMLDivElement>(null)
  const abortRef = React.useRef<AbortController | null>(null)
  const [streaming, setStreaming] = React.useState(false)
  const [streamText, setStreamText] = React.useState('')
  const [autoScroll, setAutoScroll] = React.useState(true)
  const [composerValue, setComposerValue] = React.useState('')

  const convQ = useQuery({
    queryKey: ['conversation', id],
    queryFn: async () => (await api.get<ConversationWithMessages>(`/chat/conversations/${id}`)).data,
    enabled: !!id,
  })

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight
    setAutoScroll(dist < 80)
  }

  React.useEffect(() => {
    if (autoScroll) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: streaming ? 'auto' : 'smooth' })
  }, [convQ.data?.messages, streamText, autoScroll, streaming])

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
        metadata: opts.attachments ? { attachments: opts.attachments } : {},
        createdAt: new Date().toISOString(), tokens: null, model: null, reaction: null, parentId: null,
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
    setStreaming(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const token = getAccessToken()
      const csrf = readCsrfToken()
      const res = await fetch(`/api/v1/chat/conversations/${id}/stream`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(csrf ? { 'x-csrf-token': csrf } : {}),
        },
        body: JSON.stringify({
          content,
          modelId: selectedModelId || convQ.data?.modelId || null,
          role: 'user',
          attachments: opts.attachments?.map((a) => ({ id: a.id, kind: a.kind, name: a.name, url: a.url, mimeType: a.mimeType })),
          regenerate: isRegen,
        }),
      })
      if (!res.ok || !res.body) {
        // Surface the API's message (e.g. "Message is too long…") instead of "HTTP 400".
        let detail = `Request failed (${res.status})`
        try {
          const body = await res.json()
          const d = body?.detail ?? body?.error
          if (typeof d === 'string') detail = d
          else if (Array.isArray(d)) detail = d.map((x: any) => x?.msg).join(', ') || detail
        } catch { /* non-JSON error body */ }
        throw new Error(detail)
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
            } else if (event === 'error') {
              toast.error(payload.message || 'stream error')
            }
          } catch { /* malformed JSON, skip */ }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        toast.error(e?.message || 'stream failed')
      }
    } finally {
      abortRef.current = null
      setStreaming(false)
      setStreamText('')
      qc.invalidateQueries({ queryKey: ['conversation', id] })
      qc.invalidateQueries({ queryKey: ['conversations'] })
    }
  }

  // Agent conversations belong on the /agent route
  React.useEffect(() => {
    if (id && convQ.data?.mode === 'agent') {
      router.replace(`/agent/${id}`)
    }
  }, [id, convQ.data?.mode, router])

  // Handle auto-starting chat via ?init= query param
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

  async function startNewChat(content: string) {
    try {
      const c = (await api.post<ConversationRecord>('/chat/conversations', {})).data
      qc.invalidateQueries({ queryKey: ['conversations'] })
      router.push(`/c/${c.id}?init=${encodeURIComponent(content)}`)
    } catch {
      toast.error('Failed to start chat')
    }
  }

  async function regenerate() {
    if (!id || streaming) return
    sendMessage('', { regenerate: true })
  }


  const messages = convQ.data?.messages || []
  const visibleMessages: MessageRecord[] = streaming
    ? [...messages, { id: 'pending', conversationId: id || '', role: 'assistant', content: streamText, metadata: {}, createdAt: new Date().toISOString(), tokens: null, model: null, reaction: null, parentId: null } as MessageRecord]
    : messages

  const showEmptyState = !id || (messages.length === 0 && !streaming && !convQ.isLoading)

  return (
    <>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col bg-background">
        <TopBar />

        {showEmptyState ? (
          /* Empty state — ChatGPT style: centered title + composer */
          <div className="flex flex-1 flex-col items-center justify-center px-4 pb-16">
            <h1 className="mb-8 text-center text-3xl font-semibold tracking-tight">
              What can I help with?
            </h1>
            <div className="w-full max-w-3xl">
              <Composer
                onSend={(msg, opts) => (id ? sendMessage(msg, opts) : startNewChat(msg))}
                value={composerValue}
                onChange={setComposerValue}
              />
            </div>
            <p className="mt-1 text-center text-[11px] text-muted-foreground/80">
              Powered by internal models —{' '}
              <a href="https://3mh.pages.dev/" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
                3MH Technologies
              </a>
              {' · '}
              <a href="https://t.me/j49_c" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
                t.me/j49_c
              </a>
            </p>
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
              />
            </div>
          </>
        )}
      </div>
    </>
  )
}

