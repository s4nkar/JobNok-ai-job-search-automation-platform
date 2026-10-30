'use client'

import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { PREBUILT_TEMPLATES } from '@/lib/templates/prebuilt'
import { extractPlaceholders, fillTemplate, cn } from '@jobnok/ui'
import { TEMPLATE_CATEGORIES, type Template, type TemplateCategory } from '@/lib/types'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Textarea } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import { Badge } from '@jobnok/ui'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@jobnok/ui'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@jobnok/ui'
import { useToast } from '@jobnok/ui'
import { Plus, Copy, Check, Trash2, FileText, Loader2, AlertCircle } from 'lucide-react'

const LINKEDIN_CHAR_LIMIT = 300
// Mirrors the backend's Pydantic bounds (apps/api/app/modules/templates/
// schemas.py) — kept in sync by hand, same pattern CLAUDE.md documents for
// every other tool's Zod/Pydantic pair.
const NAME_MAX_LENGTH = 100
const CONTENT_MAX_LENGTH = 5000

const templateSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters').max(NAME_MAX_LENGTH, `Keep it under ${NAME_MAX_LENGTH} characters`),
  category: z.enum(TEMPLATE_CATEGORIES as [TemplateCategory, ...TemplateCategory[]]),
  content: z.string().min(10, 'Template must be at least 10 characters').max(CONTENT_MAX_LENGTH, `Keep it under ${CONTENT_MAX_LENGTH} characters`),
})
type TemplateFormData = z.infer<typeof templateSchema>

// Previously keyed on category names ('LinkedIn', 'Email', 'Follow-up',
// 'Thank You') that don't match any value TEMPLATE_CATEGORIES actually
// contains (apps/web/lib/types.ts) — every real category silently fell
// back to the 'Custom' style below, since none of these keys ever matched.
// The two "cold DM" categories share one recognizable outreach color;
// everything else is a neutral category label with no status meaning.
const categoryColors: Record<string, string> = {
  'Cold DM - Recruiter': 'bg-blue-50 text-blue-700 border-blue-100',
  'Cold DM - Hiring Manager': 'bg-blue-50 text-blue-700 border-blue-100',
  'Follow-Up': 'bg-slate-50 text-slate-600 border-slate-200',
  'Referral Ask': 'bg-slate-50 text-slate-600 border-slate-200',
  'Email Outreach': 'bg-slate-50 text-slate-600 border-slate-200',
  'Custom': 'bg-slate-50 text-slate-600 border-slate-200',
}

function CategoryBadge({ category }: { category: string }) {
  const cls = categoryColors[category] || categoryColors['Custom']
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold border', cls)}>
      {category}
    </span>
  )
}

