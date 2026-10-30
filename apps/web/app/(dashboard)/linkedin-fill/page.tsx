'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { config } from '@/lib/config'
import { LinkedInProfile } from '@/lib/types'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import { useToast } from '@jobnok/ui'
import { Linkedin, Loader2, RefreshCw, Clock, SlidersHorizontal, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { cn } from '@jobnok/ui'

// Scraping a third party's profile pages carries real ToS/legal risk that
// hasn't been reviewed yet - the tool is intentionally taken off the air
// (input + submit disabled, banner shown) until that review happens, rather
// than silently left reachable. Flip this back to false to re-enable - no
// other code path needs to change.
const TOOL_TEMPORARILY_DISABLED = true

const schema = z.object({
  linkedin_url: z
    .string()
    .url('Enter a valid URL')
    .includes('linkedin.com', { message: 'Must be a LinkedIn URL' }),
})
type FormData = z.infer<typeof schema>

export default function LinkedInFillPage() {
  const [loading, setLoading] = useState(false)
  const [profile, setProfile] = useState<LinkedInProfile | null>(null)
  const [cached, setCached] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const { register, handleSubmit, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })
  const urlValue = watch('linkedin_url') ?? ''

  // Mobile/tablet-only: the input card starts collapsed so results are
  // reachable without scrolling past the form first — same pattern as
  // cover-letter/interview-prep/resume-tailor's sidebar. Ignored at lg+
  // (always expanded there).
  const [inputsOpen, setInputsOpen] = useState(false)

  async function onSubmit(data: FormData) {
    setLoading(true)
    setError(null)
    setProfile(null)

    try {
      const res = await apiFetch('/api/scrape/linkedin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ linkedin_url: data.linkedin_url }),
      })
      const json = await res.json()

      if (!res.ok) {
        setError(json.detail || json.error || 'Scrape failed. Try again.')
      } else {
        setProfile(json.data)
        setCached(json.cached || false)
        toast({ title: 'Profile loaded!', description: cached ? 'Served from cache.' : 'Freshly scraped.' })
      }
    } catch {
      setError('Network error. Please try again.')
    }

    setLoading(false)
  }

  const fieldMap: Array<{ key: keyof LinkedInProfile; label: string }> = [
    { key: 'name', label: 'Full Name' },
    { key: 'headline', label: 'Headline' },
    { key: 'current_role', label: 'Current Role' },
    { key: 'current_company', label: 'Current Company' },
    { key: 'location', label: 'Location' },
    { key: 'about', label: 'About' },
    { key: 'recent_experience', label: 'Recent Experience' },
    { key: 'education', label: 'Education' },
  ]

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-6">
        <div className="hidden sm:flex page-header-icon bg-blue-100">
          <Linkedin className="h-5 w-5 text-blue-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">LinkedIn Auto-Fill</h1>
          <p className="text-slate-500 text-sm mt-0.5">Paste a LinkedIn profile URL to extract data and auto-fill your templates</p>
        </div>
      </div>

      {TOOL_TEMPORARILY_DISABLED && (
        <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-100 text-amber-800 rounded-xl px-4 py-3 mb-5 text-sm">
          <AlertTriangle className="h-4 w-4 flex-shrink-0 text-amber-500 mt-0.5" />
          <span>This tool is temporarily unavailable while we review it. Check back soon.</span>
        </div>
      )}

      {/* lg:, not md: — see resume-tailor/recent-job-search's identical
          sidebar comment: at md a fixed sidebar leaves the results column
          too narrow for its own sm: breakpoints, which key off full
          viewport width, not the column's actual space. */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5 items-start">
        {/* Left — inputs, one unified sticky card, matching the other
            tools' sidebar instead of the old plain 5-col grid. */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm lg:sticky lg:top-6 lg:max-h-[calc(100vh-8.5rem)] lg:flex lg:flex-col overflow-hidden">
          {/* Mobile/tablet-only collapsible header */}
          <button
            type="button"
            onClick={() => setInputsOpen(v => !v)}
            className="w-full lg:hidden flex items-center justify-between gap-3 px-5 py-3.5"
          >
            <span className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wider flex-shrink-0">
              <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" />
              Profile URL
            </span>
            <span className="flex items-center gap-1.5 text-xs text-slate-500 font-normal normal-case min-w-0">
              <span className="truncate">{urlValue || 'No profile URL yet'}</span>
              {inputsOpen ? <ChevronUp className="h-3.5 w-3.5 flex-shrink-0" /> : <ChevronDown className="h-3.5 w-3.5 flex-shrink-0" />}
            </span>
          </button>

          <div className={cn(
            inputsOpen ? 'block' : 'hidden',
            'lg:block lg:flex-1 lg:min-h-0 lg:overflow-y-auto scrollbar-thin p-5 lg:pt-5 space-y-4',
            inputsOpen && 'border-t border-slate-100 lg:border-t-0',
          )}>
            <div className="flex items-center gap-2.5 mb-1 hidden lg:flex">
              <div className="w-7 h-7 rounded-lg bg-blue-100 flex items-center justify-center">
                <Linkedin className="h-3.5 w-3.5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800">LinkedIn Profile URL</p>
                <p className="text-xs text-slate-500">Paste any public LinkedIn profile URL</p>
              </div>
            </div>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Profile URL</Label>
                <Input
                  placeholder="https://linkedin.com/in/username"
                  className="rounded-xl border-slate-200"
                  disabled={TOOL_TEMPORARILY_DISABLED}
                  {...register('linkedin_url')}
                />
                {errors.linkedin_url && (
                  <p className="text-xs text-destructive">{errors.linkedin_url.message}</p>
                )}
              </div>

              <Button
                type="submit"
                className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
                disabled={loading || TOOL_TEMPORARILY_DISABLED}
              >
                {TOOL_TEMPORARILY_DISABLED
                  ? 'Currently Unavailable'
                  : loading
                    ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Scraping…</>
                    : <><RefreshCw className="h-4 w-4 mr-2" /> Scrape Profile</>
                }
              </Button>
              <p className="text-center text-[11px] text-slate-400">
                Up to {config.rateLimits.linkedinScrapesPerDay} scrapes/day on the free tier - cached for {config.linkedin.cacheTtlDays} days per URL
              </p>
            </form>

            <div className="pt-2 border-t border-slate-100">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3 mt-3">How it works</p>
              <ol className="space-y-3">
                {[
                  'Paste the profile URL',
                  'We scrape name, role, company, headline',
                  'AI enriches open-ended fields',
                  'Copy data to fill your templates',
                ].map((step, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm text-slate-600">
                    <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                      {i + 1}
                    </span>
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>

        {/* Results */}
        <div className="min-w-0">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm mb-4">
              {error}
            </div>
          )}

          {!profile && !error && !loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm min-h-[18rem] flex items-center justify-center p-6">
              <div className="text-center space-y-1">
                <p className="font-semibold text-slate-500">Profile data will appear here</p>
                <p className="text-sm text-slate-400">Paste a LinkedIn URL to get started</p>
              </div>
            </div>
          )}

          {loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-3">
                <Loader2 className="h-10 w-10 animate-spin mx-auto text-indigo-500" />
                <div>
                  <p className="font-semibold text-slate-700">Scraping profile…</p>
                  <p className="text-slate-400 text-sm mt-1">This can take up to 8 seconds</p>
                </div>
              </div>
            </div>
          )}

          {profile && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm font-semibold text-slate-700">Scraped Profile</p>
                {cached && (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600 text-xs font-medium">
                    <Clock className="h-3 w-3" />
                    From cache
                  </span>
                )}
              </div>
              <div className="space-y-0 divide-y divide-slate-50">
                {fieldMap.map(({ key, label }) => {
                  const value = profile[key]
                  if (!value || (Array.isArray(value) && value.length === 0)) return null
                  return (
                    <div key={key} className="grid grid-cols-1 sm:grid-cols-3 gap-1.5 sm:gap-3 py-3">
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider pt-0.5">{label}</span>
                      <div className="sm:col-span-2 text-sm text-slate-800">
                        {Array.isArray(value) ? value.join(', ') : String(value)}
                      </div>
                    </div>
                  )
                })}

                {profile.skills && profile.skills.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5 sm:gap-3 py-3">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider pt-0.5">Skills</span>
                    <div className="sm:col-span-2 flex flex-wrap gap-1.5">
                      {profile.skills.slice(0, 12).map((s) => (
                        <span key={s} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
