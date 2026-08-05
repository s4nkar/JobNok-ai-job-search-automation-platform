'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { DollarSign, Loader2, TrendingUp, Info, MessageSquare } from 'lucide-react'
import { apiFetch } from '@/lib/api'

const schema = z.object({
  job_title: z.string().min(2, 'Enter a job title'),
  location: z.string().min(2, 'Enter a location'),
})
type FormData = z.infer<typeof schema>

export default function SalaryPage() {
  const [loading, setLoading] = useState(false)
  const [streamOutput, setStreamOutput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  async function onSubmit(data: FormData) {
    setLoading(true)
    setStreamOutput('')
    setError(null)

    try {
      const res = await apiFetch('/api/ai/salary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })

      if (!res.ok) {
        const json = await res.json()
        setError(json.detail || 'Research failed. Try again.')
        setLoading(false)
        return
      }

      if (!res.body) { setLoading(false); return }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        setStreamOutput((prev) => prev + decoder.decode(value))
      }
    } catch {
      setError('Network error. Please try again.')
    }

    setLoading(false)
  }

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-emerald-100">
          <DollarSign className="h-5 w-5 text-emerald-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Salary Research</h1>
          <p className="text-slate-500 text-sm mt-0.5">Get market rate data, compensation factors, and negotiation talking points</p>
        </div>
      </div>

      {/* Rate limit notice */}
      <div className="flex items-center gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500" />
        <span><strong>{config.rateLimits.salaryResearchPerDay} researches/day</strong> on the free tier. AI aggregates data from public sources in real-time.</span>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Input */}
        <div className="col-span-1 space-y-4">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 space-y-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Job title</Label>
                <Input placeholder="Senior Software Engineer" className="rounded-xl border-slate-200" {...register('job_title')} />
                {errors.job_title && <p className="text-xs text-destructive">{errors.job_title.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Location</Label>
                <Input placeholder="San Francisco, CA" className="rounded-xl border-slate-200" {...register('location')} />
                {errors.location && <p className="text-xs text-destructive">{errors.location.message}</p>}
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
              disabled={loading}
            >
              {loading
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Researching…</>
                : <><TrendingUp className="h-4 w-4 mr-2" /> Research Salary</>
              }
            </Button>
          </form>

          {/* What you get */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">What you get</p>
            <ul className="space-y-3">
              <li className="flex items-center gap-3 text-sm text-slate-600">
                <div className="w-7 h-7 rounded-lg bg-emerald-50 flex items-center justify-center flex-shrink-0">
                  <DollarSign className="h-3.5 w-3.5 text-emerald-600" />
                </div>
                Median salary + range
              </li>
              <li className="flex items-center gap-3 text-sm text-slate-600">
                <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                  <TrendingUp className="h-3.5 w-3.5 text-blue-600" />
                </div>
                Factors affecting pay
              </li>
              <li className="flex items-center gap-3 text-sm text-slate-600">
                <div className="w-7 h-7 rounded-lg bg-violet-50 flex items-center justify-center flex-shrink-0">
                  <MessageSquare className="h-3.5 w-3.5 text-violet-600" />
                </div>
                Negotiation talking points
              </li>
            </ul>
          </div>
        </div>

        {/* Results */}
        <div className="col-span-2">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm mb-4">
              {error}
            </div>
          )}

          {!streamOutput && !loading && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[400px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto">
                  <DollarSign className="h-7 w-7 text-emerald-200" />
                </div>
                <p className="font-semibold text-slate-500">Salary research will appear here</p>
                <p className="text-sm text-slate-400">Results stream in real-time</p>
              </div>
            </div>
          )}

          {(streamOutput || loading) && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
              <div className="flex items-center gap-2 mb-4">
                <p className="text-sm font-semibold text-slate-700">Research Results</p>
                {loading && <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />}
              </div>
              <div className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                {streamOutput}
                {loading && <span className="inline-block w-1.5 h-4 bg-indigo-400 animate-pulse ml-0.5 align-middle rounded-sm" />}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
