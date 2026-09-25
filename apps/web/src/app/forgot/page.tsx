'use client'
import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Bot, Loader2, Mail, KeyRound, Check } from 'lucide-react'
import { motion } from 'framer-motion'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { api, apiError } from '@/lib/api'
import { toast } from 'sonner'

export default function ForgotPage() {
  const router = useRouter()
  const [step, setStep] = React.useState<'request' | 'reset' | 'done'>('request')
  const [email, setEmail] = React.useState('')
  const [token, setToken] = React.useState('')
  const [newPw, setNewPw] = React.useState('')
  const [devToken, setDevToken] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  async function request(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await api.post('/auth/forgot-password', { email })
      if (r.data?.devToken) setDevToken(r.data.devToken)
      toast.success('If an account exists, a reset link has been issued.')
      setStep('reset')
    } catch (err) {
      toast.error(apiError(err))
    } finally {
      setBusy(false)
    }
  }

  async function reset(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post('/auth/reset-password', { token, newPassword: newPw })
      toast.success('Password updated')
      setStep('done')
    } catch (err) {
      toast.error(apiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <div className="pointer-events-none absolute inset-0 -z-10 grid-pattern opacity-[0.04]" />
      <div className="pointer-events-none absolute -top-32 left-1/2 -z-10 h-[400px] w-[800px] -translate-x-1/2 rounded-full bg-gradient-to-tr from-brand-500/20 via-blue-500/10 to-violet-500/20 blur-3xl" />
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-lg gradient-brand text-white shadow">
            <Bot className="h-4 w-4" />
          </div>
          <span className="text-xl font-semibold">worm-ai</span>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>
              {step === 'request' ? 'Forgot password' : step === 'reset' ? 'Set new password' : 'All set'}
            </CardTitle>
            <CardDescription>
              {step === 'request' && "Enter your email and we'll send you a reset link."}
              {step === 'reset' && 'Use the token from your email (or the dev token below) to set a new password.'}
              {step === 'done' && 'Your password has been updated. You can now sign in.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {step === 'request' && (
              <form className="space-y-3" onSubmit={request}>
                <div>
                  <label className="text-sm font-medium">Email</label>
                  <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
                <Button type="submit" className="w-full" disabled={busy}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Mail className="h-4 w-4" /> Send reset link</>}
                </Button>
              </form>
            )}
            {step === 'reset' && (
              <form className="space-y-3" onSubmit={reset}>
                <div>
                  <label className="text-sm font-medium">Reset token</label>
                  <Input value={token} onChange={(e) => setToken(e.target.value)} placeholder="paste token" required />
                </div>
                <div>
                  <label className="text-sm font-medium">New password</label>
                  <Input type="password" required minLength={8} value={newPw} onChange={(e) => setNewPw(e.target.value)} />
                </div>
                {devToken && (
                  <div className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400">
                    <strong>Dev token:</strong> <code className="break-all">{devToken}</code> (only shown in non-production)
                  </div>
                )}
                <Button type="submit" className="w-full" disabled={busy || !token || !newPw}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><KeyRound className="h-4 w-4" /> Update password</>}
                </Button>
              </form>
            )}
            {step === 'done' && (
              <div className="space-y-3 text-center">
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-500/15 text-emerald-600">
                  <Check className="h-5 w-5" />
                </div>
                <Button className="w-full" onClick={() => router.push('/login')}>Go to sign in</Button>
              </div>
            )}
            <div className="mt-4 text-center text-sm text-muted-foreground">
              <Link href="/login" className="inline-flex items-center gap-1 hover:text-foreground">
                <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
              </Link>
            </div>
          </CardContent>
        </Card>
      </motion.div>
      <footer className="pb-6 text-center text-[11px] text-muted-foreground">
        Powered by internal models ·{' '}
        <a href="https://3mh.pages.dev/" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
          3MH Technologies
        </a>
        {' · '}
        <a href="https://t.me/j49_c" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
          t.me/j49_c
        </a>
      </footer>
    </div>
  )
}
