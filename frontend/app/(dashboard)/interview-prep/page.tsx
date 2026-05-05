'use client'

import { useState } from 'react'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import { MessageSquare, Loader2, RefreshCw, ChevronDown, ChevronUp, Info } from 'lucide-react'
import { apiFetch } from '@/lib/api'

interface InterviewQuestion {
  question: string
  framework: string
  answer_framework: string
  tips: string[]
}

export default function InterviewPrepPage() {
  const [jd, setJd] = useState('')
  const [loading, setLoading] = useState(false)
  const [questions, setQuestions] = useState<InterviewQuestion[]>([])
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [regeneratingIdx, setRegeneratingIdx] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  async function generateQuestions() {
    if (!jd.trim()) return
    setLoading(true)
    setQuestions([])
    setError(null)

    try {
      const res = await apiFetch('/api/ai/interview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_description: jd }),
      })
      const json = await res.json()

      if (!res.ok) {
        setError(json.detail || 'Generation failed.')
      } else {
        setQuestions(json.questions || [])
        setExpandedIdx(0)
      }
    } catch {
      setError('Network error. Please try again.')
    }

    setLoading(false)
  }

  async function regenerateAnswer(idx: number) {
    setRegeneratingIdx(idx)
    try {
      const res = await apiFetch('/api/ai/interview/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_description: jd, question: questions[idx].question }),
      })
      const json = await res.json()
      if (!res.ok) {
        toast({ title: 'Regeneration failed', variant: 'destructive' })
      } else {
        setQuestions((prev) => prev.map((q, i) => i === idx ? { ...q, ...json } : q))
        toast({ title: 'Answer regenerated!' })
      }
    } catch {
      toast({ title: 'Network error', variant: 'destructive' })
    }
    setRegeneratingIdx(null)
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Interview Prep</h1>
        <p className="text-slate-500 text-sm mt-1">
          Paste the job description — get 10 likely questions with STAR-method answer frameworks
        </p>
      </div>

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>{config.rateLimits.interviewPrepPerDay} preps/day</strong> on the free tier.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-2 gap-6">
        {/* Input */}
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-4">
              <Label className="mb-2 block">Job Description</Label>
              <Textarea
                value={jd}
                onChange={(e) => setJd(e.target.value)}
                rows={18}
                placeholder="Paste the full job description here…"
                className="text-sm"
              />
            </CardContent>
          </Card>

          <Button className="w-full" onClick={generateQuestions} disabled={!jd.trim() || loading}>
            {loading
              ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
              : <><MessageSquare className="h-4 w-4 mr-2" /> Generate 10 Questions</>
            }
          </Button>
        </div>

        {/* Questions */}
        <div>
          {error && <Alert variant="destructive" className="mb-4"><AlertDescription>{error}</AlertDescription></Alert>}

          {!questions.length && !loading && (
            <Card className="min-h-[400px] flex items-center justify-center">
              <CardContent className="text-center text-slate-400 pt-6">
                <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-20" />
                <p>Questions will appear here</p>
              </CardContent>
            </Card>
          )}

          {loading && (
            <Card className="min-h-[400px] flex items-center justify-center">
              <CardContent className="text-center pt-6">
                <Loader2 className="h-10 w-10 animate-spin mx-auto mb-3 text-primary" />
                <p className="font-medium">Generating questions…</p>
              </CardContent>
            </Card>
          )}

          <div className="space-y-3">
            {questions.map((q, i) => (
              <Card key={i} className="overflow-hidden">
                <button
                  onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                  className="w-full text-left px-4 py-3 flex items-start justify-between gap-3 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex gap-3 items-start">
                    <span className="text-xs font-bold text-slate-400 mt-0.5 w-5 shrink-0">Q{i + 1}</span>
                    <p className="text-sm font-medium text-slate-800">{q.question}</p>
                  </div>
                  {expandedIdx === i
                    ? <ChevronUp className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
                    : <ChevronDown className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
                  }
                </button>

                {expandedIdx === i && (
                  <div className="px-4 pb-4 border-t">
                    <div className="flex items-center justify-between mt-3 mb-2">
                      <Badge variant="outline" className="text-xs">{q.framework}</Badge>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => regenerateAnswer(i)}
                        disabled={regeneratingIdx === i}
                        className="h-7 text-xs"
                      >
                        {regeneratingIdx === i
                          ? <Loader2 className="h-3 w-3 animate-spin mr-1" />
                          : <RefreshCw className="h-3 w-3 mr-1" />
                        }
                        Regenerate
                      </Button>
                    </div>

                    <div className="bg-slate-50 rounded-md p-3">
                      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Answer Framework</p>
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">{q.answer_framework}</p>
                    </div>

                    {q.tips?.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Tips</p>
                        <ul className="space-y-1">
                          {q.tips.map((tip, ti) => (
                            <li key={ti} className="text-xs text-slate-600 flex items-start gap-1.5">
                              <span className="text-slate-400">•</span>
                              {tip}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </Card>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
