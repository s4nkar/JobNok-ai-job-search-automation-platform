'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { config } from '@/lib/config'
import { LinkedInProfile } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { Linkedin, Loader2, RefreshCw, Info, Clock } from 'lucide-react'
import { apiFetch } from '@/lib/api'

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

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

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
        <div className="page-header-icon bg-blue-100">
          <Linkedin className="h-5 w-5 text-blue-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">LinkedIn Auto-Fill</h1>
          <p className="text-slate-500 text-sm mt-0.5">Paste a LinkedIn profile URL to extract data and auto-fill your templates</p>
        </div>
      </div>

      {/* Rate limit notice */}
      <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500" />
        <span>
          <strong>{config.rateLimits.linkedinScrapesPerDay} scrapes/day</strong> on the free tier.
          Profiles are cached for {config.linkedin.cacheTtlDays} days — same URL doesn&apos;t count twice.
        </span>
      </div>

      <div className="grid grid-cols-5 gap-6">
        {/* Input */}
        <div className="col-span-2 space-y-4">
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <div className="flex items-center gap-2.5 mb-4">
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
                  {...register('linkedin_url')}
                />
                {errors.linkedin_url && (
                  <p className="text-xs text-destructive">{errors.linkedin_url.message}</p>
                )}
              </div>

              <Button
                type="submit"
                className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
                disabled={loading}
              >
                {loading
                  ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Scraping…</>
                  : <><RefreshCw className="h-4 w-4 mr-2" /> Scrape Profile</>
                }
              </Button>
            </form>
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">How it works</p>
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

        {/* Results */}
        <div className="col-span-3">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm mb-4">
              {error}
            </div>
          )}

          {!profile && !error && !loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto">
                  <Linkedin className="h-7 w-7 text-blue-200" />
                </div>
                <p className="font-semibold text-slate-500">Profile data will appear here</p>
                <p className="text-sm text-slate-400">Paste a LinkedIn URL to get started</p>
              </div>
            </div>
          )}

          {loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-3">
                <Loader2 className="h-10 w-10 animate-spin mx-auto text-blue-500" />
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
                    <div key={key} className="grid grid-cols-3 gap-3 py-3">
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider pt-0.5">{label}</span>
                      <div className="col-span-2 text-sm text-slate-800">
                        {Array.isArray(value) ? value.join(', ') : String(value)}
                      </div>
                    </div>
                  )
                })}

                {profile.skills && profile.skills.length > 0 && (
                  <div className="grid grid-cols-3 gap-3 py-3">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider pt-0.5">Skills</span>
                    <div className="col-span-2 flex flex-wrap gap-1.5">
                      {profile.skills.slice(0, 12).map((s) => (
                        <span key={s} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100">
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
