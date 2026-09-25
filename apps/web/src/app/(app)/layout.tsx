'use client'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/auth'
import { Loader2 } from 'lucide-react'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { user, refreshMe } = useAuthStore()
  const [ready, setReady] = React.useState(false)

  React.useEffect(() => {
    (async () => {
      await refreshMe()
      setReady(true)
    })()
  }, [refreshMe])

  React.useEffect(() => {
    if (ready && !user) router.replace('/login')
  }, [ready, user, router])

  if (!ready || !user) {
    return (
      <div className="grid h-screen w-screen place-items-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return <div className="flex h-screen overflow-hidden bg-background text-foreground">{children}</div>
}
