'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Pencil, Sparkles, FolderOpen, FileText, PenLine, Briefcase } from 'lucide-react'
import { Button, useToast, cn, formatDate } from '@jobnok/ui'
import { ScaledResumeThumb } from '@/components/shared/ScaledResumeThumb'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { CoverLetterSessionSummary, SessionSummary } from '@/lib/types'

// A generic row shape the grid renders from, kept separate from
// SessionSummary/CoverLetterSessionSummary's own fields. sourceOpportunityId/
// sourceApplicationId power the grouping below - two rows (one of each kind)
// sharing either id get bundled into a JobGroupCard instead of appearing as
// two unrelated cards.
interface DocRow {
  id: string
  kind: 'resume' | 'cover_letter'
  label: string
  isAiMatched: boolean
  meta: string
  matchScore: number | null
  createdAt: string
  isDraft: boolean
  previewHtml: string | null
  openHref: string
  sourceOpportunityId: string | null
  sourceApplicationId: string | null
}

function toResumeDocRow(s: SessionSummary): DocRow {
  return {
    id: s.id,
    kind: 'resume',
    label: s.display_label,
    isAiMatched: s.is_ai_matched,
    meta: s.template_id ? s.template_id.replace(/_/g, ' ') : 'Resume',
    matchScore: s.match_score,
    createdAt: s.created_at,
    isDraft: s.is_draft,
    previewHtml: s.preview_html,
    openHref: `/resume-tailor/editor?session_id=${s.id}`,
    sourceOpportunityId: s.source_opportunity_id,
    sourceApplicationId: s.source_application_id,
  }
}

function toCoverLetterDocRow(s: CoverLetterSessionSummary): DocRow {
  return {
    id: s.id,
    kind: 'cover_letter',
    label: s.display_label,
    isAiMatched: false,
    meta: 'Cover Letter',
    matchScore: null,
    createdAt: s.created_at,
    isDraft: false,
    previewHtml: null,
    openHref: `/cover-letter?session_id=${s.id}`,
    sourceOpportunityId: s.source_opportunity_id,
    sourceApplicationId: s.source_application_id,
  }
}

function groupKeyFor(row: DocRow): string | null {
  if (row.sourceOpportunityId) return `opp:${row.sourceOpportunityId}`
  if (row.sourceApplicationId) return `app:${row.sourceApplicationId}`
  return null
}

const PREVIEW_PEEK_HEIGHT = 160

function scoreColor(score: number): string {
  if (score >= 70) return 'text-emerald-600 bg-emerald-50 border-emerald-100'
  if (score >= 40) return 'text-amber-600 bg-amber-50 border-amber-100'
  return 'text-red-600 bg-red-50 border-red-100'
}

