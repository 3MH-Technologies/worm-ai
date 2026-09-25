'use client'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Sparkles, Globe, BookOpen, ArrowRight } from 'lucide-react'
import { Sidebar } from '@/components/layout/sidebar'
import { TopBar } from '@/components/layout/topbar'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Markdown } from '@/components/renderers/markdown'
import { useMutation } from '@tanstack/react-query'
import { api, apiError } from '@/lib/api'
import { ResearchReport } from '@/lib/types'
import { toast } from 'sonner'

export default function ResearchPage() {
  const router = useRouter()
  const [query, setQuery] = React.useState('')
  const [report, setReport] = React.useState<ResearchReport | null>(null)

  const run = useMutation({
    mutationFn: async () => (await api.post<ResearchReport>('/research/run', { query, maxSources: 8, saveAsCanvas: true })).data,
    onSuccess: (r) => { setReport(r); toast.success('Research complete') },
    onError: (e) => toast.error(apiError(e)),
  })

  return (
    <>
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar />
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-4xl p-6">
            <div className="mb-6 flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl gradient-brand text-white shadow">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <h1 className="text-xl font-semibold">Research mode</h1>
                <p className="text-sm text-muted-foreground">Multi-source aggregation with citations and a long-form report.</p>
              </div>
            </div>
            <Card>
              <CardContent className="space-y-3 p-4">
                <div className="flex items-center gap-2">
                  <Globe className="h-4 w-4 text-muted-foreground" />
                  <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="What do you want to research?" />
                </div>
                <Button onClick={() => run.mutate()} disabled={query.trim().length < 3 || run.isPending} className="w-full">
                  {run.isPending ? 'Gathering sources…' : <>Run research <ArrowRight className="h-4 w-4" /></>}
                </Button>
              </CardContent>
            </Card>

            {report && (
              <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1fr,320px]">
                <Card>
                  <CardContent className="p-6">
                    <h2 className="mb-2 text-lg font-semibold">Report</h2>
                    <Markdown>{report.report}</Markdown>
                  </CardContent>
                </Card>
                <div className="space-y-3">
                  <Card>
                    <CardContent className="p-4">
                      <div className="mb-2 flex items-center justify-between text-sm font-medium">
                        <span>Sources</span>
                        <span className="text-xs text-muted-foreground">{report.sources.length}</span>
                      </div>
                      <ol className="space-y-2 text-xs">
                        {report.sources.map((s, i) => (
                          <li key={s.url} className="rounded border border-border bg-muted/20 p-2">
                            <a href={s.url} target="_blank" rel="noreferrer" className="font-medium text-primary hover:underline">[{i + 1}] {s.title}</a>
                            <p className="line-clamp-2 text-muted-foreground">{s.snippet}</p>
                          </li>
                        ))}
                      </ol>
                    </CardContent>
                  </Card>
                  {report.canvasId && (
                    <Button variant="outline" className="w-full" onClick={() => router.push(`/canvas/${report.canvasId}`)}>
                      <BookOpen className="h-4 w-4" /> Open in canvas
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
