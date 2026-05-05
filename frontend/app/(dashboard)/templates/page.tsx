'use client'

import { useEffect, useState, useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/client'
import { useTemplateStore } from '@/lib/stores/templates'
import { PREBUILT_TEMPLATES } from '@/lib/templates/prebuilt'
import { extractPlaceholders, fillTemplate, cn } from '@/lib/utils'
import { TEMPLATE_CATEGORIES, type Template, type TemplateCategory } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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

export default function TemplatesPage() {
  const { savedTemplates, setSavedTemplates, addTemplate, removeTemplate } = useTemplateStore()
  const [selected, setSelected] = useState<Template | null>(null)
  const [fillValues, setFillValues] = useState<Record<string, string>>({})
  const [filledContent, setFilledContent] = useState('')
  const [copied, setCopied] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [saving, setSaving] = useState(false)
  const [filterCategory, setFilterCategory] = useState<string>('all')
  const { toast } = useToast()
  const supabase = createClient()

  const { register, handleSubmit, setValue, reset, watch, formState: { errors } } = useForm<TemplateFormData>({
    resolver: zodResolver(templateSchema),
    defaultValues: { category: 'Custom' },
  })

  const watchContent = watch('content', '')

  useEffect(() => {
    async function load() {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return
      const { data } = await supabase
        .from('templates')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })
      if (data) setSavedTemplates(data)
    }
    load()
  }, [])

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
      await supabase.from('templates').update({ use_count: (selected.use_count || 0) + 1 }).eq('id', selected.id)
    }
    setTimeout(() => setCopied(false), 3000)
  }

  async function onSaveTemplate(data: TemplateFormData) {
    setSaving(true)
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    const placeholders = extractPlaceholders(data.content)
    const { data: saved, error } = await supabase.from('templates').insert({
      user_id: user.id,
      name: data.name,
      category: data.category,
      content: data.content,
      placeholders,
    }).select().single()

    if (error) {
      toast({ title: 'Error saving template', description: error.message, variant: 'destructive' })
    } else {
      addTemplate(saved)
      toast({ title: 'Template saved!' })
      reset()
      setShowCreate(false)
    }
    setSaving(false)
  }

  async function deleteTemplate(id: string) {
    const { error } = await supabase.from('templates').delete().eq('id', id)
    if (!error) {
      removeTemplate(id)
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
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Smart Templates</h1>
          <p className="text-slate-500 text-sm mt-1">
            Create reusable messages with <code className="bg-slate-100 px-1 rounded">{'{{placeholder}}'}</code> auto-fill
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Template
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Template List */}
        <div className="col-span-1 space-y-3">
          <Select value={filterCategory} onValueChange={setFilterCategory}>
            <SelectTrigger className="h-9 text-sm">
              <SelectValue placeholder="All categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {TEMPLATE_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>

          <div className="space-y-1.5 max-h-[calc(100vh-250px)] overflow-y-auto pr-1">
            {filtered.length === 0 && (
              <div className="text-center py-8 text-slate-400 text-sm">
                <FileText className="h-8 w-8 mx-auto mb-2 opacity-40" />
                No templates found
              </div>
            )}
            {filtered.map((t) => (
              <button
                key={t.id}
                onClick={() => selectTemplate(t)}
                className={cn(
                  'w-full text-left p-3 rounded-lg border text-sm transition-colors',
                  selected?.id === t.id
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                )}
              >
                <div className="font-medium truncate">{t.name}</div>
                <div className={cn('text-xs mt-0.5', selected?.id === t.id ? 'text-primary-foreground/70' : 'text-slate-400')}>
                  {t.category}
                  {t.is_prebuilt && ' · Pre-built'}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Template Editor / Fill */}
        <div className="col-span-2">
          {!selected ? (
            <Card className="h-full flex items-center justify-center min-h-[400px]">
              <CardContent className="text-center text-slate-400 pt-6">
                <FileText className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p className="font-medium">Select a template to get started</p>
                <p className="text-sm mt-1">Or create a new one with the button above</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{selected.name}</CardTitle>
                    <div className="flex gap-2">
                      <Badge variant="outline">{selected.category}</Badge>
                      {!selected.is_prebuilt && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-slate-400 hover:text-red-500"
                          onClick={() => deleteTemplate(selected.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
              </Card>

              {/* Placeholder Inputs */}
              {selected.placeholders.length > 0 && (
                <Card>
                  <CardContent className="pt-4 pb-4">
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">Fill in placeholders</p>
                    <div className="grid grid-cols-2 gap-3">
                      {selected.placeholders.map((ph) => (
                        <div key={ph} className="space-y-1">
                          <Label className="text-xs text-slate-600">{ph.replace(/_/g, ' ')}</Label>
                          <Input
                            placeholder={`Enter ${ph.replace(/_/g, ' ')}`}
                            value={fillValues[ph] || ''}
                            onChange={(e) => updateFill(ph, e.target.value)}
                            className="h-8 text-sm"
                          />
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Filled Output */}
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Output</p>
                    <div className="flex items-center gap-2">
                      {overLinkedInLimit && (
                        <span className="flex items-center gap-1 text-xs text-amber-600">
                          <AlertCircle className="h-3 w-3" />
                          Over LinkedIn limit ({charCount}/{LINKEDIN_CHAR_LIMIT})
                        </span>
                      )}
                      {!overLinkedInLimit && charCount > 0 && (
                        <span className="text-xs text-slate-400">{charCount} chars</span>
                      )}
                      <Button size="sm" onClick={copyToClipboard} disabled={charCount === 0}>
                        {copied ? <Check className="h-3.5 w-3.5 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
                        {copied ? 'Copied!' : 'Copy'}
                      </Button>
                    </div>
                  </div>
                  <pre className="whitespace-pre-wrap text-sm text-slate-700 bg-slate-50 rounded-md p-3 min-h-[180px] font-sans leading-relaxed">
                    {filledContent}
                  </pre>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* Create Template Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create Template</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSaveTemplate)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label>Template name</Label>
                <Input placeholder="e.g. Cold DM — Software Engineer" {...register('name')} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="space-y-1">
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

            <div className="space-y-1">
              <Label>Template content</Label>
              <p className="text-xs text-slate-500">Use <code className="bg-slate-100 px-1 rounded">{'{{placeholder}}'}</code> for dynamic values</p>
              <Textarea
                {...register('content')}
                rows={10}
                placeholder={`Hi {{name}},\n\nI came across your profile at {{company}}...`}
                className="font-mono text-sm"
              />
              <div className="flex justify-between items-center">
                {errors.content && <p className="text-xs text-destructive">{errors.content.message}</p>}
                <p className="text-xs text-slate-400 ml-auto">{watchContent.length} chars</p>
              </div>
            </div>

            {watchContent && extractPlaceholders(watchContent).length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                <span className="text-xs text-slate-500">Detected:</span>
                {extractPlaceholders(watchContent).map((ph) => (
                  <Badge key={ph} variant="secondary" className="text-xs">{'{{' + ph + '}}'}</Badge>
                ))}
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>
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
