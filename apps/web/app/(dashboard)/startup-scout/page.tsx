'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import Papa from 'papaparse'
import { useToast } from '@jobnok/ui'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import {
  Select, SelectContent, SelectItem,
  SelectTrigger, SelectValue,
} from '@jobnok/ui'
import { apiFetch } from '@/lib/api'
import { cn } from '@jobnok/ui'
import {
  Radar, Search, Loader2, ExternalLink, BookmarkPlus,
  CheckCircle, Building2, MapPin, TrendingUp, Download,
  Database, ChevronLeft, ChevronRight, SlidersHorizontal,
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

interface SearchMeta {
  total: number
  limit: number
  queries_run: number
  sources: Record<string, number>
  location: string
  industry: string | null
  funding_stages: string[]
}

// ── Constants ─────────────────────────────────────────────────────────────────

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

const RESULT_LIMITS = [
  { value: '25', label: '25 results' },
  { value: '50', label: '50 results' },
  { value: '100', label: '100 results' },
  { value: '200', label: '200 results' },
]

const PAGE_SIZE = 10

// ── Source styling ─────────────────────────────────────────────────────────

const SOURCE_PILL: Record<string, string> = {
  Crunchbase: 'bg-blue-50   text-blue-600   ring-blue-200',
  Wellfound: 'bg-teal-50   text-teal-600   ring-teal-200',
  Dealroom: 'bg-violet-50 text-violet-600 ring-violet-200',
  'Germanyy.ai': 'bg-orange-50 text-orange-600 ring-orange-200',
  Seedtable: 'bg-rose-50   text-rose-600   ring-rose-200',
  'Y Combinator': 'bg-amber-50  text-amber-600  ring-amber-200',
  Tracxn: 'bg-cyan-50   text-cyan-600   ring-cyan-200',
  'Crunchbase API': 'bg-blue-50   text-blue-700   ring-blue-300',
  TheirStack: 'bg-indigo-50 text-indigo-600 ring-indigo-200',
  Startupdetector: 'bg-lime-50   text-lime-700   ring-lime-200',
  F6S: 'bg-fuchsia-50 text-fuchsia-600 ring-fuchsia-200',
}

const SOURCE_DOT: Record<string, string> = {
  Crunchbase: 'bg-blue-500',
  Wellfound: 'bg-teal-500',
  Dealroom: 'bg-violet-500',
  'Germanyy.ai': 'bg-orange-500',
  Seedtable: 'bg-rose-500',
  'Y Combinator': 'bg-amber-500',
  Tracxn: 'bg-cyan-500',
  'Crunchbase API': 'bg-blue-600',
  TheirStack: 'bg-indigo-500',
  Startupdetector: 'bg-lime-600',
  F6S: 'bg-fuchsia-500',
}

const STAGE_PILL: Record<string, string> = {
  'Pre-Seed': 'bg-purple-50 text-purple-600 ring-purple-200',
  'Seed': 'bg-blue-50   text-blue-600   ring-blue-200',
  'Series A': 'bg-emerald-50 text-emerald-600 ring-emerald-200',
  'Series B': 'bg-amber-50  text-amber-600  ring-amber-200',
  'Series C': 'bg-red-50    text-red-600    ring-red-200',
  'Series C+': 'bg-red-50    text-red-600    ring-red-200',
  'Angel': 'bg-pink-50   text-pink-600   ring-pink-200',
}

// ── Smart page range (shows at most 7 page numbers) ──────────────────────────

function pageRange(current: number, total: number): (number | '…')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const delta = 2
  const left = Math.max(2, current - delta)
  const right = Math.min(total - 1, current + delta)
  const pages: (number | '…')[] = [1]
  if (left > 2) pages.push('…')
  for (let p = left; p <= right; p++) pages.push(p)
  if (right < total - 1) pages.push('…')
  pages.push(total)
  return pages
}

