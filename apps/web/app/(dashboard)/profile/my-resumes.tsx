'use client'

import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Loader2, Pencil, Trash2, Upload, X } from 'lucide-react'
import { Button, Input, useToast } from '@jobnok/ui'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { SavedResume } from '@/lib/types'

const SLOTS = [1, 2, 3] as const
const MAX_PDF_BYTES = 5 * 1024 * 1024

function defaultLabel(filename: string): string {
  return filename.replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ').trim() || 'Resume'
}

function SlotTile({ slot, resume }: { slot: 1 | 2 | 3; resume: SavedResume | undefined }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [editingLabel, setEditingLabel] = useState(false)
  const [labelDraft, setLabelDraft] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  function updateCache(updated: SavedResume | null) {
    queryClient.setQueryData<{ resumes: SavedResume[] } | undefined>(queryKeys.savedResumes, (prev) => {
      const rest = (prev?.resumes ?? []).filter(r => r.slot !== slot)
      return { resumes: updated ? [...rest, updated] : rest }
    })
  }

  async function upload(file: File, label: string) {
    if (file.type !== 'application/pdf') {
      toast({ title: 'PDF only', description: 'Please upload a PDF file.', variant: 'destructive' })
      return
    }
    if (file.size > MAX_PDF_BYTES) {
      toast({ title: 'Too large', description: 'PDF must be under 5 MB.', variant: 'destructive' })
      return
    }
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    form.append('label', label)
    try {
      const res = await apiFetch(`/api/ai/resumes/${slot}`, { method: 'PUT', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      updateCache(data)
      toast({ title: resume ? 'Resume replaced' : 'Resume saved' })
    } catch (err) {
      toast({ title: 'Upload failed', description: err instanceof Error ? err.message : undefined, variant: 'destructive' })
    } finally {
      setUploading(false)
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    upload(file, resume?.label || defaultLabel(file.name))
  }

  async function saveLabel() {
    const trimmed = labelDraft.trim()
    setEditingLabel(false)
    if (!resume || !trimmed || trimmed === resume.label) return
    try {
      const res = await apiFetch(`/api/ai/resumes/${slot}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: trimmed }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Rename failed')
      updateCache(data)
    } catch (err) {
      toast({ title: 'Rename failed', description: err instanceof Error ? err.message : undefined, variant: 'destructive' })
    }
  }

  async function handleDelete() {
    if (!resume) return
    try {
      const res = await apiFetch(`/api/ai/resumes/${slot}`, { method: 'DELETE' })
      if (!res.ok) throw new Error()
      updateCache(null)
      toast({ title: 'Resume removed' })
    } catch {
      toast({ title: 'Delete failed', variant: 'destructive' })
    } finally {
      setConfirmingDelete(false)
    }
  }

  return (
    <div className="border border-slate-200/70 rounded-xl p-4 bg-slate-50/60 min-h-[132px] flex flex-col">
      <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />

      {!resume ? (
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400 hover:text-indigo-500 transition-colors"
        >
          {uploading
            ? <Loader2 className="h-5 w-5 animate-spin" />
            : <Upload className="h-5 w-5" />
          }
          <span className="text-xs font-medium">{uploading ? 'Uploading…' : `Upload resume ${slot}`}</span>
        </button>
      ) : (
        <div className="flex-1 flex flex-col">
          <div className="flex items-start gap-2 mb-2">
            <FileText className="h-4 w-4 text-indigo-400 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              {editingLabel ? (
                <input
                  autoFocus
                  value={labelDraft}
                  onChange={e => setLabelDraft(e.target.value)}
                  onFocus={e => e.currentTarget.select()}
                  onBlur={saveLabel}
                  onKeyDown={e => {
                    if (e.key === 'Enter') e.currentTarget.blur()
                    if (e.key === 'Escape') setEditingLabel(false)
                  }}
                  maxLength={100}
                  className="text-sm font-semibold text-slate-900 bg-white border border-indigo-300 rounded px-1 -mx-1 outline-none ring-2 ring-indigo-100 w-full"
                />
              ) : (
                <button
                  onClick={() => { setLabelDraft(resume.label); setEditingLabel(true) }}
                  className="group flex items-center gap-1 min-w-0 text-left"
                >
                  <span className="text-sm font-semibold text-slate-900 truncate">{resume.label}</span>
                  <Pencil className="h-3 w-3 text-slate-300 group-hover:text-slate-500 shrink-0" />
                </button>
              )}
              <p className="text-[11px] text-slate-400 truncate mt-0.5">{resume.original_filename}</p>
            </div>
          </div>

          <div className="mt-auto flex items-center gap-1.5 pt-2">
            {confirmingDelete ? (
              <>
                <span className="text-[11px] text-slate-500 mr-1">Delete this resume?</span>
                <Button size="sm" variant="destructive" className="h-7 text-xs px-2 rounded-lg" onClick={handleDelete}>
                  Delete
                </Button>
                <button onClick={() => setConfirmingDelete(false)} className="text-slate-400 hover:text-slate-600">
                  <X className="h-3.5 w-3.5" />
                </button>
              </>
            ) : (
              <>
                <Button
                  size="sm" variant="outline" disabled={uploading}
                  className="h-7 text-xs px-2 rounded-lg"
                  onClick={() => fileRef.current?.click()}
                >
                  {uploading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : null}
                  Replace
                </Button>
                <button
                  onClick={() => setConfirmingDelete(true)}
                  className="h-7 w-7 flex items-center justify-center rounded-lg text-slate-300 hover:text-red-400 transition-colors"
                  aria-label="Delete resume"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function MyResumes() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.savedResumes,
    queryFn: () => apiGet<{ resumes: SavedResume[] }>('/api/ai/resumes'),
  })

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
      <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1">My Resumes</p>
      <p className="text-xs text-slate-400 mb-4">
        Save up to 3 resumes here to pick from instantly in Resume Tailor, instead of re-uploading every time.
      </p>
      {isLoading ? (
        <div className="flex items-center justify-center h-24">
          <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {SLOTS.map(slot => (
            <SlotTile key={slot} slot={slot} resume={data?.resumes.find(r => r.slot === slot)} />
          ))}
        </div>
      )}
    </div>
  )
}
