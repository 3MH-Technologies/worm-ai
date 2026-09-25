'use client'
import * as React from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Save, Trash2, LogOut } from 'lucide-react'
import { Sidebar } from '@/components/layout/sidebar'
import { TopBar } from '@/components/layout/topbar'
import { api, apiError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { toast } from 'sonner'
import { MemoryRecord, MemoryKind } from '@/lib/types'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

export default function SettingsPage() {
  const { user, refreshMe, logout } = useAuthStore()
  const [username, setUsername] = React.useState(user?.username || '')
  const [oldPw, setOldPw] = React.useState('')
  const [newPw, setNewPw] = React.useState('')

  const memQ = useQuery({
    queryKey: ['memory'],
    queryFn: async () => (await api.get<MemoryRecord[]>('/memory')).data,
  })
  const addMem = useMutation({
    mutationFn: async (payload: { kind: MemoryKind; content: string }) => (await api.post<MemoryRecord>('/memory', payload)).data,
    onSuccess: () => toast.success('Memory saved'),
  })
  const delMem = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/memory/${id}`) },
    onSuccess: () => toast.success('Memory removed'),
  })

  const saveProfile = useMutation({
    mutationFn: async () => (await api.patch('/auth/me', { username })).data,
    onSuccess: () => { refreshMe(); toast.success('Profile updated') },
  })
  const changePw = useMutation({
    mutationFn: async () => { await api.post('/auth/change-password', { oldPassword: oldPw, newPassword: newPw }) },
    onSuccess: () => { setOldPw(''); setNewPw(''); toast.success('Password changed') },
    onError: (e) => toast.error(apiError(e)),
  })
  const logoutAll = useMutation({
    mutationFn: async () => { await api.post('/auth/logout-all') },
    onSuccess: async () => {
      await logout()
      window.location.href = '/login'
    },
    onError: (e) => toast.error(apiError(e)),
  })

  return (
    <>
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar />
        <div className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-3xl space-y-6">
            <h1 className="text-xl font-semibold">Settings</h1>

            <Card>
              <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <label className="text-sm font-medium">Username</label>
                  <Input value={username} onChange={(e) => setUsername(e.target.value)} />
                </div>
                <div>
                  <label className="text-sm font-medium">Email</label>
                  <Input value={user?.email || ''} disabled />
                </div>
                <Button onClick={() => saveProfile.mutate()} disabled={saveProfile.isPending}><Save className="h-4 w-4" /> Save</Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Password</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Input type="password" placeholder="Current password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} />
                <Input type="password" placeholder="New password (min 8 chars)" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
                <Button onClick={() => changePw.mutate()} disabled={changePw.isPending}>Change password</Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Conversation memory</CardTitle></CardHeader>
              <CardContent>
                <p className="mb-3 text-sm text-muted-foreground">Memory items are added to your future conversations. Manage them below.</p>
                <Tabs defaultValue="long_term">
                  <TabsList>
                    <TabsTrigger value="long_term">Long-term</TabsTrigger>
                    <TabsTrigger value="preference">Preferences</TabsTrigger>
                    <TabsTrigger value="context">Context</TabsTrigger>
                  </TabsList>
                  {(['long_term', 'preference', 'context'] as MemoryKind[]).map((k) => (
                    <TabsContent key={k} value={k} className="space-y-2">
                      {(memQ.data || []).filter((m) => m.kind === k).map((m) => (
                        <div key={m.id} className="flex items-center gap-2 rounded-md border border-border bg-card p-2 text-sm">
                          <span className="flex-1">{m.content}</span>
                          <Button size="icon" variant="ghost" onClick={() => delMem.mutate(m.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                        </div>
                      ))}
                      <AddMemoryForm onAdd={(content) => addMem.mutate({ kind: k, content })} />
                    </TabsContent>
                  ))}
                </Tabs>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Sessions</CardTitle></CardHeader>
              <CardContent>
                <Button variant="destructive" onClick={() => logoutAll.mutate()} disabled={logoutAll.isPending}>
                  <LogOut className="h-4 w-4" /> Sign out everywhere
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  )
}

function AddMemoryForm({ onAdd }: { onAdd: (s: string) => void }) {
  const [v, setV] = React.useState('')
  return (
    <div className="flex items-center gap-2">
      <Input value={v} onChange={(e) => setV(e.target.value)} placeholder="Add a memory item…" />
      <Button onClick={() => { if (v.trim()) { onAdd(v); setV('') } }}>Add</Button>
    </div>
  )
}
