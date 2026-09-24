'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Pencil, Sparkles, FolderOpen, FileText } from 'lucide-react'
import { Button, useToast, cn, formatDate } from '@jobnok/ui'
import { ScaledResumeThumb } from '@/components/shared/ScaledResumeThumb'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { SessionSummary } from '@/lib/types'

// A generic row shape the grid renders from, kept separate from
// SessionSummary's resume-specific fields - once cover letters get their own
// persistence, mapping a second source into this same shape (kind:
// 'cover_letter') is additive, not a rewrite of this page's markup.
interface DocRow {
  id: string
  kind: 'resume'
  label: string
  isAiMatched: boolean
  meta: string
  matchScore: number | null
  createdAt: string
  isDraft: boolean
  previewHtml: string | null
  openHref: string
}

function toDocRow(s: SessionSummary): DocRow {
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
  }
}

const PREVIEW_PEEK_HEIGHT = 160

function scoreColor(score: number): string {
  if (score >= 70) return 'text-emerald-600 bg-emerald-50 border-emerald-100'
  if (score >= 40) return 'text-amber-600 bg-amber-50 border-amber-100'
  return 'text-red-600 bg-red-50 border-red-100'
}

function DocCard({ row, onRename }: { row: DocRow; onRename: (id: string, newLabel: string) => void }) {
  const router = useRouter()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(row.label)

  function save(value: string) {
    setEditing(false)
    const trimmed = value.trim()
    if (trimmed && trimmed !== row.label) onRename(row.id, trimmed)
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200/70 overflow-hidden transition-colors duration-150 hover:border-slate-300">
      <button
        onClick={() => router.push(row.openHref)}
        className="w-full text-left block"
        title="Open in editor"
      >
        {row.previewHtml ? (
          <ScaledResumeThumb
            html={row.previewHtml}
            label={row.label}
            cropHeight={PREVIEW_PEEK_HEIGHT}
            className="border-b border-slate-100 bg-slate-50"
          />
        ) : (
          <div
            className="w-full border-b border-slate-100 bg-slate-50 flex flex-col items-center justify-center gap-1"
            style={{ height: PREVIEW_PEEK_HEIGHT }}
          >
            <FileText className="h-5 w-5 text-slate-300" />
            <span className="text-[11px] text-slate-400">Open to generate a preview</span>
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

export default function MyDocsPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.tailoringSessions,
    queryFn: () => apiGet<{ sessions: SessionSummary[] }>('/api/ai/tailor/sessions'),
  })
  const rows = (data?.sessions ?? []).map(toDocRow)

  async function handleRename(id: string, newTitle: string) {
    try {
      const res = await apiFetch(`/api/ai/tailor/${id}/title`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      })
      if (!res.ok) throw new Error()
      queryClient.setQueryData<{ sessions: SessionSummary[] } | undefined>(queryKeys.tailoringSessions, (prev) => {
        if (!prev) return prev
        return {
          sessions: prev.sessions.map(s => s.id === id ? { ...s, title: newTitle, display_label: newTitle, is_ai_matched: false } : s),
        }
      })
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
            {!isLoading && rows.length > 0 && (
              <span className="text-xs font-semibold bg-slate-100 text-slate-600 rounded-full px-2.5 py-1 shrink-0">
                {rows.length} {rows.length === 1 ? 'document' : 'documents'}
              </span>
            )}
          </div>
          <p className="text-slate-500 text-sm mt-0.5">Every resume you&apos;ve generated, most recent first</p>
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
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-56 bg-white rounded-2xl border border-slate-100 shadow-sm px-4 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
            <FolderOpen className="h-7 w-7 text-slate-300" />
          </div>
          <p className="font-medium text-slate-600">No documents yet</p>
          <p className="text-sm text-slate-400 mt-1">Tailor a resume to see it show up here</p>
          <Button
            onClick={() => router.push('/resume-tailor')}
            className="mt-4 gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl h-9 text-sm px-5"
          >
            Go to Resume Tailor
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {rows.map((row) => (
            <DocCard key={row.id} row={row} onRename={handleRename} />
          ))}
        </div>
      )}
    </div>
  )
}
