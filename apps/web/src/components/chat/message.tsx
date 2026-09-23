'use client'
import * as React from 'react'
import { Copy, Check, Pencil, RotateCw, ThumbsUp, ThumbsDown, FilePlus2, FileText, FolderTree, Trash2, Globe, Link as LinkIcon, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Markdown } from '@/components/renderers/markdown'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { MessageRecord } from '@/lib/types'

interface MessageBubbleProps {
  message: MessageRecord
  conversationId: string
  isLast: boolean
  isStreaming?: boolean
  onRegenerate?: () => void
}

const TOOL_ICONS: Record<string, any> = {
  create_file: FilePlus2,
  read_file: FileText,
  list_files: FolderTree,
  delete_file: Trash2,
  web_search: Globe,
  fetch_url: LinkIcon,
}

export function MessageBubble({ message, conversationId, isLast, isStreaming, onRegenerate }: MessageBubbleProps) {
  const qc = useQueryClient()
  const [copied, setCopied] = React.useState(false)
  const [editing, setEditing] = React.useState(false)
  const [editValue, setEditValue] = React.useState(message.content)

  const react = useMutation({
    mutationFn: async (r: string | null) =>
      (await api.post(`/chat/conversations/${conversationId}/messages/${message.id}/react`, { reaction: r ?? '' })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conversation', conversationId] }),
  })
  const saveEdit = useMutation({
    mutationFn: async (content: string) =>
      (await api.patch(`/chat/conversations/${conversationId}/messages/${message.id}`, { content })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversation', conversationId] })
      setEditing(false)
    },
  })

  const isUser = message.role === 'user'

  const copy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  const actionBtn =
    'grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground'

  if (isUser) {
    return (
      <div className="group flex w-full justify-end px-4 py-1.5">
        <div className="max-w-[85%] sm:max-w-[70%]">
          {editing ? (
            <div className="rounded-3xl bg-secondary px-4 py-3">
              <textarea
                autoFocus
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none"
                rows={Math.min(10, Math.max(2, editValue.split('\n').length))}
              />
              <div className="mt-2 flex justify-end gap-2">
                <button
                  onClick={() => { setEditing(false); setEditValue(message.content) }}
                  className="rounded-full bg-background px-3.5 py-1.5 text-xs font-medium hover:bg-accent"
                >
                  Cancel
                </button>
                <button
                  onClick={() => editValue.trim() && saveEdit.mutate(editValue.trim())}
                  className="rounded-full bg-primary px-3.5 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="whitespace-pre-wrap break-words rounded-3xl bg-secondary px-5 py-2.5 text-[15px] leading-relaxed">
                {message.content}
              </div>
              <div className="mt-1 flex justify-end gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                <button onClick={copy} className={actionBtn} aria-label="Copy">
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                </button>
                <button onClick={() => setEditing(true)} className={actionBtn} aria-label="Edit">
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    )
  }

  // Assistant message — plain, no bubble (ChatGPT style)
  return (
    <div className="group w-full px-4 py-1.5">
      {isStreaming && !message.content ? (
        <div className="py-3">
          <div className="h-3 w-3 animate-pulse rounded-full bg-foreground" />
        </div>
      ) : (
        <div className="text-[15px] leading-relaxed">
          <Markdown>{message.content}</Markdown>
        </div>
      )}

      {Array.isArray(message.metadata?.tools) && message.metadata.tools.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {message.metadata.tools.map((t: any, i: number) => {
            const Icon = TOOL_ICONS[t?.name] || Wrench
            return (
              <span
                key={i}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg border border-border bg-secondary/60 px-2.5 py-1 text-xs text-muted-foreground',
                  t?.ok === false && 'text-destructive'
                )}
              >
                <Icon className="h-3 w-3 shrink-0" />
                <span className="font-medium">{t?.name}</span>
                {t?.summary && <span className="max-w-64 truncate">— {t.summary}</span>}
              </span>
            )
          })}
        </div>
      )}

      {!isStreaming && message.content && (
        <div
          className={cn(
            'mt-1.5 flex items-center gap-0.5 transition-opacity',
            isLast ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          )}
        >
          <button onClick={copy} className={actionBtn} aria-label="Copy">
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={() => react.mutate(message.reaction === 'like' ? null : 'like')}
            className={cn(actionBtn, message.reaction === 'like' && 'text-foreground')}
            aria-label="Good response"
          >
            <ThumbsUp className={cn('h-3.5 w-3.5', message.reaction === 'like' && 'fill-current')} />
          </button>
          <button
            onClick={() => react.mutate(message.reaction === 'dislike' ? null : 'dislike')}
            className={cn(actionBtn, message.reaction === 'dislike' && 'text-foreground')}
            aria-label="Bad response"
          >
            <ThumbsDown className={cn('h-3.5 w-3.5', message.reaction === 'dislike' && 'fill-current')} />
          </button>
          {onRegenerate && (
            <button onClick={onRegenerate} className={actionBtn} aria-label="Regenerate response">
              <RotateCw className="h-3.5 w-3.5" />
            </button>
          )}
          {message.model && (
            <span className="ml-2 text-xs text-muted-foreground/70">{message.model}</span>
          )}
        </div>
      )}
    </div>
  )
}

