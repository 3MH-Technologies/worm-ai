'use client'
import * as React from 'react'
import { getAccessToken } from '@/lib/api'

/**
 * Attachment URLs (`/api/v1/attachments/{id}`) live behind Bearer auth, which a
 * plain `<img src>` cannot send. Fetch the bytes with the token and hand back an
 * object URL, so avatars and inlined attachments actually render.
 */
export function useAuthImageUrl(url: string | null | undefined): string | null {
  const [objectUrl, setObjectUrl] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!url) {
      setObjectUrl(null)
      return
    }
    if (!url.startsWith('/api/v1/attachments/')) {
      setObjectUrl(url)
      return
    }
    let revoked: string | null = null
    let cancelled = false
    const token = getAccessToken()

    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((blob) => {
        if (cancelled) return
        const next = URL.createObjectURL(blob)
        revoked = next
        setObjectUrl(next)
      })
      .catch(() => {
        if (!cancelled) setObjectUrl(null)
      })

    return () => {
      cancelled = true
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [url])

  return objectUrl
}