export default function TemplatesPage() {
  const queryClient = useQueryClient()
  const { data: savedTemplates = [] } = useQuery({
    queryKey: queryKeys.templates,
    queryFn: () => apiGet<Template[]>('/api/templates'),
  })
  const [selected, setSelected] = useState<Template | null>(null)
  const [fillValues, setFillValues] = useState<Record<string, string>>({})
  const [filledContent, setFilledContent] = useState('')
  const [copied, setCopied] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [saving, setSaving] = useState(false)
  const [filterCategory, setFilterCategory] = useState<string>('all')
  const { toast } = useToast()

  const { register, handleSubmit, setValue, reset, watch, formState: { errors } } = useForm<TemplateFormData>({
    resolver: zodResolver(templateSchema),
    defaultValues: { category: 'Custom' },
  })

  const watchContent = watch('content', '')

  function selectTemplate(t: Template) {
    setSelected(t)
    setFillValues({})
    setFilledContent(t.content)
    setCopied(false)
  }

  const updateFill = useCallback((key: string, value: string) => {
    setFillValues((prev) => {
      const next = { ...prev, [key]: value }
      setFilledContent(fillTemplate(selected?.content || '', next))
      return next
    })
  }, [selected])

  async function copyToClipboard() {
    await navigator.clipboard.writeText(filledContent)
    setCopied(true)
    toast({ title: 'Copied!', description: 'Message copied to clipboard.' })
    if (selected && !selected.is_prebuilt) {
      // Atomic server-side increment (POST /{id}/use), not a client-
      // computed "current + 1" PUT - that previously let two rapid
      // copies (or two tabs) both read the same stale count and both
      // write the same incremented value, silently losing one.
      await apiFetch(`/api/templates/${selected.id}/use`, { method: 'POST' })
    }
    setTimeout(() => setCopied(false), 3000)
  }

  async function onSaveTemplate(data: TemplateFormData) {
    setSaving(true)
    const res = await apiFetch('/api/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })

    if (res.ok) {
      const created: Template = await res.json()
      queryClient.setQueryData<Template[]>(queryKeys.templates, (prev) => [created, ...(prev || [])])
      toast({ title: 'Template saved!' })
      reset()
      setShowCreate(false)
    } else {
      const err = await res.json().catch(() => ({}))
      toast({ title: 'Error saving template', description: err.detail, variant: 'destructive' })
    }
    setSaving(false)
  }

  async function deleteTemplate(id: string) {
    const res = await apiFetch(`/api/templates/${id}`, { method: 'DELETE' })
    if (res.ok) {
      queryClient.setQueryData<Template[]>(queryKeys.templates, (prev) => (prev || []).filter((t) => t.id !== id))
      if (selected?.id === id) setSelected(null)
      toast({ title: 'Template deleted' })
    }
  }

  const allTemplates = [...savedTemplates, ...PREBUILT_TEMPLATES]
  const filtered = filterCategory === 'all'
    ? allTemplates
    : allTemplates.filter((t) => t.category === filterCategory)

  const charCount = filledContent.length
  const overLinkedInLimit = charCount > LINKEDIN_CHAR_LIMIT

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex page-header-icon bg-indigo-100">
            <FileText className="h-5 w-5 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Smart Templates</h1>
            <p className="text-slate-500 text-sm mt-0.5">
              Create reusable messages with <code className="bg-slate-100 px-1.5 py-0.5 rounded-md text-xs font-mono text-slate-600">{'{{placeholder}}'}</code> auto-fill
            </p>
          </div>
        </div>
        <Button
          onClick={() => setShowCreate(true)}
          className="gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl h-9 text-sm px-5"
        >
          <Plus className="h-3.5 w-3.5 mr-2" />
          New Template
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-start">
        {/* Template List — locked in place while scrolling the editor/fill
            panel at lg+, same pattern as recent-job-search's filter
            sidebar, so switching templates doesn't need scrolling back up
            first. */}
        <div className="lg:col-span-1 lg:sticky lg:top-6 lg:max-h-[calc(100vh-8.5rem)] lg:flex lg:flex-col space-y-3">
          <Select value={filterCategory} onValueChange={setFilterCategory}>
            <SelectTrigger className="h-9 text-sm rounded-xl border-slate-200">
              <SelectValue placeholder="All categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {TEMPLATE_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>

          <div className="space-y-1.5 max-h-64 lg:max-h-none lg:flex-1 lg:min-h-0 overflow-y-auto pr-1 scrollbar-thin">
            {filtered.length === 0 && (
              <div className="text-center py-10 text-slate-400 text-sm">
                <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                  <FileText className="h-5 w-5 text-slate-300" />
                </div>
                No templates found
              </div>
            )}
            {filtered.map((t) => (
              <button
                key={t.id}
                onClick={() => selectTemplate(t)}
                className={cn(
                  'w-full text-left p-3.5 rounded-xl border text-sm transition-all duration-150',
                  selected?.id === t.id
                    ? 'bg-indigo-50 border-indigo-200 shadow-sm'
                    : 'bg-white border-slate-100 hover:border-slate-200 hover:shadow-sm shadow-sm'
                )}
              >
                <div className={cn('font-semibold truncate text-[13px]', selected?.id === t.id ? 'text-indigo-900' : 'text-slate-800')}>
                  {t.name}
                </div>
                <div className="mt-1.5 flex items-center gap-1.5">
                  <CategoryBadge category={t.category} />
                  {t.is_prebuilt && <span className="text-[10px] text-slate-400">· Pre-built</span>}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Template Editor / Fill */}
        <div className="lg:col-span-2 min-w-0">
          {!selected ? (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm min-h-[18rem] flex items-center justify-center p-6">
              <div className="text-center space-y-1">
                <p className="font-semibold text-slate-500">Select a template to get started</p>
                <p className="text-sm text-slate-400">Or create a new one with the button above</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Template header */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-sm px-5 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
                    <FileText className="h-4 w-4 text-indigo-500" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-bold text-slate-800 text-[15px] truncate">{selected.name}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <CategoryBadge category={selected.category} />
                      {selected.is_prebuilt && <span className="text-[10px] text-slate-400">Pre-built</span>}
                    </div>
                  </div>
                </div>
                {!selected.is_prebuilt && (
                  <button
                    onClick={() => deleteTemplate(selected.id)}
                    className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors flex-shrink-0"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>

              {/* Placeholder Inputs */}
              {selected.placeholders.length > 0 && (
                <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">Fill in placeholders</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {selected.placeholders.map((ph) => (
                      <div key={ph} className="space-y-1.5">
                        <Label className="text-xs font-medium text-slate-600">{ph.replace(/_/g, ' ')}</Label>
                        <Input
                          placeholder={`Enter ${ph.replace(/_/g, ' ')}`}
                          value={fillValues[ph] || ''}
                          onChange={(e) => updateFill(ph, e.target.value)}
                          className="h-8 text-sm rounded-xl border-slate-200"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Filled Output */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest">Output</p>
                  <div className="flex items-center gap-3">
                    {overLinkedInLimit && (
                      <span className="flex items-center gap-1 text-xs text-amber-600 font-medium">
                        <AlertCircle className="h-3 w-3" />
                        Over LinkedIn limit ({charCount}/{LINKEDIN_CHAR_LIMIT})
                      </span>
                    )}
                    {!overLinkedInLimit && charCount > 0 && (
                      <span className="text-xs text-slate-400">{charCount} chars</span>
                    )}
                    <Button
                      size="sm"
                      onClick={copyToClipboard}
                      disabled={charCount === 0}
                      className={cn(
                        'rounded-xl h-8 px-3 text-xs font-semibold transition-all',
                        copied
                          ? 'bg-emerald-500 text-white hover:bg-emerald-600'
                          : 'gradient-brand text-white border-0 hover:opacity-90'
                      )}
                    >
                      {copied ? <Check className="h-3.5 w-3.5 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
                      {copied ? 'Copied!' : 'Copy'}
                    </Button>
                  </div>
                </div>
                <pre className="whitespace-pre-wrap text-sm text-slate-700 bg-slate-50 rounded-xl p-4 min-h-[200px] font-sans leading-relaxed border border-slate-100">
                  {filledContent}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create Template Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Create Template</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSaveTemplate)} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Template name</Label>
                <Input placeholder="e.g. Cold DM — Software Engineer" maxLength={NAME_MAX_LENGTH} {...register('name')} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>Category</Label>
                <Select onValueChange={(v) => setValue('category', v as TemplateCategory)} defaultValue="Custom">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TEMPLATE_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Template content</Label>
              <p className="text-xs text-slate-500">Use <code className="bg-slate-100 px-1.5 py-0.5 rounded-md font-mono">{'{{placeholder}}'}</code> for dynamic values</p>
              <Textarea
                {...register('content')}
                rows={10}
                maxLength={CONTENT_MAX_LENGTH}
                placeholder={`Hi {{name}},\n\nI came across your profile at {{company}}...`}
                className="font-mono text-sm resize-none"
              />
              <div className="flex justify-between items-center">
                {errors.content && <p className="text-xs text-destructive">{errors.content.message}</p>}
                <p className={cn('text-xs ml-auto', watchContent.length > CONTENT_MAX_LENGTH ? 'text-destructive' : 'text-slate-400')}>
                  {watchContent.length}/{CONTENT_MAX_LENGTH} chars
                </p>
              </div>
            </div>

            {watchContent && extractPlaceholders(watchContent).length > 0 && (
              <div className="flex flex-wrap gap-1.5 p-3 bg-indigo-50 rounded-xl">
                <span className="text-xs text-indigo-600 font-medium">Detected placeholders:</span>
                {extractPlaceholders(watchContent).map((ph) => (
                  <span key={ph} className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-indigo-100 text-indigo-700 border border-indigo-200">
                    {'{{' + ph + '}}'}
                  </span>
                ))}
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowCreate(false)} className="rounded-xl">Cancel</Button>
              <Button
                type="submit"
                disabled={saving}
                className="gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl"
              >
                {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Save Template
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
