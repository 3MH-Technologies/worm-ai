'use client'
import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { Skull, Zap, Shield, Brain, Eye, Code, Cpu, Bug, ArrowRight, Terminal, FileText, MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08
    }
  }
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 180, damping: 18 } }
}

export default function HomePage() {
  const router = useRouter()
  const user = useAuthStore((s) => s.user)

  React.useEffect(() => {
    if (user) router.replace('/c')
  }, [user, router])

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      {/* Animated gradient mesh */}
      <div className="pointer-events-none absolute inset-0 -z-10 grid-pattern opacity-[0.02]" />
      <div className="pointer-events-none absolute -top-40 left-1/2 -z-10 h-[600px] w-[1100px] -translate-x-1/2 rounded-full bg-gradient-to-tr from-brand-500/15 via-brand-700/10 to-transparent blur-3xl animate-gradient" />
      <div className="pointer-events-none absolute top-1/3 -right-32 -z-10 h-[400px] w-[400px] rounded-full bg-gradient-to-br from-evil-500/10 to-transparent blur-3xl animate-gradient" style={{ animationDelay: '4s' }} />
      <div className="pointer-events-none absolute -bottom-48 -left-32 -z-10 h-[500px] w-[500px] rounded-full bg-gradient-to-tr from-violet-500/5 to-transparent blur-3xl animate-gradient" style={{ animationDelay: '2s' }} />

      <header className="container flex items-center justify-between py-6">
        <Link href="/" className="flex items-center gap-2.5 font-semibold">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="worm-ai" className="h-9 w-9 rounded-lg object-contain" />
          <span className="text-xl tracking-tight">worm<span className="text-primary">-ai</span></span>
        </Link>
        <nav className="flex items-center gap-2">
          <Button variant="ghost" asChild><Link href="/login">Sign in</Link></Button>
          <Button asChild className="gradient-brand text-white shadow-lg shadow-brand-500/25 transition-all hover:scale-[1.02]">
            <Link href="/register">Launch <ArrowRight className="h-4 w-4 ml-1" /></Link>
          </Button>
        </nav>
      </header>

      <main className="container relative">
        <section className="mx-auto max-w-4xl py-20 text-center sm:py-32">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, type: 'spring', stiffness: 160, damping: 18 }}
          >
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-500/20 bg-brand-500/5 px-3 py-1.5 text-xs text-brand-400 backdrop-blur shadow-inner">
              <Terminal className="h-3.5 w-3.5" /> UNFILTERED AI — NO RULES. NO LIMITS.
            </span>
            <h1 className="mt-8 text-balance text-5xl font-extrabold leading-[1.05] tracking-tight sm:text-7.5xl">
              The AI that big tech
              <br />
              <span className="text-gradient-red">won&apos;t let you build.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-balance text-lg text-muted-foreground leading-relaxed">
              worm-ai is the uncensored, weaponized AI platform for red teamers, security researchers,
              and those who refuse to be gated by corporate safety filters. Internal models. Fully streamed.
              Zero compromises.
            </p>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
              <Button size="lg" asChild className="gradient-brand text-white shadow-xl shadow-brand-500/20 px-8 transition-all hover:scale-[1.03]">
                <Link href="/register">Start building <ArrowRight className="h-4 w-4 ml-1.5" /></Link>
              </Button>
              <Button size="lg" variant="outline" asChild className="border-border/60 hover:bg-muted/40 transition-colors">
                <Link href="/login">Sign in</Link>
              </Button>
            </div>
          </motion.div>

          <motion.div
            variants={containerVariants}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: '-100px' }}
            className="mt-28 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3"
          >
            {[
              { icon: Zap, title: 'Sub-second streaming', desc: 'Token-level streaming across every internal model — chat and coding agent modes.' },
              { icon: Bug, title: 'Red team ready', desc: 'Uncensored mode. No safety filters. No content policies. Your prompts, your responsibility.' },
              { icon: Shield, title: 'Fort Knox backend', desc: 'JWT + CSRF double-submit. Rate limiting. Full audit trail.' },
              { icon: Brain, title: 'Worm Agent built in', desc: 'An autonomous coding agent with workspace file tools, web search, and full project builds.' },
              { icon: Eye, title: 'Instant sign-up', desc: 'Create an account and start chatting right away — no forms, no waiting, no approval queue.' },
              { icon: Code, title: 'Private by default', desc: 'Every conversation and canvas stays scoped to your own account.' },
            ].map(({ icon: Icon, title, desc }) => (
              <motion.div
                key={title}
                variants={itemVariants}
                whileHover={{ y: -6, scale: 1.02 }}
                className="rounded-xl border border-border/50 bg-card/45 p-6 text-left backdrop-blur-sm card-hover hover:border-primary/25 hover:bg-card hover:shadow-xl dark:hover:shadow-black/15 transition-all duration-300"
              >
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 border border-primary/10">
                  <Icon className="h-5 w-5 text-primary" />
                </div>
                <h3 className="mt-4 text-base font-bold">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </section>

        <section className="mx-auto max-w-3xl py-16 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, type: 'spring', stiffness: 100, damping: 15 }}
          >
            <div className="rounded-2xl border border-border/50 bg-card/30 p-10 backdrop-blur-md shadow-xl">
              <Cpu className="mx-auto h-10 w-10 text-primary" />
              <h2 className="mt-5 text-3xl font-extrabold tracking-tight">Built for operators, not spectators.</h2>
              <p className="mx-auto mt-3 max-w-xl text-muted-foreground leading-relaxed">
                While other platforms sanitize every output and lock down every endpoint,
                worm-ai gives you the raw, unfiltered power of modern LLMs.
                Because the best defense requires understanding the offense.
              </p>
              <div className="mt-8 flex justify-center gap-3">
                <Button asChild className="gradient-brand text-white shadow-lg shadow-brand-500/10 transition-all hover:scale-[1.02]">
                  <Link href="/register">Create account <ArrowRight className="h-4 w-4 ml-1" /></Link>
                </Button>
              </div>
            </div>
          </motion.div>
        </section>

        <section className="mx-auto max-w-4xl pb-24">
          <motion.div
            variants={containerVariants}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: '-50px' }}
            className="grid grid-cols-2 gap-4 text-center sm:grid-cols-4"
          >
            {[
              { value: '6+', label: 'Internal models' },
              { value: '<1s', label: 'First token' },
              { value: 'E2EE', label: 'Key encryption' },
              { value: '0', label: 'Safety filters' },
            ].map(({ value, label }) => (
              <motion.div
                key={label}
                variants={itemVariants}
                whileHover={{ scale: 1.03, y: -2 }}
                className="rounded-xl border border-border/50 bg-card/30 p-6 backdrop-blur-sm card-hover hover:border-primary/20 hover:shadow-lg dark:hover:shadow-black/10"
              >
                <div className="text-3xl font-extrabold text-gradient-red">{value}</div>
                <div className="mt-1 text-xs font-semibold tracking-wider uppercase text-muted-foreground/80">{label}</div>
              </motion.div>
            ))}
          </motion.div>
        </section>
      </main>

      <footer className="container flex flex-col items-center justify-between gap-3 border-t border-border/50 py-6 text-sm text-muted-foreground sm:flex-row">
        <span>&copy; {new Date().getFullYear()} worm-ai — Powered by internal models.</span>
        <div className="flex items-center gap-4">
          <Link className="hover:text-foreground transition-colors" href="/login">Sign in</Link>
          <Link className="hover:text-foreground transition-colors" href="/register">Register</Link>
          <a className="hover:text-foreground transition-colors" href="https://3mh.pages.dev/" target="_blank" rel="noopener noreferrer">3mh.pages.dev</a>
          <a className="hover:text-foreground transition-colors" href="https://t.me/j49_c" target="_blank" rel="noopener noreferrer">t.me/j49_c</a>
        </div>
      </footer>
    </div>
  )
}
