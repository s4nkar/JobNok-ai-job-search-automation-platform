'use client'

import { useState, useEffect, useRef, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery } from '@tanstack/react-query'
import { config } from '@/lib/config'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Textarea } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import { useToast } from '@jobnok/ui'
import { cn } from '@jobnok/ui'
import {
  PenLine, Loader2, Copy, Check, Compass, X,
  SlidersHorizontal, ChevronDown, ChevronUp, Download, Save,
} from 'lucide-react'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { CoverLetterSessionDetail, StartupHuntSavedOpportunity, UserProfile } from '@/lib/types'

// Bounds mirror the backend's Pydantic schema (apps/api/app/modules/
// cover_letter/schemas.py::CoverLetterRequest) — kept in sync by hand, same
// pattern used for every other tool's Zod/Pydantic pair in this codebase.
// Previously unbounded on both sides (a real DoS vector per CLAUDE.md's
// input-length rule); this is the client-side half of that fix.
const schema = z.object({
  company: z.string().min(1, 'Required').max(200, 'Keep it under 200 characters'),
  role: z.string().min(1, 'Required').max(200, 'Keep it under 200 characters'),
  selling_points: z.string().min(20, 'Describe at least one selling point').max(3000, 'Keep it under 3,000 characters'),
  resume_text: z.string().max(8000, 'Keep it under 8,000 characters').optional(),
})
type FormData = z.infer<typeof schema>

