'use client'
import * as React from 'react'
import TextareaAutosize from 'react-textarea-autosize'
import { ArrowUp, Square, Plus, X, File as FileIcon, Image as ImageIcon, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api, apiError } from '@/lib/api'
import { AttachmentRecord } from '@/lib/types'
import { toast } from 'sonner'

export interface ComposerAttachment {
  id: string
  kind: 'image' | 'file'
  name: string
  url: string
  mimeType: string
  size: number
}

export interface ComposerProps {
  onSend: (msg: string, opts: {
    attachments?: ComposerAttachment[]
    regenerate?: boolean
  }) => void
  onStop?: () => void
  streaming?: boolean
  placeholder?: string
  value?: string
  onChange?: (v: string) => void
}

export function Composer({ onSend, onStop, streaming, placeholder, value: externalValue, onChange }: ComposerProps) {
  const [value, setValue] = React.useState('')
  const [attachments, setAttachments] = React.useState<ComposerAttachment[]>([])
  const [uploading, setUploading] = React.useState(false)
  const ref = React.useRef<HTMLTextAreaElement>(null)
  const fileInput = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => { ref.current?.focus() }, [])

  React.useEffect(() => {
    if (externalValue !== undefined) {
      setValue(externalValue)
      if (externalValue) ref.current?.focus()
    }
  }, [externalValue])

  const handleValueChange = (val: string) => {
    setValue(val)
    if (onChange) onChange(val)
  }

  async function onPickFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      const uploaded: ComposerAttachment[] = []
      for (const f of Array.from(files)) {
        const fd = new FormData()
        fd.append('file', f)
        const r = await api.post<AttachmentRecord>('/attachments', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
        uploaded.push({
          id: r.data.id, kind: r.data.kind, name: r.data.originalName,
          url: r.data.url, mimeType: r.data.mimeType, size: r.data.size,
        })
      }
      setAttachments((a) => [...a, ...uploaded])
    } catch (e) {
      toast.error(apiError(e))
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  function send() {
    const v = value.trim()
    if (!v || streaming) return
    onSend(v, { attachments: attachments.length ? attachments : undefined })
    handleValueChange('')
    setAttachments([])
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4">
      <div className="rounded-[28px] border border-border/50 bg-secondary shadow-[0_4px_14px_rgba(0,0,0,0.06)] dark:border-border dark:shadow-none">
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 px-3 pt-3">
            {attachments.map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-1.5 text-xs"
              >
                {a.kind === 'image'
                  ? <ImageIcon className="h-3.5 w-3.5 text-muted-foreground" />
                  : <FileIcon className="h-3.5 w-3.5 text-muted-foreground" />}
                <span className="max-w-40 truncate">{a.name}</span>
                <button
                  onClick={() => setAttachments((arr) => arr.filter((x) => x.id !== a.id))}
                  className="rounded-full p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Remove attachment"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-1 px-2 py-1.5">
          <input
            ref={fileInput}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => onPickFiles(e.target.files)}
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
            className="mb-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
            aria-label="Attach files"
          >
            {uploading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Plus className="h-5 w-5" />}
          </button>

          <TextareaAutosize
            ref={ref}
            value={value}
            onChange={(e) => handleValueChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder={placeholder || 'Ask anything'}
            minRows={1}
            maxRows={10}
            className="max-h-64 w-full resize-none bg-transparent px-2 py-2 text-[15px] leading-relaxed outline-none placeholder:text-muted-foreground"
          />

          {streaming ? (
            <button
              onClick={onStop}
              className="mb-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground transition-opacity hover:opacity-85"
              aria-label="Stop generating"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
            </button>
          ) : (
            <button
              onClick={send}
              disabled={!value.trim()}
              className={cn(
                'mb-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full transition-all',
                value.trim()
                  ? 'bg-primary text-primary-foreground hover:opacity-85'
                  : 'cursor-not-allowed bg-muted text-muted-foreground/50'
              )}
              aria-label="Send message"
            >
              <ArrowUp className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>
      <p className="py-2 text-center text-[11px] leading-4 text-muted-foreground">
        worm-ai can make mistakes. Check important info.
      </p>
    </div>
  )
}
