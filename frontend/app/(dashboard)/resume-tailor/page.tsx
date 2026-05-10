'use client'

import { useState, useRef } from 'react'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { useToast } from '@/components/ui/use-toast'
import { Upload, FileText, Loader2, CheckCircle, XCircle, ArrowRight, Info, FileSearch } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { cn } from '@/lib/utils'

interface TailorResult {
  match_score: number
  matched_keywords: string[]
  missing_keywords: Array<{ keyword: string; suggested_placement: string }>
  bullet_rewrites: Array<{ original: string; improved: string }>
  summary: string
}

export default function ResumeTailorPage() {
  const [file, setFile] = useState<File | null>(null)
  const [jd, setJd] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [result, setResult] = useState<TailorResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

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

      try {
        const jsonMatch = fullText.match(/\{[\s\S]*\}/)
        if (jsonMatch) setResult(JSON.parse(jsonMatch[0]))
      } catch { /* raw stream fallback */ }

    } catch {
      setError('Network error. Please try again.')
    }

    setLoading(false)
  }

  const scoreColor = result
    ? result.match_score >= 70 ? 'text-emerald-600' : result.match_score >= 40 ? 'text-amber-600' : 'text-red-600'
    : ''

  const scoreBarColor = result
    ? result.match_score >= 70 ? 'bg-emerald-500' : result.match_score >= 40 ? 'bg-amber-500' : 'bg-red-500'
    : ''

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-violet-100">
          <FileSearch className="h-5 w-5 text-violet-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Resume Tailor</h1>
          <p className="text-slate-500 text-sm mt-0.5">Get an ATS score, missing keywords, and bullet rewrites for your target role</p>
        </div>
      </div>

      {/* Rate limit notice */}
      <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500" />
        <span><strong>{config.rateLimits.resumeTailorPerDay} analyses/day</strong> on the free tier.</span>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Inputs */}
        <div className="space-y-4">
          {/* PDF Upload */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <Label className="text-sm font-semibold text-slate-700 mb-3 block">Resume (PDF)</Label>
            <div
              onClick={() => fileRef.current?.click()}
              className={cn(
                'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200',
                file
                  ? 'border-emerald-300 bg-emerald-50/50'
                  : 'border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/30'
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

          {/* Job Description */}
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

        {/* Results */}
        <div className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm">
              {error}
            </div>
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
              {/* ATS Score */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-semibold text-slate-600">ATS Match Score</p>
                  <span className={cn('text-3xl font-bold', scoreColor)}>{result.match_score}%</span>
                </div>
                <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={cn('h-full rounded-full transition-all duration-700', scoreBarColor)}
                    style={{ width: `${result.match_score}%` }}
                  />
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  {result.match_score >= 70 ? 'Strong match — you\'re a great fit!' : result.match_score >= 40 ? 'Moderate match — some gaps to address' : 'Weak match — needs significant tailoring'}
                </p>
              </div>

              {/* Matched Keywords */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle className="h-4 w-4 text-emerald-500" />
                  <p className="text-sm font-semibold text-slate-700">Matched Keywords <span className="text-slate-400 font-normal">({result.matched_keywords.length})</span></p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {result.matched_keywords.map((k) => (
                    <span key={k} className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-100">
                      {k}
                    </span>
                  ))}
                </div>
              </div>

              {/* Missing Keywords */}
              {result.missing_keywords.length > 0 && (
                <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <XCircle className="h-4 w-4 text-red-400" />
                    <p className="text-sm font-semibold text-slate-700">Missing Keywords <span className="text-slate-400 font-normal">({result.missing_keywords.length})</span></p>
                  </div>
                  <div className="space-y-2">
                    {result.missing_keywords.map(({ keyword, suggested_placement }) => (
                      <div key={keyword} className="flex items-start gap-2 text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-600 border border-red-100 shrink-0">
                          {keyword}
                        </span>
                        <span className="text-slate-400 text-xs pt-0.5">→ {suggested_placement}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bullet Rewrites */}
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

              {/* Summary */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                <p className="text-sm font-semibold text-slate-700 mb-2">AI Assessment</p>
                <p className="text-sm text-slate-600 leading-relaxed">{result.summary}</p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
