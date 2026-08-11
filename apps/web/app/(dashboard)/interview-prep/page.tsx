'use client'

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { MessageSquare, Loader2, RefreshCw, ChevronDown, ChevronUp, Info, Compass, X } from 'lucide-react'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { cn } from '@/lib/utils'
import { StartupHuntSavedOpportunity } from '@/lib/types'

interface InterviewQuestion {
  question: string
  framework: string
  answer_framework: string
  tips: string[]
}

function buildJdFromOpportunity(lead: StartupHuntSavedOpportunity): string {
  const parts: string[] = []
  parts.push(`${lead.role_title} at ${lead.company_name}`)
  if (lead.location) parts.push(`Location: ${lead.location}`)
  const cp = lead.company_payload as Record<string, unknown>
  if (cp?.ai_relevance) parts.push(`\nCompany focus: ${cp.ai_relevance}`)
  if (cp?.stage) parts.push(`Stage: ${cp.stage}`)
  if (lead.score_reasons?.length) {
    parts.push(`\nRole signals:\n${lead.score_reasons.map((r: string) => `• ${r}`).join('\n')}`)
  }
  parts.push('\n[Paste or add the full job description below this line for best results]')
  return parts.join('\n')
}

function InterviewPrepInner() {
  const searchParams = useSearchParams()
  const opportunityId = searchParams.get('opportunity_id')

  const [lead, setLead] = useState<StartupHuntSavedOpportunity | null>(null)
  const [jd, setJd] = useState('')
  const [loading, setLoading] = useState(false)
  const [questions, setQuestions] = useState<InterviewQuestion[]>([])
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [regeneratingIdx, setRegeneratingIdx] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const { data: opportunities } = useQuery({
    queryKey: queryKeys.startupHuntOpportunities,
    queryFn: () => apiGet<StartupHuntSavedOpportunity[]>('/api/startup-hunt/opportunities'),
    enabled: !!opportunityId,
  })

  useEffect(() => {
    if (!opportunityId || !opportunities) return
    const found = opportunities.find((r) => r.id === opportunityId)
    if (found) {
      setLead(found)
      setJd(buildJdFromOpportunity(found))
    }
  }, [opportunityId, opportunities])

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
        const qs: InterviewQuestion[] = json.questions || []
        setQuestions(qs)
        setExpandedIdx(0)

        if (opportunityId && qs.length) {
          await apiFetch(`/api/startup-hunt/opportunities/${opportunityId}/artifacts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              artifact_type: 'interview_prep',
              tool_used: 'interview-prep',
              content: JSON.stringify(qs),
              metadata: { question_count: qs.length, company: lead?.company_name, role: lead?.role_title },
            }),
          })
          toast({ title: 'Interview prep saved to lead' })
        }
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
    <div className="animate-fade-in">
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-teal-100">
          <MessageSquare className="h-5 w-5 text-teal-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Interview Prep</h1>
          <p className="text-slate-500 text-sm mt-0.5">Paste the job description — get 10 likely questions with STAR-method answer frameworks</p>
        </div>
      </div>

      {lead && (
        <div className="flex items-center gap-2.5 bg-orange-50 border border-orange-100 text-orange-800 rounded-xl px-4 py-3 mb-4 text-sm">
          <Compass className="h-4 w-4 flex-shrink-0 text-orange-500" />
          <span>Pre-filled from <strong>{lead.company_name} — {lead.role_title}</strong>. Add the full JD below the signals for best results.</span>
          <button onClick={() => { setLead(null); setJd('') }} className="ml-auto text-orange-400 hover:text-orange-700">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500" />
        <span><strong>{config.rateLimits.interviewPrepPerDay} preps/day</strong> on the free tier.</span>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <Label className="text-sm font-semibold text-slate-700 mb-3 block">Job Description</Label>
            <Textarea
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              rows={18}
              placeholder="Paste the full job description here…"
              className="text-sm rounded-xl border-slate-200 resize-none"
            />
          </div>

          <Button
            className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
            onClick={generateQuestions}
            disabled={!jd.trim() || loading}
          >
            {loading
              ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
              : <><MessageSquare className="h-4 w-4 mr-2" /> Generate 10 Questions</>
            }
          </Button>
        </div>

        <div>
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm mb-4">{error}</div>
          )}

          {!questions.length && !loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-teal-50 flex items-center justify-center mx-auto">
                  <MessageSquare className="h-7 w-7 text-teal-200" />
                </div>
                <p className="font-semibold text-slate-500">Questions will appear here</p>
                <p className="text-sm text-slate-400">Paste a job description to generate interview questions</p>
              </div>
            </div>
          )}

          {loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-3">
                <Loader2 className="h-10 w-10 animate-spin mx-auto text-indigo-500" />
                <p className="font-semibold text-slate-700">Generating questions…</p>
                <p className="text-sm text-slate-400">Analysing the job description</p>
              </div>
            </div>
          )}

          {questions.length > 0 && (
            <div className="space-y-2.5">
              {questions.map((q, i) => (
                <div
                  key={i}
                  className={cn(
                    'bg-white rounded-2xl border shadow-card overflow-hidden transition-all duration-200',
                    expandedIdx === i ? 'border-indigo-200 shadow-card-md' : 'border-slate-100'
                  )}
                >
                  <button
                    onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                    className="w-full text-left px-5 py-4 flex items-start justify-between gap-3 hover:bg-slate-50/50 transition-colors"
                  >
                    <div className="flex gap-3 items-start min-w-0">
                      <span className={cn(
                        'text-xs font-bold w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5',
                        expandedIdx === i ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500'
                      )}>
                        {i + 1}
                      </span>
                      <p className="text-sm font-semibold text-slate-800 leading-snug">{q.question}</p>
                    </div>
                    {expandedIdx === i
                      ? <ChevronUp className="h-4 w-4 text-indigo-400 shrink-0 mt-1" />
                      : <ChevronDown className="h-4 w-4 text-slate-400 shrink-0 mt-1" />
                    }
                  </button>

                  {expandedIdx === i && (
                    <div className="px-5 pb-5 border-t border-slate-100">
                      <div className="flex items-center justify-between mt-4 mb-3">
                        <span className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100">
                          {q.framework}
                        </span>
                        <button
                          onClick={() => regenerateAnswer(i)}
                          disabled={regeneratingIdx === i}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                        >
                          {regeneratingIdx === i ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                          Regenerate
                        </button>
                      </div>
                      <div className="bg-slate-50 rounded-xl p-4">
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Answer Framework</p>
                        <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{q.answer_framework}</p>
                      </div>
                      {q.tips?.length > 0 && (
                        <div className="mt-3 bg-amber-50 rounded-xl p-4">
                          <p className="text-[10px] font-bold text-amber-600 uppercase tracking-widest mb-2">Tips</p>
                          <ul className="space-y-1.5">
                            {q.tips.map((tip, ti) => (
                              <li key={ti} className="text-xs text-amber-800 flex items-start gap-2">
                                <span className="text-amber-400 mt-0.5">•</span>
                                {tip}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function InterviewPrepPage() {
  return (
    <Suspense>
      <InterviewPrepInner />
    </Suspense>
  )
}