function CoverLetterInner() {
  const searchParams = useSearchParams()
  const opportunityId = searchParams.get('opportunity_id')
  const jobSearchApplicationId = searchParams.get('job_search_application_id')
  const trackerCompany = searchParams.get('company')
  const trackerRole = searchParams.get('role')
  const sessionId = searchParams.get('session_id')

  const [lead, setLead] = useState<StartupHuntSavedOpportunity | null>(null)
  const [trackerApp, setTrackerApp] = useState<{ company: string; role: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [output, setOutput] = useState('')
  const [copied, setCopied] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  // Reusable default from the profile page (Profile → "Default Selling
  // Points") — pre-fills this form's selling_points field once so it
  // doesn't need retyping per application. Read-only here; editing this
  // field for one letter never writes back to the saved default.
  const { data: profile } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: () => apiGet<UserProfile>('/api/profile'),
  })

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })
  const sellingPointsValue = watch('selling_points') ?? ''
  const resumeTextValue = watch('resume_text') ?? ''
  const companyValue = watch('company') ?? ''
  const roleValue = watch('role') ?? ''
  const inputsSummary = companyValue && roleValue ? `${companyValue} — ${roleValue}` : 'No details yet'

  // Mobile/tablet-only: the input card starts collapsed so the generated
  // letter is reachable without scrolling past the whole form first — same
  // pattern as resume-tailor/recent-job-search's sidebar. Ignored at lg+
  // (always expanded there).
  const [inputsOpen, setInputsOpen] = useState(false)

  useEffect(() => {
    if (opportunityId) {
      apiFetch(`/api/startup-hunt/opportunities/${opportunityId}`)
        .then((r) => r.ok ? r.json() : null)
        .then((found: StartupHuntSavedOpportunity | null) => {
          if (found) {
            setLead(found)
            setValue('company', found.company_name)
            setValue('role', found.role_title)
          }
        })
      return
    }

    if (trackerCompany && trackerRole) {
      setTrackerApp({ company: trackerCompany, role: trackerRole })
      setValue('company', trackerCompany)
      setValue('role', trackerRole)
    }
  }, [opportunityId, trackerCompany, trackerRole, setValue])

  // Reopening a previously-saved letter from My Docs — pre-fills the form
  // and output exactly as if freshly generated, so the user can keep
  // editing, re-download, or re-save it as a new row.
  useEffect(() => {
    if (!sessionId) return
    apiGet<CoverLetterSessionDetail>(`/api/ai/cover-letter/sessions/${sessionId}`)
      .then((session) => {
        setValue('company', session.company)
        setValue('role', session.role)
        setValue('selling_points', session.selling_points)
        if (session.resume_text) setValue('resume_text', session.resume_text)
        setOutput(session.content)
        setSaved(true)
      })
      .catch(() => {
        toast({ title: 'Could not load saved letter', variant: 'destructive' })
      })
  }, [sessionId, setValue, toast])

  // Pre-fill selling_points from the saved profile default exactly once —
  // a ref guard, not a dependency check, so a background refetch of the
  // profile query (react-query refetches on window focus etc.) never
  // overwrites whatever the user has since typed.
  const sellingPointsPrefilledRef = useRef(false)
  useEffect(() => {
    if (!sellingPointsPrefilledRef.current && profile?.key_selling_points) {
      sellingPointsPrefilledRef.current = true
      setValue('selling_points', profile.key_selling_points)
    }
  }, [profile, setValue])

  async function onSubmit(data: FormData) {
    setLoading(true)
    setOutput('')
    setSaved(false)
    setError(null)

    try {
      const res = await apiFetch('/api/ai/cover-letter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })

      if (!res.ok) {
        const json = await res.json()
        setError(json.detail || 'Generation failed. Try again.')
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
        setOutput((prev) => prev + chunk)
      }

      if (opportunityId && fullText.trim()) {
        await apiFetch(`/api/startup-hunt/opportunities/${opportunityId}/artifacts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            artifact_type: 'cover_letter',
            tool_used: 'cover-letter',
            content: fullText,
            metadata: { company: data.company, role: data.role },
          }),
        })
        toast({ title: 'Cover letter saved to lead' })
      }
    } catch {
      setError('Network error. Please try again.')
    }

    setLoading(false)
  }

  async function copy() {
    await navigator.clipboard.writeText(output)
    setCopied(true)
    toast({ title: 'Copied to clipboard!' })
    setTimeout(() => setCopied(false), 3000)
  }

  async function download() {
    // Server-rendered PDF (Jinja + WeasyPrint, reusing resume-tailor's
    // already-installed stack, no new dependency) rather than a plain
    // .txt: most ATS portals and application forms specifically expect a
    // PDF/Word attachment, not .txt.
    setDownloading(true)
    try {
      const res = await apiFetch('/api/ai/cover-letter/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: output }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        toast({ title: 'Download failed', description: json?.detail, variant: 'destructive' })
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const namePart = [companyValue, roleValue].filter(Boolean).join(' - ')
      a.href = url
      a.download = `Cover Letter${namePart ? ` - ${namePart}` : ''}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      toast({ title: 'Network error', description: 'Please try again.', variant: 'destructive' })
    } finally {
      setDownloading(false)
    }
  }

  // Explicit save, not auto-saved on every generation — there's no
  // deterministic dedup key the way resume+JD hash gives resume_tailor, so
  // every click creates a new "My Docs" row rather than silently
  // overwriting a previous save.
  async function saveSession() {
    setSaving(true)
    try {
      const res = await apiFetch('/api/ai/cover-letter/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company: companyValue,
          role: roleValue,
          selling_points: sellingPointsValue,
          resume_text: resumeTextValue || undefined,
          content: output,
          opportunity_id: opportunityId || undefined,
          job_search_application_id: jobSearchApplicationId || undefined,
        }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        toast({ title: 'Could not save', description: json?.detail, variant: 'destructive' })
        return
      }
      setSaved(true)
      toast({ title: 'Saved to My Docs' })
    } catch {
      toast({ title: 'Network error', description: 'Please try again.', variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="flex items-center gap-4 mb-6">
        <div className="hidden sm:flex page-header-icon bg-indigo-100">
          <PenLine className="h-5 w-5 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Cover Letter Generator</h1>
          <p className="text-slate-500 text-sm mt-0.5">AI writes a tailored cover letter — edit inline before sending</p>
        </div>
      </div>

      {lead && (
        <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-800 rounded-xl px-4 py-3 mb-4 text-sm">
          <Compass className="h-4 w-4 flex-shrink-0 text-indigo-500" />
          <span>Pre-filled from <strong>{lead.company_name} — {lead.role_title}</strong>. Add your selling points below.</span>
          <button onClick={() => setLead(null)} className="ml-auto text-indigo-400 hover:text-indigo-700">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {trackerApp && (
        <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-800 rounded-xl px-4 py-3 mb-4 text-sm">
          <PenLine className="h-4 w-4 flex-shrink-0 text-indigo-500" />
          <span>Pre-filled from your tracker: <strong>{trackerApp.company} — {trackerApp.role}</strong>. Add your selling points below.</span>
          <button onClick={() => setTrackerApp(null)} className="ml-auto text-indigo-400 hover:text-indigo-700">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* lg:, not md: — see resume-tailor/recent-job-search's identical
          sidebar comment: at md a fixed sidebar leaves the results column
          too narrow for its own sm: breakpoints, which key off full
          viewport width, not the column's actual space. */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5 items-start">
        {/* Left — inputs, one unified sticky card, matching resume-tailor/
            recent-job-search's sidebar instead of the old plain 2-col grid. */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm lg:sticky lg:top-6 lg:max-h-[calc(100vh-8.5rem)] lg:flex lg:flex-col overflow-hidden">
          {/* Mobile/tablet-only collapsible header */}
          <button
            type="button"
            onClick={() => setInputsOpen(v => !v)}
            className="w-full lg:hidden flex items-center justify-between gap-3 px-5 py-3.5"
          >
            <span className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wider flex-shrink-0">
              <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" />
              Details
            </span>
            <span className="flex items-center gap-1.5 text-xs text-slate-500 font-normal normal-case min-w-0">
              <span className="truncate">{inputsSummary}</span>
              {inputsOpen ? <ChevronUp className="h-3.5 w-3.5 flex-shrink-0" /> : <ChevronDown className="h-3.5 w-3.5 flex-shrink-0" />}
            </span>
          </button>

          <form onSubmit={handleSubmit(onSubmit)} className={cn(
            inputsOpen ? 'block' : 'hidden',
            'lg:block lg:flex-1 lg:min-h-0 lg:overflow-y-auto scrollbar-thin p-5 lg:pt-5 space-y-4',
            inputsOpen && 'border-t border-slate-100 lg:border-t-0',
          )}>
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Company name</Label>
                  <Input placeholder="Acme Corp" className="rounded-xl border-slate-200" maxLength={200} {...register('company')} />
                  {errors.company && <p className="text-xs text-destructive">{errors.company.message}</p>}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Role / position</Label>
                  <Input placeholder="Senior Software Engineer" className="rounded-xl border-slate-200" maxLength={200} {...register('role')} />
                  {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-sm font-medium">Your key selling points</Label>
                  <span className={`text-xs ${sellingPointsValue.length > 3000 ? 'text-destructive' : 'text-slate-400'}`}>
                    {sellingPointsValue.length}/3000
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  {profile?.key_selling_points
                    ? <>Pre-filled from your profile default — edit freely for this letter.</>
                    : <>What makes you the right fit? Be specific. <Link href="/profile" className="text-indigo-500 hover:text-indigo-700 underline">Save a default</Link> to skip retyping next time.</>
                  }
                </p>
                <Textarea
                  {...register('selling_points')}
                  rows={5}
                  maxLength={3000}
                  placeholder="5 years building React apps, led a team of 4 engineers, shipped 3 major product launches..."
                  className="rounded-xl border-slate-200 resize-none"
                />
                {errors.selling_points && <p className="text-xs text-destructive">{errors.selling_points.message}</p>}
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-sm font-medium">
                    Resume text <span className="text-slate-400 font-normal">(optional)</span>
                  </Label>
                  <span className={`text-xs ${resumeTextValue.length > 8000 ? 'text-destructive' : 'text-slate-400'}`}>
                    {resumeTextValue.length}/8000
                  </span>
                </div>
                <Textarea
                  {...register('resume_text')}
                  rows={4}
                  maxLength={8000}
                  placeholder="Paste resume text to help AI tailor the letter more precisely..."
                  className="text-sm rounded-xl border-slate-200 resize-none"
                />
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
              disabled={loading}
            >
              {loading
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
                : <><PenLine className="h-4 w-4 mr-2" /> Generate Cover Letter</>
              }
            </Button>
            <p className="text-center text-[11px] text-slate-400">
              Up to {config.rateLimits.coverLetterPerDay} letters/day on the free tier
            </p>
          </form>
        </div>

        <div className="min-w-0">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm mb-4">{error}</div>
          )}

          {!output && !loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-indigo-50 flex items-center justify-center mx-auto">
                  <PenLine className="h-7 w-7 text-indigo-200" />
                </div>
                <p className="font-semibold text-slate-500">Your cover letter will appear here</p>
                <p className="text-sm text-slate-400">Streams in real-time as it&apos;s generated</p>
              </div>
            </div>
          )}

          {(output || loading) && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-slate-700">Cover Letter</p>
                {output && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={saveSession}
                      disabled={saving || saved}
                      className={cn(
                        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all disabled:opacity-60',
                        saved ? 'bg-emerald-500 text-white' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100',
                      )}
                    >
                      {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : saved ? <Check className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
                      {saving ? 'Saving…' : saved ? 'Saved' : 'Save'}
                    </button>
                    <button
                      onClick={download}
                      disabled={downloading}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all bg-indigo-50 text-indigo-600 hover:bg-indigo-100 disabled:opacity-60"
                    >
                      {downloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                      {downloading ? 'Rendering…' : 'Download PDF'}
                    </button>
                    <button
                      onClick={copy}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                        copied ? 'bg-emerald-500 text-white' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100'
                      }`}
                    >
                      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                )}
              </div>
              <Textarea
                value={output}
                onChange={(e) => { setOutput(e.target.value); setSaved(false) }}
                rows={20}
                className="text-sm leading-relaxed font-sans rounded-xl border-slate-200 resize-none"
                placeholder={loading ? 'Generating…' : ''}
              />
              {loading && (
                <div className="flex items-center gap-2 mt-2 text-sm text-slate-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> Writing…
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function CoverLetterPage() {
  return (
    <Suspense>
      <CoverLetterInner />
    </Suspense>
  )
}