// ── Skeleton card ─────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 p-5 flex items-start gap-4 animate-pulse">
      <div className="w-10 h-10 rounded-xl bg-slate-100 flex-shrink-0" />
      <div className="flex-1 space-y-2.5">
        <div className="h-3.5 w-40 bg-slate-100 rounded-full" />
        <div className="flex gap-2">
          <div className="h-3 w-20 bg-slate-100 rounded-full" />
          <div className="h-3 w-14 bg-slate-100 rounded-full" />
        </div>
        <div className="h-3 w-full bg-slate-100 rounded-full" />
        <div className="h-3 w-3/4 bg-slate-100 rounded-full" />
      </div>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function StartupScoutPage() {
  const router = useRouter()
  const { toast } = useToast()

  // ── Form state ────────────────────────────────────────────────────────────
  const [location, setLocation] = useState('')
  const [selectedStages, setSelectedStages] = useState<string[]>(['seed'])
  const [industry, setIndustry] = useState('')
  const [sizeRange, setSizeRange] = useState('')
  const [limit, setLimit] = useState('50')

  // ── Result state ──────────────────────────────────────────────────────────
  const [results, setResults] = useState<DiscoveredCompany[]>([])
  const [meta, setMeta] = useState<SearchMeta | null>(null)
  const [searching, setSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  // ── Pagination ────────────────────────────────────────────────────────────
  const [currentPage, setCurrentPage] = useState(1)
  const totalPages = Math.ceil(results.length / PAGE_SIZE)
  const pageResults = results.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  // ── Saved / saving tracking ───────────────────────────────────────────────
  const [savedNames, setSavedNames] = useState<Set<string>>(new Set())
  const [savingName, setSavingName] = useState<string | null>(null)

  // ── Handlers ──────────────────────────────────────────────────────────────

  function toggleStage(stage: string) {
    setSelectedStages(prev =>
      prev.includes(stage) ? prev.filter(s => s !== stage) : [...prev, stage]
    )
  }

  function goToPage(page: number) {
    setCurrentPage(page)
    window.scrollTo({ top: 0, behavior: 'smooth' })
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
    setMeta(null)
    setCurrentPage(1)

    const res = await apiFetch('/api/startup-scout/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        location: location.trim(),
        funding_stages: selectedStages,
        industry: industry.trim(),
        size_range: sizeRange,
        limit: parseInt(limit, 10),
      }),
    })

    if (res.ok) {
      const data = await res.json()
      setResults(data.companies || [])
      setMeta(data.meta || null)
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
      setSavedNames(prev => new Set([...prev, company.name]))
      toast({ title: 'Saved to tracker', description: `${company.name} added. Go to Tracker → Startup Scout to crawl contacts.` })
    } else {
      const err = await res.json().catch(() => ({}))
      toast({ title: 'Could not save', description: err.detail || 'Something went wrong.', variant: 'destructive' })
    }
    setSavingName(null)
  }

  function downloadCSV() {
    if (!results.length) return
    const rows = results.map(c => ({
      Name: c.name,
      Description: c.description,
      'Funding Stage': c.funding_stage,
      Location: c.location,
      'Size Range': c.size_range,
      Website: c.website,
      Source: c.source,
    }))
    const csv = Papa.unparse(rows)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = Object.assign(document.createElement('a'), {
      href: url,
      download: `startups-${location.trim().toLowerCase().replace(/\s+/g, '-')}-${new Date().toISOString().slice(0, 10)}.csv`,
    })
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast({ title: 'Downloaded', description: `${results.length} startups exported as CSV (opens in Excel)` })
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="animate-fade-in">

      {/* ── Page header ───────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="page-header-icon bg-cyan-100">
            <Radar className="h-5 w-5 text-cyan-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Startup Scout</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Discover startups by location &amp; stage, then crawl for founder contacts
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {results.length > 0 && (
            <Button
              variant="outline"
              onClick={downloadCSV}
              className="h-9 px-3.5 rounded-xl text-sm border-slate-200 text-slate-600 hover:text-slate-900 hover:border-slate-300 gap-1.5"
            >
              <Download className="h-3.5 w-3.5" />
              Export CSV
              <span className="text-slate-400 text-xs">({results.length})</span>
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() => router.push('/tracker')}
            className="h-9 px-3.5 rounded-xl text-sm border-slate-200 text-slate-600 hover:text-slate-900 gap-1.5"
          >
            <Building2 className="h-3.5 w-3.5" />
            View Tracker
          </Button>
        </div>
      </div>

      {/* ── Main grid ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-[300px_1fr] gap-5 items-start">

        {/* ── Filter panel ──────────────────────────────────────────────── */}
        <aside className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-5 sticky top-6">

          <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
            <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Filters</span>
          </div>

          {/* Location */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">
              Location <span className="text-rose-400">*</span>
            </Label>
            <Input
              placeholder="e.g. Berlin, London, Remote"
              value={location}
              onChange={e => setLocation(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
            />
          </div>

          {/* Funding stages */}
          <div className="space-y-2">
            <Label className="text-xs font-medium text-slate-600">
              Funding stage <span className="text-rose-400">*</span>
            </Label>
            <div className="flex flex-wrap gap-1.5">
              {FUNDING_STAGES.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => toggleStage(value)}
                  className={cn(
                    'px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-all',
                    selectedStages.includes(value)
                      ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                      : 'bg-white text-slate-500 border-slate-200 hover:border-indigo-300 hover:text-indigo-600',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Industry */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Industry</Label>
            <Input
              placeholder="e.g. AI, FinTech, SaaS, Climate"
              value={industry}
              onChange={e => setIndustry(e.target.value)}
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
            />
          </div>

          {/* Company size */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Company size</Label>
            <Select value={sizeRange || 'any'} onValueChange={v => setSizeRange(v === 'any' ? '' : v)}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200">
                <SelectValue placeholder="Any size" />
              </SelectTrigger>
              <SelectContent>
                {SIZE_RANGES.map(({ value, label }) => (
                  <SelectItem key={value || 'any'} value={value || 'any'} className="text-sm">
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Result limit */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Result limit</Label>
            <Select value={limit} onValueChange={setLimit}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RESULT_LIMITS.map(({ value, label }) => (
                  <SelectItem key={value} value={value} className="text-sm">{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Higher limits run more queries, allow up to 90 s for 200.
            </p>
          </div>

          {/* Search button */}
          <Button
            onClick={handleSearch}
            disabled={searching}
            className="w-full gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl h-9 text-sm font-semibold"
          >
            {searching
              ? <><Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />Searching…</>
              : <><Search className="h-3.5 w-3.5 mr-2" />Discover Startups</>
            }
          </Button>

          {hasSearched && !searching && (
            <p className="text-[11px] text-slate-400 text-center tabular-nums">
              {results.length} of {limit} results found
            </p>
          )}
        </aside>

        {/* ── Results column ────────────────────────────────────────────── */}
        <div className="min-w-0 space-y-3">

          {/* Empty / initial state */}
          {!hasSearched && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm flex flex-col items-center justify-center py-20 px-6 text-center">
              <div className="w-14 h-14 rounded-2xl bg-cyan-50 flex items-center justify-center mb-4">
                <Radar className="h-7 w-7 text-cyan-300" />
              </div>
              <p className="font-semibold text-slate-700 text-base">Find your next startup</p>
              <p className="text-sm text-slate-400 mt-1 max-w-xs leading-relaxed">
                Set a location and funding stage, then hit Discover. <span className="text-blue-500">Save interesting companies to your tracker to crawl for founder contacts.</span>
              </p>
            </div>
          )}

          {/* Skeleton loading */}
          {searching && (
            <>
              <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4 flex items-center gap-3">
                <Loader2 className="h-4 w-4 animate-spin text-cyan-400 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-slate-600">Scanning startup directories…</p>
                  <p className="text-xs text-slate-400 mt-0.5">Running {limit === '200' ? '14+' : limit === '100' ? '10+' : '6'} queries across Crunchbase, Wellfound, Dealroom &amp; more</p>
                </div>
              </div>
              {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
            </>
          )}

          {/* No results */}
          {!searching && hasSearched && results.length === 0 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm flex flex-col items-center justify-center py-20 text-center">
              <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-4">
                <Search className="h-5 w-5 text-slate-300" />
              </div>
              <p className="font-semibold text-slate-600">No startups found</p>
              <p className="text-sm text-slate-400 mt-1">
                Try a broader location, different stage, or remove the industry filter.
              </p>
            </div>
          )}

          {/* Results */}
          {!searching && results.length > 0 && (
            <>
              {/* ── Citation card ──────────────────────────────────────── */}
              {meta && (
                <div className="bg-gradient-to-r from-slate-50 to-white rounded-2xl border border-slate-200 p-4">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Database className="h-4 w-4 text-indigo-500" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center flex-wrap gap-x-3 gap-y-1">
                        <span className="text-sm font-semibold text-slate-800">
                          {meta.total} startup{meta.total !== 1 ? 's' : ''} found
                        </span>
                        <span className="text-xs text-slate-400">
                          {meta.queries_run} quer{meta.queries_run !== 1 ? 'ies' : 'y'} · {Object.keys(meta.sources).length} source{Object.keys(meta.sources).length !== 1 ? 's' : ''}
                        </span>
                        <span className="text-xs text-slate-400">limit: {meta.limit}</span>
                      </div>

                      {/* Source chips */}
                      <div className="flex flex-wrap gap-1.5 mt-2.5">
                        {Object.entries(meta.sources)
                          .sort(([, a], [, b]) => b - a)
                          .map(([src, count]) => (
                            <span
                              key={src}
                              className={cn(
                                'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ring-1',
                                SOURCE_PILL[src] || 'bg-slate-50 text-slate-600 ring-slate-200',
                              )}
                            >
                              <span className={cn('w-1.5 h-1.5 rounded-full', SOURCE_DOT[src] || 'bg-slate-400')} />
                              {src} <span className="opacity-60">({count})</span>
                            </span>
                          ))}
                      </div>

                      {/* Search params */}
                      <p className="text-[11px] text-slate-400 mt-2">
                        Searched:&nbsp;
                        <span className="text-slate-500 font-medium">{meta.location}</span>
                        {meta.industry && <>&nbsp;·&nbsp;<span className="text-slate-500 font-medium">{meta.industry}</span></>}
                        {meta.funding_stages.length > 0 && (
                          <>&nbsp;·&nbsp;<span className="text-slate-500 font-medium">{meta.funding_stages.join(', ')}</span></>
                        )}
                      </p>
                    </div>

                    <button
                      onClick={downloadCSV}
                      className="flex-shrink-0 h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-medium text-slate-500 hover:text-slate-800 hover:border-slate-300 transition-colors flex items-center gap-1"
                    >
                      <Download className="h-3 w-3" />
                      Export
                    </button>
                  </div>
                </div>
              )}

              {/* ── Result count + top pagination ──────────────────────── */}
              <div className="flex items-center justify-between px-0.5">
                <p className="text-xs text-slate-500">
                  Showing <span className="font-semibold text-slate-700">
                    {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, results.length)}
                  </span> of <span className="font-semibold text-slate-700">{results.length}</span>
                </p>
                {totalPages > 1 && (
                  <Pagination current={currentPage} total={totalPages} onChange={goToPage} />
                )}
              </div>

              {/* ── Company cards ──────────────────────────────────────── */}
              {pageResults.map((company, i) => {
                const saved = savedNames.has(company.name)
                const saving = savingName === company.name
                const stagePill = STAGE_PILL[company.funding_stage] || ''

                return (
                  <article
                    key={`${company.website}-${i}`}
                    className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-start gap-4 hover:border-slate-200 hover:shadow-md transition-all duration-150"
                  >
                    {/* Avatar */}
                    <div className="w-10 h-10 rounded-xl bg-cyan-50 border border-cyan-100 flex items-center justify-center flex-shrink-0">
                      <Building2 className="h-5 w-5 text-cyan-500" />
                    </div>

                    {/* Body */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          {/* Name + index */}
                          <div className="flex items-baseline gap-2">
                            <p className="font-semibold text-slate-900 text-sm leading-snug truncate">
                              {company.name}
                            </p>
                            <span className="text-[10px] text-slate-300 tabular-nums flex-shrink-0">
                              #{(currentPage - 1) * PAGE_SIZE + i + 1}
                            </span>
                          </div>

                          {/* Meta row */}
                          <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                            {company.location && (
                              <span className="flex items-center gap-0.5 text-[11px] text-slate-400">
                                <MapPin className="h-2.5 w-2.5" />
                                {company.location}
                              </span>
                            )}
                            {company.funding_stage && stagePill && (
                              <span className={cn(
                                'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ring-1',
                                stagePill,
                              )}>
                                <TrendingUp className="h-2.5 w-2.5" />
                                {company.funding_stage}
                              </span>
                            )}
                            {company.size_range && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-50 text-slate-500 ring-1 ring-slate-200">
                                {company.size_range} people
                              </span>
                            )}
                            {/* Source */}
                            <span className={cn(
                              'px-2 py-0.5 rounded-full text-[10px] font-medium ring-1',
                              SOURCE_PILL[company.source] || 'bg-slate-50 text-slate-500 ring-slate-200',
                            )}>
                              {company.source}
                            </span>
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {company.website && (
                            <Link
                              href={company.website}
                              target="_blank"
                              className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-300 hover:text-slate-600 hover:bg-slate-50 border border-transparent hover:border-slate-200 transition-all"
                              title="Open profile"
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
                              'h-8 px-3 rounded-xl text-[11px] font-semibold',
                              saved
                                ? 'border-emerald-200 text-emerald-600 bg-emerald-50 hover:bg-emerald-50'
                                : 'gradient-brand text-white border-0 hover:opacity-90 shadow-sm',
                            )}
                          >
                            {saving ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : saved ? (
                              <><CheckCircle className="h-3 w-3 mr-1" />Saved</>
                            ) : (
                              <><BookmarkPlus className="h-3 w-3 mr-1" />Save</>
                            )}
                          </Button>
                        </div>
                      </div>

                      {/* Description */}
                      {company.description && (
                        <p className="text-[12px] text-slate-500 mt-2 leading-relaxed line-clamp-2">
                          {company.description}
                        </p>
                      )}
                    </div>
                  </article>
                )
              })}

              {/* ── Bottom pagination ──────────────────────────────────── */}
              {totalPages > 1 && (
                <div className="flex justify-center pt-1">
                  <Pagination current={currentPage} total={totalPages} onChange={goToPage} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Pagination component ──────────────────────────────────────────────────────

function Pagination({
  current, total, onChange,
}: { current: number; total: number; onChange: (p: number) => void }) {
  const pages = pageRange(current, total)
  return (
    <nav className="flex items-center gap-1" aria-label="Pagination">
      <button
        onClick={() => onChange(current - 1)}
        disabled={current === 1}
        className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      {pages.map((p, idx) =>
        p === '…' ? (
          <span key={`ellipsis-${idx}`} className="h-8 w-8 flex items-center justify-center text-slate-400 text-xs">
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onChange(p)}
            className={cn(
              'h-8 w-8 rounded-lg flex items-center justify-center text-xs font-semibold transition-colors',
              p === current
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800',
            )}
            aria-current={p === current ? 'page' : undefined}
          >
            {p}
          </button>
        )
      )}

      <button
        onClick={() => onChange(current + 1)}
        disabled={current === total}
        className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </nav>
  )
}
