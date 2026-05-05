'use client'

import { useState, useRef } from 'react'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useToast } from '@/components/ui/use-toast'
import { Upload, FileText, Loader2, CheckCircle, XCircle, ArrowRight, Info } from 'lucide-react'
import { apiFetch } from '@/lib/api'

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

      // Parse the final JSON result
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
    ? result.match_score >= 70 ? 'text-green-600' : result.match_score >= 40 ? 'text-yellow-600' : 'text-red-600'
    : ''

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Resume Tailor</h1>
        <p className="text-slate-500 text-sm mt-1">
          Get an ATS score, missing keywords, and bullet rewrites for your target role
        </p>
      </div>

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>{config.rateLimits.resumeTailorPerDay} analyses/day</strong> on the free tier.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-2 gap-6">
        {/* Inputs */}
        <div className="space-y-4">
          {/* PDF Upload */}
          <Card>
            <CardContent className="pt-4">
              <Label className="mb-2 block">Resume (PDF)</Label>
              <div
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center cursor-pointer hover:border-slate-300 hover:bg-slate-50 transition-colors"
              >
                {file ? (
                  <div className="flex items-center justify-center gap-2 text-green-600">
                    <CheckCircle className="h-5 w-5" />
                    <span className="text-sm font-medium">{file.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload className="h-8 w-8 mx-auto text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Click to upload your resume PDF</p>
                  </>
                )}
              </div>
              <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
            </CardContent>
          </Card>

          {/* Job Description */}
          <Card>
            <CardContent className="pt-4">
              <Label className="mb-2 block">Job Description</Label>
              <Textarea
                value={jd}
                onChange={(e) => setJd(e.target.value)}
                placeholder="Paste the full job description here…"
                rows={12}
                className="text-sm"
              />
            </CardContent>
          </Card>

          <Button
            className="w-full"
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
          {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}

          {loading && !result && (
            <Card className="min-h-[300px] flex items-center justify-center">
              <CardContent className="text-center pt-6">
                <Loader2 className="h-10 w-10 animate-spin mx-auto mb-3 text-primary" />
                <p className="font-medium text-slate-700">Analysing your resume…</p>
                <p className="text-slate-400 text-sm mt-1">Streaming response in real-time</p>
                {streamText && (
                  <pre className="text-left text-xs text-slate-500 bg-slate-50 p-3 rounded mt-4 max-h-40 overflow-y-auto whitespace-pre-wrap">
                    {streamText.slice(-500)}
                  </pre>
                )}
              </CardContent>
            </Card>
          )}

          {result && (
            <>
              {/* ATS Score */}
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium text-slate-600">ATS Match Score</p>
                    <span className={`text-2xl font-bold ${scoreColor}`}>{result.match_score}%</span>
                  </div>
                  <Progress value={result.match_score} className="h-3" />
                </CardContent>
              </Card>

              {/* Matched Keywords */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    Matched Keywords ({result.matched_keywords.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {result.matched_keywords.map((k) => (
                      <Badge key={k} variant="success" className="text-xs">{k}</Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Missing Keywords */}
              {result.missing_keywords.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <XCircle className="h-4 w-4 text-red-500" />
                      Missing Keywords ({result.missing_keywords.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {result.missing_keywords.map(({ keyword, suggested_placement }) => (
                        <div key={keyword} className="flex items-start gap-2 text-sm">
                          <Badge variant="destructive" className="text-xs shrink-0">{keyword}</Badge>
                          <span className="text-slate-500 text-xs">→ {suggested_placement}</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Bullet Rewrites */}
              {result.bullet_rewrites.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Top Bullet Rewrites</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {result.bullet_rewrites.map((b, i) => (
                        <div key={i} className="space-y-1">
                          <div className="flex items-start gap-2">
                            <span className="text-xs text-slate-400 mt-0.5 shrink-0">Before</span>
                            <p className="text-xs text-slate-500 line-through">{b.original}</p>
                          </div>
                          <div className="flex items-start gap-2">
                            <ArrowRight className="h-3 w-3 text-green-500 mt-0.5 shrink-0" />
                            <p className="text-xs text-green-700 font-medium">{b.improved}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Summary */}
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm">AI Assessment</CardTitle></CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-600 leading-relaxed">{result.summary}</p>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
