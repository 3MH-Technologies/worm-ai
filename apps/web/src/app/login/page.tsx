'use client'
import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Skull, ArrowRight, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuthStore } from '@/stores/auth'
import { apiError } from '@/lib/api'
import { toast } from 'sonner'

export default function LoginPage() {
  const router = useRouter()
  const { login, isLoading, user } = useAuthStore()
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')

  React.useEffect(() => { if (user) router.replace('/c') }, [user, router])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    try {
      await login(email, password)
      toast.success('Access granted')
      router.replace('/c')
    } catch (err) {
      toast.error(apiError(err))
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <div className="pointer-events-none absolute inset-0 -z-10 grid-pattern opacity-[0.03]" />
      <div className="pointer-events-none absolute -top-32 left-1/2 -z-10 h-[400px] w-[800px] -translate-x-1/2 rounded-full bg-gradient-to-tr from-brand-500/15 via-brand-700/10 to-transparent blur-3xl" />
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="worm-ai" className="h-10 w-10 rounded-lg object-contain" />
          <span className="text-2xl font-bold tracking-tight">worm<span className="text-primary">-ai</span></span>
        </div>
        <Card className="border-border/50 bg-card/80 backdrop-blur">
          <CardHeader className="text-center">
            <CardTitle className="text-xl">Welcome back</CardTitle>
            <CardDescription>Enter your credentials to access the platform.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={onSubmit}>
              <div>
                <label className="text-sm font-medium">Email</label>
                <Input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="operator@example.com" />
              </div>
              <div>
                <label className="text-sm font-medium">Password</label>
                <Input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter password" />
              </div>
              <Button type="submit" className="w-full gradient-brand text-white shadow-lg shadow-brand-500/25" disabled={isLoading}>
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Sign in <ArrowRight className="h-4 w-4" /></>}
              </Button>
            </form>
            <p className="mt-5 text-center text-sm text-muted-foreground">
              No account? <Link href="/register" className="text-primary hover:underline font-medium">Create account</Link>
            </p>
            <p className="mt-1 text-center text-sm text-muted-foreground">
              <Link href="/forgot" className="hover:text-foreground hover:underline">Forgot password?</Link>
            </p>
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