function DocCard({ row, onRename }: { row: DocRow; onRename: (row: DocRow, newLabel: string) => void }) {
  const router = useRouter()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(row.label)

  function save(value: string) {
    setEditing(false)
    const trimmed = value.trim()
    if (trimmed && trimmed !== row.label) onRename(row, trimmed)
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200/70 overflow-hidden transition-colors duration-150 hover:border-slate-300">
      <button
        onClick={() => router.push(row.openHref)}
        className="w-full text-left block"
        title={row.kind === 'resume' ? 'Open in editor' : 'Open in Cover Letter Generator'}
      >
        {row.previewHtml ? (
          <ScaledResumeThumb
            html={row.previewHtml}
            label={row.label}
            cropHeight={PREVIEW_PEEK_HEIGHT}
            className="border-b border-slate-100 bg-slate-50"
          />
        ) : row.kind === 'resume' ? (
          <div
            className="w-full border-b border-slate-100 bg-slate-50 flex flex-col items-center justify-center gap-1"
            style={{ height: PREVIEW_PEEK_HEIGHT }}
          >
            <FileText className="h-5 w-5 text-slate-300" />
            <span className="text-[11px] text-slate-400">Open to generate a preview</span>
          </div>
        ) : (
          <div
            className="w-full border-b border-slate-100 bg-slate-50 flex flex-col items-center justify-center gap-1"
            style={{ height: PREVIEW_PEEK_HEIGHT }}
          >
            <PenLine className="h-5 w-5 text-slate-300" />
            <span className="text-[11px] text-slate-400">Cover letter</span>
          </div>
        )}
      </button>

      <div className="p-3 space-y-1.5">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onFocus={e => e.currentTarget.select()}
            onBlur={e => save(e.currentTarget.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') e.currentTarget.blur()
              if (e.key === 'Escape') setEditing(false)
            }}
            maxLength={200}
            className="text-sm font-semibold text-slate-900 bg-white border border-indigo-300 rounded px-1.5 py-0.5 outline-none ring-2 ring-indigo-100 w-full"
          />
        ) : (
          <button
            onClick={() => { setDraft(row.label); setEditing(true) }}
            className="group/rename flex items-center gap-1.5 min-w-0 text-left w-full"
          >
            <span className="text-sm font-semibold text-slate-900 truncate">{row.label}</span>
            {row.isAiMatched && (
              <span title="AI-detected from the job description — may not be exact" className="shrink-0">
                <Sparkles className="h-3 w-3 text-indigo-400" />
              </span>
            )}
            <Pencil className="h-3 w-3 text-slate-300 group-hover/rename:text-slate-500 shrink-0 ml-auto" />
          </button>
        )}

        <p className="text-xs text-slate-400 capitalize truncate">{row.meta}</p>

        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
          {row.matchScore !== null && (
            <span className={cn('inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold border', scoreColor(row.matchScore))}>
              {row.matchScore}%
            </span>
          )}
          <span className={cn(
            'inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium',
            row.isDraft ? 'bg-amber-50 text-amber-700 border border-amber-100' : 'bg-slate-50 text-slate-500 border border-slate-200'
          )}>
            {row.isDraft ? 'Draft' : 'Generated'}
          </span>
          <span className="text-[10px] text-slate-400 ml-auto shrink-0">{formatDate(row.createdAt)}</span>
        </div>
      </div>
    </div>
  )
}

// Two or more docs (a resume and/or cover letter) saved for the same tracked
// job - wrapped together so they read as "one application's documents"
// instead of two unrelated cards scattered across the grid. Every other row
// (no shared linkage, or an unmatched single row) renders as a plain
// standalone DocCard, unchanged from before this feature existed.
function JobGroupCard({ rows, onRename }: { rows: DocRow[]; onRename: (row: DocRow, newLabel: string) => void }) {
  const headerLabel = rows.find(r => r.kind === 'resume')?.label ?? rows[0].label
  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-2 space-y-2">
      <div className="flex items-center gap-1.5 px-1 pt-0.5">
        <Briefcase className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
        <span className="text-xs font-semibold text-indigo-700 truncate">{headerLabel}</span>
      </div>
      <div className="space-y-2">
        {rows.map(row => <DocCard key={row.id} row={row} onRename={onRename} />)}
      </div>
    </div>
  )
}

type GridItem = { type: 'single'; row: DocRow } | { type: 'group'; rows: DocRow[] }

function buildGridItems(allRows: DocRow[]): GridItem[] {
  const buckets = new Map<string, DocRow[]>()
  for (const row of allRows) {
    const key = groupKeyFor(row)
    if (!key) continue
    const bucket = buckets.get(key) ?? []
    bucket.push(row)
    buckets.set(key, bucket)
  }

  const groupedIds = new Set<string>()
  const items: GridItem[] = []
  for (const bucket of buckets.values()) {
    if (bucket.length < 2) continue
    bucket.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    bucket.forEach(r => groupedIds.add(r.id))
    items.push({ type: 'group', rows: bucket })
  }
  for (const row of allRows) {
    if (!groupedIds.has(row.id)) items.push({ type: 'single', row })
  }

  const timestampOf = (item: GridItem) =>
    item.type === 'single'
      ? new Date(item.row.createdAt).getTime()
      : Math.max(...item.rows.map(r => new Date(r.createdAt).getTime()))
  items.sort((a, b) => timestampOf(b) - timestampOf(a))
  return items
}

