'use client'
import * as React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Sidebar } from '@/components/layout/sidebar'
import { TopBar } from '@/components/layout/topbar'
import { api, apiError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { Save, Camera } from 'lucide-react'
import { toast } from 'sonner'
import { formatRelative } from '@/lib/utils'
import { useAuthImageUrl } from '@/lib/auth-image'

export default function ProfilePage() {
  const { user, refreshMe } = useAuthStore()
  const qc = useQueryClient()
  const [username, setUsername] = React.useState(user?.username || '')
  const [avatar, setAvatar] = React.useState(user?.avatar || '')
  const avatarSrc = useAuthImageUrl(avatar)

  React.useEffect(() => {
    setUsername(user?.username || '')
    setAvatar(user?.avatar || '')
  }, [user?.username, user?.avatar])

  const save = useMutation({
    mutationFn: async () => (await api.patch('/auth/me', { username, avatar: avatar || null })).data,
    onSuccess: () => { refreshMe(); qc.invalidateQueries({ queryKey: ['auth'] }); toast.success('Profile updated') },
    onError: (e) => toast.error(apiError(e)),
  })

  const onPickAvatar = async (file: File | null) => {
    if (!file) return
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api.post('/attachments', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setAvatar(r.data.url)
      toast.success('Avatar uploaded')
    } catch (e) {
      toast.error(apiError(e))
    }
  }

  if (!user) return null
  const initials = user.username.slice(0, 1).toUpperCase()

  return (
    <>
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar />
        <div className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-3xl space-y-6">
            <div>
              <h1 className="text-xl font-semibold">Profile</h1>
              <p className="text-sm text-muted-foreground">How you appear across the workspace.</p>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Avatar & display name</CardTitle>
                <CardDescription>Used in the sidebar, message bubbles, and mentions.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-4">
                  <Avatar className="h-16 w-16">
                    {avatarSrc ? <AvatarImage src={avatarSrc} alt={user.username} /> : null}
                    <AvatarFallback className="bg-gradient-to-br from-brand-500 to-violet-500 text-lg text-white">{initials}</AvatarFallback>
                  </Avatar>
                  <div className="flex flex-col gap-2">
                    <label className="inline-flex items-center gap-2 text-sm font-medium">
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => onPickAvatar(e.target.files?.[0] || null)}
                      />
                      <span className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 hover:bg-accent">
                        <Camera className="h-3.5 w-3.5" /> Upload image
                      </span>
                    </label>
                    {avatar && (
                      <Button size="sm" variant="ghost" onClick={() => setAvatar('')}>Remove</Button>
                    )}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium">Display name</label>
                  <Input value={username} onChange={(e) => setUsername(e.target.value)} />
                </div>
                <Button onClick={() => save.mutate()} disabled={save.isPending || !username}>
                  <Save className="h-4 w-4" /> Save
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Account</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row label="Email" value={user.email} />
                <Row label="Joined" value={user.createdAt ? new Date(user.createdAt).toLocaleDateString() : '—'} />
                <Row label="Last login" value={user.lastLogin ? formatRelative(user.lastLogin) : '—'} />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 py-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  )
}
