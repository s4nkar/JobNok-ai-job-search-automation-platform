'use client'

import { useState, useRef, useEffect, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import {
  Upload, FileText, Loader2, CheckCircle, XCircle, ArrowRight,
  Info, FileSearch, X, Compass, Download, LayoutTemplate,
  Sparkles, AlertTriangle, BarChart3, Pencil,
} from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { cn } from '@/lib/utils'
import { StartupHuntSavedOpportunity } from '@/lib/types'

interface TailorResult {
  match_score: number
  matched_keywords: string[]
  missing_keywords: Array<{ keyword: string; suggested_placement: string }>
  bullet_rewrites: Array<{ original: string; improved: string }>
  summary: string
  target_role?: string
  target_company?: string
  profile_headline?: string
  tailored_summary?: string
  // Phase 4 additions — produced by the deterministic matcher
  score_breakdown?: {
    core_skills?: number
    responsibilities?: number
    domain?: number
    ats_keywords?: number
    seniority?: number
  }
  transferable_strengths?: string[]
  critical_missing?: string[]
  degraded?: boolean
}

const SCORE_LABELS: Record<string, string> = {
  core_skills: 'Core Skills',
  responsibilities: 'Responsibilities',
  domain: 'Domain Fit',
  ats_keywords: 'ATS Keywords',
  seniority: 'Seniority Fit',
}

function scoreBarTone(score: number): string {
  if (score >= 70) return 'bg-emerald-500'
  if (score >= 40) return 'bg-amber-500'
  return 'bg-red-500'
}

function buildJdFromOpportunity(lead: StartupHuntSavedOpportunity): string {
  const parts: string[] = []
  parts.push(`${lead.role_title} at ${lead.company_name}`)
  if (lead.location) parts.push(`Location: ${lead.location}`)
  const cp = lead.company_payload as Record<string, unknown>
  if (cp?.ai_relevance) parts.push(`\nCompany focus: ${cp.ai_relevance}`)
  if (cp?.stage) parts.push(`Stage: ${cp.stage}`)
  if (lead.score_reasons?.length) {
    // Filter "Company signal:" — its content is already present in Company focus above.
    const signals = lead.score_reasons.filter((r: string) => !r.startsWith('Company signal:'))
    if (signals.length) {
      parts.push(`\nRole signals:\n${signals.map((r: string) => `• ${r}`).join('\n')}`)
    }
  }
  return parts.join('\n')
}

function ResumeTailorInner() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const opportunityId = searchParams.get('opportunity_id')

  const [lead, setLead] = useState<StartupHuntSavedOpportunity | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [jd, setJd] = useState('')
  const [loading, setLoading] = useState(false)
  const [prefilling, setPrefilling] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [result, setResult] = useState<TailorResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [generating, setGenerating] = useState(false)

  const fileRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (!opportunityId) return
    setPrefilling(true)
    apiFetch(`/api/startup-hunt/opportunities`)
      .then((r) => r.json())
      .then((rows: StartupHuntSavedOpportunity[]) => {
        const found = rows.find((r) => r.id === opportunityId)
        if (found) {
          setLead(found)
          setJd(buildJdFromOpportunity(found))
        }
      })
      .finally(() => setPrefilling(false))
  }, [opportunityId])

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f && f.type === 'application/pdf') {
      setFile(f)
    } else if (f) {
      toast({ title: 'PDF only', description: 'Please upload a PDF file.', variant: 'destructive' })
    }
  }

  async function analyzeResume() {
    if (!file || !jd.trim()) return
    setLoading(true)
    setStreamText('')
    setResult(null)
    setError(null)

    const formData = new FormData()
    formData.append('resume', file)
    formData.append('job_description', jd)

    try {
      const res = await apiFetch('/api/ai/tailor', { method: 'POST', body: formData })

      if (!res.ok) {
        const json = await res.json()
        setError(json.detail || 'Analysis failed. Please try again.')
        setLoading(false)
        return
      }

      if (!res.body) { setLoading(false); return }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let fullText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value)
        fullText += chunk
        setStreamText(fullText)
      }

      let parsed: TailorResult | null = null
      try {
        const jsonMatch = fullText.match(/\{[\s\S]*\}/)
        if (jsonMatch) parsed = JSON.parse(jsonMatch[0])
      } catch { /* raw stream fallback */ }

      if (parsed) {
        setResult(parsed)
        if (opportunityId) {
          await apiFetch(`/api/startup-hunt/opportunities/${opportunityId}/artifacts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              artifact_type: 'resume_analysis',
              tool_used: 'resume-tailor',
              content: JSON.stringify(parsed),
              metadata: { match_score: parsed.match_score, company: lead?.company_name, role: lead?.role_title },
            }),
          })
          toast({ title: 'Analysis saved to lead' })
        }
      }
    } catch {
      setError('Network error. Please try again.')
    }

    setLoading(false)
  }

  async function generatePdf() {
    if (!result) return
    if (selectedTemplate === 'classic' && !classicProfileReady(profile)) {
      toast({ title: 'Complete your profile first', description: 'Add photo, name, phone and city to use the Classic template.', variant: 'destructive' })
      router.push('/profile')
      return
    }
    setGenerating(true)
    try {
      const res = await apiFetch('/api/ai/tailor/generate-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: 'standard',
          analysis: result,
          opportunity_id: opportunityId || undefined,
        }),
      })
      if (!res.ok) {
        const json = await res.json()
        toast({ title: json.detail || 'Generation failed', variant: 'destructive' })
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `tailored_cv_standard.pdf`
      a.click()
      URL.revokeObjectURL(url)
      toast({ title: 'PDF downloaded!' })
    } catch {
      toast({ title: 'Network error', variant: 'destructive' })
    } finally {
      setGenerating(false)
    }
  }

  const scoreColor = result
    ? result.match_score >= 70 ? 'text-emerald-600' : result.match_score >= 40 ? 'text-amber-600' : 'text-red-600'
    : ''
  const scoreBarColor = result
    ? result.match_score >= 70 ? 'bg-emerald-500' : result.match_score >= 40 ? 'bg-amber-500' : 'bg-red-500'
    : ''

  return (
    <div className="animate-fade-in">
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-violet-100">
          <FileSearch className="h-5 w-5 text-violet-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Resume Tailor</h1>
          <p className="text-slate-500 text-sm mt-0.5">Get an ATS score, missing keywords, and bullet rewrites — then generate a tailored PDF</p>
        </div>
      </div>

      {lead && (
        <div className="flex items-center gap-2.5 bg-orange-50 border border-orange-100 text-orange-800 rounded-xl px-4 py-3 mb-4 text-sm">
          <Compass className="h-4 w-4 flex-shrink-0 text-orange-500" />
          <span>Pre-filled from <strong>{lead.company_name} — {lead.role_title}</strong>. No full JD stored — add it below the signals for best results.</span>
          <button onClick={() => { setLead(null); setJd('') }} className="ml-auto text-orange-400 hover:text-orange-700">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {prefilling && (
        <div className="flex items-center gap-2 text-sm text-slate-500 mb-4">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading lead details…
        </div>
      )}

      <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500" />
        <span><strong>{config.rateLimits.resumeTailorPerDay} analyses/day</strong> on the free tier.</span>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Left — inputs */}
        <div className="space-y-4">
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <Label className="text-sm font-semibold text-slate-700 mb-3 block">Resume (PDF)</Label>
            <div
              onClick={() => fileRef.current?.click()}
              className={cn(
                'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200',
                file ? 'border-emerald-300 bg-emerald-50/50' : 'border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/30'
              )}
            >
              {file ? (
                <div className="flex items-center justify-center gap-2.5 text-emerald-600">
                  <CheckCircle className="h-5 w-5" />
                  <span className="text-sm font-medium">{file.name}</span>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mx-auto">
                    <Upload className="h-5 w-5 text-slate-400" />
                  </div>
                  <p className="text-sm font-medium text-slate-600">Click to upload your resume</p>
                  <p className="text-xs text-slate-400">PDF files only</p>
                </div>
              )}
            </div>
            <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <Label className="text-sm font-semibold text-slate-700 mb-3 block">Job Description</Label>
            <Textarea
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              placeholder="Paste the full job description here…"
              rows={12}
              className="text-sm rounded-xl border-slate-200 resize-none"
            />
          </div>

          <Button
            className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
            onClick={analyzeResume}
            disabled={!file || !jd.trim() || loading}
          >
            {loading
              ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analysing…</>
              : <><FileText className="h-4 w-4 mr-2" /> Analyse Resume</>
            }
          </Button>
        </div>

        {/* Right — results */}
        <div className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm">{error}</div>
          )}

          {loading && !result && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[300px] flex items-center justify-center p-8">
              <div className="text-center space-y-3">
                <Loader2 className="h-10 w-10 animate-spin mx-auto text-indigo-500" />
                <div>
                  <p className="font-semibold text-slate-700">Analysing your resume…</p>
                  <p className="text-slate-400 text-sm mt-1">Streaming response in real-time</p>
                </div>
                {streamText && (
                  <pre className="text-left text-xs text-slate-500 bg-slate-50 p-3 rounded-xl mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap">
                    {streamText.slice(-500)}
                  </pre>
                )}
              </div>
            </div>
          )}

          {!result && !loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[300px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-violet-50 flex items-center justify-center mx-auto">
                  <FileSearch className="h-7 w-7 text-violet-300" />
                </div>
                <p className="font-medium text-slate-500">Results will appear here</p>
                <p className="text-sm text-slate-400">Upload your resume and paste a job description to start</p>
              </div>
            </div>
          )}

          {result && (
            <>
              {/* Target role banner */}
              {(result.target_role || result.target_company) && (
                <div className="flex items-center gap-2.5 bg-violet-50 border border-violet-100 text-violet-800 rounded-xl px-4 py-3 text-sm">
                  <FileText className="h-4 w-4 flex-shrink-0 text-violet-500" />
                  <span>Tailored for <strong>{result.target_role}{result.target_company ? ` at ${result.target_company}` : ''}</strong></span>
                </div>
              )}

              {/* Proposed headline */}
              {result.profile_headline && (
                <div className="bg-white rounded-2xl border border-violet-100 shadow-card p-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Suggested CV Headline</p>
                  <p className="text-sm font-medium text-violet-700">{result.profile_headline}</p>
                </div>
              )}

              {/* Tailored summary */}
              {result.tailored_summary && (
                <div className="bg-white rounded-2xl border border-violet-100 shadow-card p-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Tailored Summary</p>
                  <p className="text-sm text-slate-600 leading-relaxed">{result.tailored_summary}</p>
                </div>
              )}

              {/* ATS Score */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-semibold text-slate-600">ATS Match Score</p>
                  <span className={cn('text-3xl font-bold', scoreColor)}>{result.match_score}%</span>
                </div>
                <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                  <div className={cn('h-full rounded-full transition-all duration-700', scoreBarColor)} style={{ width: `${result.match_score}%` }} />
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  {result.match_score >= 70 ? "Strong match — you're a great fit!" : result.match_score >= 40 ? 'Moderate match — some gaps to address' : 'Weak match — needs significant tailoring'}
                </p>
              </div>

              {/* Degraded mode notice — embeddings were unavailable */}
              {result.degraded && (
                <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-100 text-amber-800 rounded-xl px-4 py-3 text-sm">
                  <AlertTriangle className="h-4 w-4 flex-shrink-0 text-amber-500 mt-0.5" />
                  <span>Semantic matching unavailable — scores are based on keyword overlap only. Results are still useful but less nuanced than usual.</span>
                </div>
              )}

              {/* Score breakdown by category */}
              {result.score_breakdown && Object.values(result.score_breakdown).some((v) => typeof v === 'number') && (
                <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <BarChart3 className="h-4 w-4 text-indigo-500" />
                    <p className="text-sm font-semibold text-slate-700">Score Breakdown</p>
                  </div>
                  <div className="space-y-2.5">
                    {Object.entries(result.score_breakdown)
                      .filter(([, v]) => typeof v === 'number')
                      .map(([key, value]) => (
                        <div key={key}>
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-slate-500 font-medium">{SCORE_LABELS[key] || key}</span>
                            <span className="text-slate-700 font-semibold tabular-nums">{value as number}%</span>
                          </div>
                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={cn('h-full rounded-full transition-all duration-700', scoreBarTone(value as number))}
                              style={{ width: `${value}%` }}
                            />
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Transferable strengths — partial matches the user can lean into */}
              {result.transferable_strengths && result.transferable_strengths.length > 0 && (
                <div className="bg-white rounded-2xl border border-amber-100 shadow-card p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Sparkles className="h-4 w-4 text-amber-500" />
                    <p className="text-sm font-semibold text-slate-700">Transferable Strengths <span className="text-slate-400 font-normal">({result.transferable_strengths.length})</span></p>
                  </div>
                  <p className="text-xs text-slate-400 mb-3">Requirements where you have related — but not explicit — experience. Reframe these honestly to strengthen alignment.</p>
                  <div className="space-y-2">
                    {result.transferable_strengths.map((s, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm">
                        <ArrowRight className="h-3.5 w-3.5 text-amber-500 mt-1 shrink-0" />
                        <span className="text-slate-600 leading-relaxed">{s}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Critical missing — hard gaps the user shouldn't try to fake */}
              {result.critical_missing && result.critical_missing.length > 0 && (
                <div className="bg-white rounded-2xl border border-red-100 shadow-card p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    <p className="text-sm font-semibold text-slate-700">Critical Gaps <span className="text-slate-400 font-normal">({result.critical_missing.length})</span></p>
                  </div>
                  <p className="text-xs text-slate-400 mb-3">Requirements with no matching evidence in your resume. Don&apos;t fabricate experience — instead, address these in your cover letter or accept them as honest gaps.</p>
                  <div className="space-y-2">
                    {result.critical_missing.map((g, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm">
                        <XCircle className="h-3.5 w-3.5 text-red-400 mt-1 shrink-0" />
                        <span className="text-slate-600 leading-relaxed">{g}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Matched */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle className="h-4 w-4 text-emerald-500" />
                  <p className="text-sm font-semibold text-slate-700">Matched Keywords <span className="text-slate-400 font-normal">({result.matched_keywords.length})</span></p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {result.matched_keywords.map((k) => (
                    <span key={k} className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-100">{k}</span>
                  ))}
                </div>
              </div>

              {/* Missing */}
              {result.missing_keywords.length > 0 && (
                <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <XCircle className="h-4 w-4 text-red-400" />
                    <p className="text-sm font-semibold text-slate-700">Missing Keywords <span className="text-slate-400 font-normal">({result.missing_keywords.length})</span></p>
                  </div>
                  <div className="space-y-2">
                    {result.missing_keywords.map(({ keyword, suggested_placement }) => (
                      <div key={keyword} className="flex items-start gap-2 text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-600 border border-red-100 shrink-0">{keyword}</span>
                        <span className="text-slate-400 text-xs pt-0.5">→ {suggested_placement}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bullet rewrites */}
              {result.bullet_rewrites.length > 0 && (
                <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                  <p className="text-sm font-semibold text-slate-700 mb-3">Top Bullet Rewrites</p>
                  <div className="space-y-4">
                    {result.bullet_rewrites.map((b, i) => (
                      <div key={i} className="space-y-1.5 p-3 rounded-xl bg-slate-50">
                        <div className="flex items-start gap-2">
                          <span className="text-xs font-medium text-slate-400 mt-0.5 shrink-0 w-12">Before</span>
                          <p className="text-xs text-slate-400 line-through">{b.original}</p>
                        </div>
                        <div className="flex items-start gap-2">
                          <ArrowRight className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0 w-12 min-w-[12px]" />
                          <p className="text-xs text-emerald-700 font-medium">{b.improved}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Assessment */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                <p className="text-sm font-semibold text-slate-700 mb-2">AI Assessment</p>
                <p className="text-sm text-slate-600 leading-relaxed">{result.summary}</p>
              </div>

              {/* ── Build Resume ── */}
              <div className="bg-white rounded-2xl border border-indigo-100 shadow-card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <LayoutTemplate className="h-4 w-4 text-indigo-500" />
                  <p className="text-sm font-semibold text-slate-700">Build Tailored Resume</p>
                </div>
                <p className="text-xs text-slate-500 mb-4">
                  Open the editor to review pre-filled content, pick from 16 layouts, and download your PDF — or quick-download with the Standard layout.
                </p>
                <div className="flex gap-3">
                  <Button
                    onClick={() => {
                      try {
                        sessionStorage.setItem('resume_tailor_analysis', JSON.stringify(result))
                        if (file) {
                          const url = URL.createObjectURL(file)
                          sessionStorage.setItem('resume_original_pdf_url', url)
                        }
                      } catch { /* sessionStorage full — editor will handle gracefully */ }
                      router.push('/resume-tailor/editor')
                    }}
                    className="flex-1 h-10 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold text-sm"
                  >
                    <Pencil className="h-4 w-4 mr-2" /> Edit &amp; Build Resume
                  </Button>
                  <Button
                    onClick={generatePdf}
                    disabled={generating}
                    variant="outline"
                    className="h-10 rounded-xl text-sm border-slate-200 text-slate-600 hover:bg-slate-50"
                  >
                    {generating
                      ? <Loader2 className="h-4 w-4 animate-spin" />
                      : <Download className="h-4 w-4" />
                    }
                  </Button>
                </div>
                <p className="text-[10px] text-slate-400 mt-2 text-center">Quick-download uses the Standard layout</p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ResumeTailorPage() {
  return (
    <Suspense>
      <ResumeTailorInner />
    </Suspense>
  )
}