export default function MyDocsPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const resumeQuery = useQuery({
    queryKey: queryKeys.tailoringSessions,
    queryFn: () => apiGet<{ sessions: SessionSummary[] }>('/api/ai/tailor/sessions'),
  })
  const coverLetterQuery = useQuery({
    queryKey: queryKeys.coverLetterSessions,
    queryFn: () => apiGet<{ sessions: CoverLetterSessionSummary[] }>('/api/ai/cover-letter/sessions'),
  })

  const isLoading = resumeQuery.isLoading || coverLetterQuery.isLoading
  const isError = resumeQuery.isError || coverLetterQuery.isError

  const allRows = [
    ...(resumeQuery.data?.sessions ?? []).map(toResumeDocRow),
    ...(coverLetterQuery.data?.sessions ?? []).map(toCoverLetterDocRow),
  ]
  const gridItems = buildGridItems(allRows)

  async function handleRename(row: DocRow, newTitle: string) {
    const isResume = row.kind === 'resume'
    const endpoint = isResume ? `/api/ai/tailor/${row.id}/title` : `/api/ai/cover-letter/sessions/${row.id}/title`
    try {
      const res = await apiFetch(endpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      })
      if (!res.ok) throw new Error()
      if (isResume) {
        queryClient.setQueryData<{ sessions: SessionSummary[] } | undefined>(queryKeys.tailoringSessions, (prev) => {
          if (!prev) return prev
          return {
            sessions: prev.sessions.map(s => s.id === row.id ? { ...s, title: newTitle, display_label: newTitle, is_ai_matched: false } : s),
          }
        })
      } else {
        queryClient.setQueryData<{ sessions: CoverLetterSessionSummary[] } | undefined>(queryKeys.coverLetterSessions, (prev) => {
          if (!prev) return prev
          return {
            sessions: prev.sessions.map(s => s.id === row.id ? { ...s, title: newTitle, display_label: newTitle } : s),
          }
        })
      }
    } catch {
      toast({ title: 'Could not rename', variant: 'destructive' })
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="flex items-center gap-4 mb-6">
        <div className="hidden sm:flex page-header-icon bg-indigo-100">
          <FolderOpen className="h-5 w-5 text-indigo-600" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">My Docs</h1>
            {!isLoading && allRows.length > 0 && (
              <span className="text-xs font-semibold bg-slate-100 text-slate-600 rounded-full px-2.5 py-1 shrink-0">
                {allRows.length} {allRows.length === 1 ? 'document' : 'documents'}
              </span>
            )}
          </div>
          <p className="text-slate-500 text-sm mt-0.5">Every resume and cover letter you&apos;ve saved, most recent first</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center h-56 bg-white rounded-2xl border border-slate-100 shadow-sm">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
          <p className="text-sm text-slate-400 mt-3">Loading your documents…</p>
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center justify-center h-56 bg-white rounded-2xl border border-slate-100 shadow-sm">
          <p className="font-medium text-slate-600">Could not load your documents</p>
          <p className="text-sm text-slate-400 mt-1">Please refresh the page to try again</p>
        </div>
      ) : allRows.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-56 bg-white rounded-2xl border border-slate-100 shadow-sm px-4 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
            <FolderOpen className="h-7 w-7 text-slate-300" />
          </div>
          <p className="font-medium text-slate-600">No documents yet</p>
          <p className="text-sm text-slate-400 mt-1">Tailor a resume or save a cover letter to see it show up here</p>
          <Button
            onClick={() => router.push('/resume-tailor')}
            className="mt-4 gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl h-9 text-sm px-5"
          >
            Go to Resume Tailor
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {gridItems.map((item) => item.type === 'single'
            ? <DocCard key={item.row.id} row={item.row} onRename={handleRename} />
            : <JobGroupCard key={item.rows.map(r => r.id).join(',')} rows={item.rows} onRename={handleRename} />
          )}
        </div>
      )}
    </div>
  )
}
