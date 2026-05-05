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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">LinkedIn Auto-Fill</h1>
        <p className="text-slate-500 text-sm mt-1">
          Paste a LinkedIn profile URL to extract data and auto-fill your templates
        </p>
      </div>

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>{config.rateLimits.linkedinScrapesPerDay} scrapes/day</strong> on the free tier.
          Profiles are cached for {config.linkedin.cacheTtlDays} days — same URL doesn&apos;t count twice.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-5 gap-6">
        {/* Input */}
        <div className="col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Linkedin className="h-4 w-4 text-blue-600" />
                LinkedIn Profile URL
              </CardTitle>
              <CardDescription>
                Paste any public LinkedIn profile URL
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div className="space-y-1">
                  <Label>Profile URL</Label>
                  <Input
                    placeholder="https://linkedin.com/in/username"
                    {...register('linkedin_url')}
                  />
                  {errors.linkedin_url && (
                    <p className="text-xs text-destructive">{errors.linkedin_url.message}</p>
                  )}
                </div>

                <Button type="submit" className="w-full" disabled={loading}>
                  {loading
                    ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Scraping…</>
                    : <><RefreshCw className="h-4 w-4 mr-2" /> Scrape Profile</>
                  }
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card className="mt-4">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">How it works</p>
              <ol className="text-sm text-slate-600 space-y-2">
                <li className="flex gap-2"><span className="text-slate-400 font-mono">1.</span> Paste the profile URL</li>
                <li className="flex gap-2"><span className="text-slate-400 font-mono">2.</span> We scrape name, role, company, headline</li>
                <li className="flex gap-2"><span className="text-slate-400 font-mono">3.</span> AI enriches open-ended fields</li>
                <li className="flex gap-2"><span className="text-slate-400 font-mono">4.</span> Copy data to fill your templates</li>
              </ol>
            </CardContent>
          </Card>
        </div>

        {/* Results */}
        <div className="col-span-3">
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!profile && !error && !loading && (
            <Card className="min-h-[400px] flex items-center justify-center">
              <CardContent className="text-center text-slate-400 pt-6">
                <Linkedin className="h-12 w-12 mx-auto mb-3 opacity-20" />
                <p>Profile data will appear here</p>
              </CardContent>
            </Card>
          )}

          {loading && (
            <Card className="min-h-[400px] flex items-center justify-center">
              <CardContent className="text-center pt-6">
                <Loader2 className="h-10 w-10 animate-spin mx-auto mb-3 text-blue-500" />
                <p className="text-slate-600 font-medium">Scraping profile…</p>
                <p className="text-slate-400 text-sm mt-1">This can take up to 8 seconds</p>
              </CardContent>
            </Card>
          )}

          {profile && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Scraped Profile</CardTitle>
                  {cached && (
                    <Badge variant="secondary" className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      From cache
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {fieldMap.map(({ key, label }) => {
                  const value = profile[key]
                  if (!value || (Array.isArray(value) && value.length === 0)) return null
                  return (
                    <div key={key} className="grid grid-cols-3 gap-2 py-2 border-b border-slate-100 last:border-0">
                      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</span>
                      <div className="col-span-2 text-sm text-slate-800">
                        {Array.isArray(value) ? value.join(', ') : String(value)}
                      </div>
                    </div>
                  )
                })}

                {profile.skills && profile.skills.length > 0 && (
                  <div className="grid grid-cols-3 gap-2 py-2">
                    <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Skills</span>
                    <div className="col-span-2 flex flex-wrap gap-1">
                      {profile.skills.slice(0, 12).map((s) => (
                        <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
