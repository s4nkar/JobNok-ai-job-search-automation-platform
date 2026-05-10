'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { PenLine, Loader2, Copy, Check, Info } from 'lucide-react'
import { apiFetch } from '@/lib/api'

const schema = z.object({
  company: z.string().min(1, 'Required'),
  role: z.string().min(1, 'Required'),
  selling_points: z.string().min(20, 'Describe at least one selling point'),
  resume_text: z.string().optional(),
})
type FormData = z.infer<typeof schema>

export default function CoverLetterPage() {
  const [loading, setLoading] = useState(false)
  const [output, setOutput] = useState('')
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  async function onSubmit(data: FormData) {
    setLoading(true)
    setOutput('')
    setError(null)

    try {
      const res = await apiFetch('/api/ai/cover-letter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })

      if (!res.ok) {
        const json = await res.json()
        setError(json.detail || 'Generation failed. Try again.')
        setLoading(false)
        return
      }

      if (!res.body) { setLoading(false); return }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        setOutput((prev) => prev + decoder.decode(value))
      }
    } catch {
      setError('Network error. Please try again.')
    }

    setLoading(false)
  }

  async function copy() {
    await navigator.clipboard.writeText(output)
    setCopied(true)
    toast({ title: 'Copied to clipboard!' })
    setTimeout(() => setCopied(false), 3000)
  }

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-pink-100">
          <PenLine className="h-5 w-5 text-pink-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Cover Letter Generator</h1>
          <p className="text-slate-500 text-sm mt-0.5">AI writes a tailored cover letter — edit inline before sending</p>
        </div>
      </div>

      {/* Rate limit notice */}
      <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500" />
        <span><strong>{config.rateLimits.coverLetterPerDay} letters/day</strong> on the free tier.</span>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Input Form */}
        <div>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Company name</Label>
                  <Input placeholder="Acme Corp" className="rounded-xl border-slate-200" {...register('company')} />
                  {errors.company && <p className="text-xs text-destructive">{errors.company.message}</p>}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Role / position</Label>
                  <Input placeholder="Senior Software Engineer" className="rounded-xl border-slate-200" {...register('role')} />
                  {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Your key selling points</Label>
                <p className="text-xs text-slate-500">What makes you the right fit? Be specific.</p>
                <Textarea
                  {...register('selling_points')}
                  rows={5}
                  placeholder="5 years building React apps, led a team of 4 engineers, shipped 3 major product launches..."
                  className="rounded-xl border-slate-200 resize-none"
                />
                {errors.selling_points && <p className="text-xs text-destructive">{errors.selling_points.message}</p>}
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm font-medium">
                  Resume text <span className="text-slate-400 font-normal">(optional)</span>
                </Label>
                <Textarea
                  {...register('resume_text')}
                  rows={4}
                  placeholder="Paste resume text to help AI tailor the letter more precisely..."
                  className="text-sm rounded-xl border-slate-200 resize-none"
                />
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
              disabled={loading}
            >
              {loading
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
                : <><PenLine className="h-4 w-4 mr-2" /> Generate Cover Letter</>
              }
            </Button>
          </form>
        </div>

        {/* Output */}
        <div>
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm mb-4">
              {error}
            </div>
          )}

          {!output && !loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-pink-50 flex items-center justify-center mx-auto">
                  <PenLine className="h-7 w-7 text-pink-200" />
                </div>
                <p className="font-semibold text-slate-500">Your cover letter will appear here</p>
                <p className="text-sm text-slate-400">Streams in real-time as it&apos;s generated</p>
              </div>
            </div>
          )}

          {(output || loading) && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-slate-700">Cover Letter</p>
                {output && (
                  <button
                    onClick={copy}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      copied
                        ? 'bg-emerald-500 text-white'
                        : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100'
                    }`}
                  >
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                )}
              </div>
              <Textarea
                value={output}
                onChange={(e) => setOutput(e.target.value)}
                rows={20}
                className="text-sm leading-relaxed font-sans rounded-xl border-slate-200 resize-none"
                placeholder={loading ? 'Generating…' : ''}
              />
              {loading && (
                <div className="flex items-center gap-2 mt-2 text-sm text-slate-400">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Writing…
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
