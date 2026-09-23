import './globals.css'
import type { Metadata, Viewport } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import { Providers } from '@/components/providers'
import { cn } from '@/lib/utils'

const inter = Inter({ subsets: ['latin'], variable: '--font-sans', display: 'swap' })
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' })

export const metadata: Metadata = {
  title: { default: 'worm-ai', template: '%s · worm-ai' },
  description: 'worm-ai — chat and Worm Agent, the coding agent, powered by internal models.',
  applicationName: 'worm-ai',
  keywords: ['AI', 'chat', 'worm-ai', 'worm agent', 'coding agent', 'internal models'],
  authors: [{ name: '3MH Technologies', url: 'https://3mh.pages.dev/' }],
  openGraph: { title: 'worm-ai', description: 'Chat + Worm Agent — powered by internal models.', type: 'website' },
  robots: { index: false, follow: false },
  icons: [
    { rel: 'icon', url: '/logo.svg', type: 'image/svg+xml' },
    { rel: 'apple-touch-icon', url: '/logo.svg' },
  ],
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#0a0f14' },
  ],
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={cn(inter.variable, mono.variable, 'font-sans antialiased')}>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
