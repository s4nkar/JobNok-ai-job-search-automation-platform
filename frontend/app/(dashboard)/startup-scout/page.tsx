'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useToast } from '@/components/ui/use-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiFetch } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Radar, Search, Loader2, Globe, Linkedin, ExternalLink,
  BookmarkPlus, CheckCircle, Building2, MapPin, TrendingUp,
} from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

interface DiscoveredCompany {
  name: string
  description: string
  website: string
  domain: string | null
  source: string
  funding_stage: string
  location: string
  size_range: string
}

const FUNDING_STAGES = [
  { value: 'pre-seed', label: 'Pre-Seed' },
  { value: 'seed', label: 'Seed' },
  { value: 'series-a', label: 'Series A' },
  { value: 'series-b', label: 'Series B' },
  { value: 'series-c', label: 'Series C+' },
]

const SIZE_RANGES = [
  { value: '', label: 'Any size' },
  { value: '1-10', label: '1–10 employees' },
  { value: '11-50', label: '11–50 employees' },
  { value: '51-200', label: '51–200 employees' },
  { value: '201-500', label: '201–500 employees' },
]

// ── Page ─────────────────────────────────────────────────────────────────────

export default function StartupScoutPage() {
  const router = useRouter()
  const { toast } = useToast()

  // Form state
  const [location, setLocation] = useState('')
  const [selectedStages, setSelectedStages] = useState<string[]>(['seed'])
  const [industry, setIndustry] = useState('')
  const [sizeRange, setSizeRange] = useState('')

  // Results state
  const [results, setResults] = useState<DiscoveredCompany[]>([])
  const [searching, setSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  // Saved tracking
  const [savedNames, setSavedNames] = useState<Set<string>>(new Set())
  const [savingName, setSavingName] = useState<string | null>(null)

  function toggleStage(stage: string) {
    setSelectedStages((prev) =>
      prev.includes(stage) ? prev.filter((s) => s !== stage) : [...prev, stage]
    )
  }

  async function handleSearch() {
    if (!location.trim()) {
      toast({ title: 'Location required', description: 'Enter a city or country to search.', variant: 'destructive' })
      return
    }
    if (selectedStages.length === 0) {
      toast({ title: 'Select a funding stage', variant: 'destructive' })
      return
    }

    setSearching(true)
    setHasSearched(true)
    setResults([])

    const res = await apiFetch('/api/startup-scout/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        location: location.trim(),
        funding_stages: selectedStages,
        industry: industry.trim(),
        size_range: sizeRange,
      }),
    })

    if (res.ok) {
      const data = await res.json()
      setResults(data.companies || [])
      if ((data.companies || []).length === 0) {
        toast({ title: 'No results', description: 'Try a broader location or different stage.' })
      }
    } else {
      const err = await res.json().catch(() => ({}))
      toast({ title: 'Search failed', description: err.detail || 'Something went wrong.', variant: 'destructive' })
    }

    setSearching(false)
  }

  async function saveToTracker(company: DiscoveredCompany) {
    setSavingName(company.name)
    const res = await apiFetch('/api/startup-scout/companies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: company.name,
        description: company.description,
        funding_stage: company.funding_stage,
        size_range: company.size_range,
        location: company.location,
        website: company.website,
        source: company.source,
      }),
    })

    if (res.ok) {
      setSavedNames((prev) => new Set([...prev, company.name]))
      toast({
        title: 'Saved to tracker',
        description: `${company.name} added. Go to Follow-Up Tracker → Startup Scout to start crawling contacts.`,
      })
    } else {
      const err = await res.json().catch(() => ({}))
      toast({ title: 'Could not save', description: err.detail || 'Something went wrong.', variant: 'destructive' })
    }
    setSavingName(null)
  }

  const stageBadgeColor: Record<string, string> = {
    'pre-seed': 'bg-violet-100 text-violet-700',
    'seed': 'bg-blue-100 text-blue-700',
    'series-a': 'bg-emerald-100 text-emerald-700',
    'series-b': 'bg-orange-100 text-orange-700',
    'series-c': 'bg-red-100 text-red-700',
  }

  return (
    <div className="animate-fade-in">
      {/* ── Header ── */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="page-header-icon bg-cyan-100">
            <Radar className="h-5 w-5 text-cyan-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Startup Scout</h1>
            <p className="text-slate-500 text-sm mt-0.5">Discover startups by location and stage, then crawl for founder contacts</p>
          </div>
        </div>
        <Button
          variant="outline"
          onClick={() => router.push('/tracker')}
          className="rounded-xl h-10 px-4 text-sm border-slate-200 text-slate-600 hover:text-slate-900"
        >
          <Building2 className="h-4 w-4 mr-2" />
          View Tracker
        </Button>
      </div>

      <div className="grid grid-cols-[320px_1fr] gap-6 items-start">
        {/* ── Search panel ── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-6 space-y-5 sticky top-6">
          <p className="text-sm font-semibold text-slate-700">Search filters</p>

          {/* Location */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Location *</Label>
            <Input
              placeholder="e.g. Berlin, London, Remote"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="rounded-xl h-10 text-sm border-slate-200 focus:border-indigo-300"
            />
          </div>

          {/* Funding stages */}
          <div className="space-y-2">
            <Label className="text-xs font-medium text-slate-600">Funding stage *</Label>
            <div className="flex flex-wrap gap-2">
              {FUNDING_STAGES.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => toggleStage(value)}
                  className={cn(
                    'px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors',
                    selectedStages.includes(value)
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600'
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Industry */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Industry (optional)</Label>
            <Input
              placeholder="e.g. AI, FinTech, SaaS, Climate"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="rounded-xl h-10 text-sm border-slate-200 focus:border-indigo-300"
            />
          </div>

          {/* Company size */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Company size (optional)</Label>
            <Select value={sizeRange} onValueChange={setSizeRange}>
              <SelectTrigger className="rounded-xl h-10 text-sm border-slate-200">
                <SelectValue placeholder="Any size" />
              </SelectTrigger>
              <SelectContent>
                {SIZE_RANGES.map(({ value, label }) => (
                  <SelectItem key={value || '__any'} value={value || '__any'} className="text-sm">{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button
            onClick={handleSearch}
            disabled={searching}
            className="w-full gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl h-10"
          >
            {searching ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Searching…</>
            ) : (
              <><Search className="h-4 w-4 mr-2" /> Discover Startups</>
            )}
          </Button>

          {hasSearched && !searching && (
            <p className="text-xs text-slate-400 text-center">
              {results.length} result{results.length !== 1 ? 's' : ''} found
            </p>
          )}
        </div>

        {/* ── Results ── */}
        <div>
          {!hasSearched && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card flex flex-col items-center justify-center h-72">
              <div className="w-16 h-16 rounded-2xl bg-cyan-50 flex items-center justify-center mb-4">
                <Radar className="h-8 w-8 text-cyan-300" />
              </div>
              <p className="font-semibold text-slate-700">Find your next startup</p>
              <p className="text-sm text-slate-400 mt-1 text-center max-w-xs">
                Fill in location and funding stage, then hit Discover. Save interesting companies to crawl for founder contacts.
              </p>
            </div>
          )}

          {searching && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card flex flex-col items-center justify-center h-72">
              <Loader2 className="h-10 w-10 animate-spin text-cyan-400 mb-4" />
              <p className="text-sm text-slate-500">Scanning startup directories…</p>
            </div>
          )}

          {!searching && hasSearched && results.length === 0 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card flex flex-col items-center justify-center h-72">
              <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                <Search className="h-7 w-7 text-slate-300" />
              </div>
              <p className="font-medium text-slate-600">No startups found</p>
              <p className="text-sm text-slate-400 mt-1">Try a broader location, different stage, or remove the industry filter.</p>
            </div>
          )}

          {!searching && results.length > 0 && (
            <div className="space-y-3">
              {results.map((company, i) => {
                const saved = savedNames.has(company.name)
                const saving = savingName === company.name
                const stageKey = company.funding_stage.split(', ')[0].toLowerCase()

                return (
                  <div
                    key={i}
                    className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 flex items-start gap-4 hover:shadow-md transition-shadow"
                  >
                    {/* Icon */}
                    <div className="w-10 h-10 rounded-xl bg-cyan-50 flex items-center justify-center flex-shrink-0">
                      <Building2 className="h-5 w-5 text-cyan-500" />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-900 text-sm leading-tight">{company.name}</p>
                          <div className="flex flex-wrap items-center gap-2 mt-1">
                            {company.location && (
                              <span className="flex items-center gap-1 text-xs text-slate-500">
                                <MapPin className="h-3 w-3" />{company.location}
                              </span>
                            )}
                            {company.funding_stage && (
                              <span className={cn(
                                'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold',
                                stageBadgeColor[stageKey] || 'bg-slate-100 text-slate-600'
                              )}>
                                <TrendingUp className="h-2.5 w-2.5 mr-1" />
                                {company.funding_stage}
                              </span>
                            )}
                            {company.size_range && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                                {company.size_range} people
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {company.website && (
                            <Link
                              href={company.website}
                              target="_blank"
                              className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                              title="Visit website"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                            </Link>
                          )}
                          <Button
                            size="sm"
                            variant={saved ? 'outline' : 'default'}
                            disabled={saved || saving}
                            onClick={() => saveToTracker(company)}
                            className={cn(
                              'h-8 px-3 rounded-xl text-xs font-semibold',
                              saved
                                ? 'border-emerald-200 text-emerald-600 bg-emerald-50 hover:bg-emerald-50'
                                : 'gradient-brand text-white border-0 hover:opacity-90'
                            )}
                          >
                            {saving ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : saved ? (
                              <><CheckCircle className="h-3 w-3 mr-1" /> Saved</>
                            ) : (
                              <><BookmarkPlus className="h-3 w-3 mr-1" /> Save</>
                            )}
                          </Button>
                        </div>
                      </div>

                      {company.description && (
                        <p className="text-xs text-slate-500 mt-2 leading-relaxed line-clamp-2">
                          {company.description}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
