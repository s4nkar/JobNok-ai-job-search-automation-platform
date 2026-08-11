'use client'

import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { PREBUILT_TEMPLATES } from '@/lib/templates/prebuilt'
import { extractPlaceholders, fillTemplate, cn } from '@/lib/utils'
import { TEMPLATE_CATEGORIES, type Template, type TemplateCategory } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import { Plus, Copy, Check, Trash2, FileText, Loader2, AlertCircle } from 'lucide-react'

const LINKEDIN_CHAR_LIMIT = 300

const templateSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  category: z.enum(TEMPLATE_CATEGORIES as [TemplateCategory, ...TemplateCategory[]]),
  content: z.string().min(10, 'Template must be at least 10 characters'),
})
type TemplateFormData = z.infer<typeof templateSchema>

const categoryColors: Record<string, string> = {
  'LinkedIn': 'bg-blue-50 text-blue-700 border-blue-100',
  'Email': 'bg-violet-50 text-violet-700 border-violet-100',
  'Follow-up': 'bg-amber-50 text-amber-700 border-amber-100',
  'Thank You': 'bg-emerald-50 text-emerald-700 border-emerald-100',
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
      await apiFetch(`/api/templates/${selected.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_count: (selected.use_count || 0) + 1 }),
      })
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
          <div className="page-header-icon bg-blue-100">
            <FileText className="h-5 w-5 text-blue-600" />
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
          className="gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl h-10 px-5"
        >
          <Plus className="h-4 w-4 mr-2" />
          New Template
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Template List */}
        <div className="col-span-1 space-y-3">
          <Select value={filterCategory} onValueChange={setFilterCategory}>
            <SelectTrigger className="h-9 text-sm rounded-xl border-slate-200">
              <SelectValue placeholder="All categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {TEMPLATE_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>

          <div className="space-y-1.5 max-h-[calc(100vh-280px)] overflow-y-auto pr-1 scrollbar-thin">
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
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-brand-sm'
                    : 'bg-white border-slate-100 hover:border-slate-200 hover:shadow-card shadow-card'
                )}
              >
                <div className="font-semibold truncate text-[13px]">{t.name}</div>
                <div className={cn('mt-1.5 flex items-center gap-1.5', selected?.id === t.id ? 'opacity-70' : '')}>
                  {selected?.id !== t.id && <CategoryBadge category={t.category} />}
                  {selected?.id === t.id && (
                    <span className="text-xs text-indigo-200">{t.category}</span>
                  )}
                  {t.is_prebuilt && (
                    <span className={cn('text-[10px]', selected?.id === t.id ? 'text-indigo-200' : 'text-slate-400')}>· Pre-built</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Template Editor / Fill */}
        <div className="col-span-2">
          {!selected ? (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto">
                  <FileText className="h-7 w-7 text-blue-200" />
                </div>
                <p className="font-semibold text-slate-500">Select a template to get started</p>
                <p className="text-sm text-slate-400">Or create a new one with the button above</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Template header */}
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card px-5 py-4 flex items-center justify-between">
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
                <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">Fill in placeholders</p>
                  <div className="grid grid-cols-2 gap-3">
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
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
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
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Template name</Label>
                <Input placeholder="e.g. Cold DM — Software Engineer" className="rounded-xl" {...register('name')} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Category</Label>
                <Select onValueChange={(v) => setValue('category', v as TemplateCategory)} defaultValue="Custom">
                  <SelectTrigger className="rounded-xl">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TEMPLATE_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm font-medium">Template content</Label>
              <p className="text-xs text-slate-500">Use <code className="bg-slate-100 px-1.5 py-0.5 rounded-md font-mono">{'{{placeholder}}'}</code> for dynamic values</p>
              <Textarea
                {...register('content')}
                rows={10}
                placeholder={`Hi {{name}},\n\nI came across your profile at {{company}}...`}
                className="font-mono text-sm rounded-xl resize-none border-slate-200"
              />
              <div className="flex justify-between items-center">
                {errors.content && <p className="text-xs text-destructive">{errors.content.message}</p>}
                <p className="text-xs text-slate-400 ml-auto">{watchContent.length} chars</p>
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
