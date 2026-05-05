'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { config } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Salary Research</h1>
        <p className="text-slate-500 text-sm mt-1">
          Get market rate data, compensation factors, and negotiation talking points
        </p>
      </div>

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>{config.rateLimits.salaryResearchPerDay} researches/day</strong> on the free tier.
          AI aggregates data from public sources in real-time.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-3 gap-6">
        {/* Input */}
        <div className="col-span-1">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Card>
              <CardContent className="pt-4 space-y-4">
                <div className="space-y-1">
                  <Label>Job title</Label>
                  <Input placeholder="Senior Software Engineer" {...register('job_title')} />
                  {errors.job_title && <p className="text-xs text-destructive">{errors.job_title.message}</p>}
                </div>
                <div className="space-y-1">
                  <Label>Location</Label>
                  <Input placeholder="San Francisco, CA" {...register('location')} />
                  {errors.location && <p className="text-xs text-destructive">{errors.location.message}</p>}
                </div>
              </CardContent>
            </Card>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Researching…</>
                : <><TrendingUp className="h-4 w-4 mr-2" /> Research Salary</>
              }
            </Button>

            <Card>
              <CardContent className="pt-4">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">What you get</p>
                <ul className="space-y-1.5 text-sm text-slate-600">
                  <li className="flex items-center gap-2"><DollarSign className="h-3.5 w-3.5 text-green-500" />Median salary + range</li>
                  <li className="flex items-center gap-2"><TrendingUp className="h-3.5 w-3.5 text-blue-500" />Factors affecting pay</li>
                  <li className="flex items-center gap-2"><MessageSquare className="h-3.5 w-3.5 text-purple-500" />Negotiation talking points</li>
                </ul>
              </CardContent>
            </Card>
          </form>
        </div>

        {/* Results */}
        <div className="col-span-2">
          {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}

          {!streamOutput && !loading && (
            <Card className="min-h-[400px] flex items-center justify-center">
              <CardContent className="text-center text-slate-400 pt-6">
                <DollarSign className="h-12 w-12 mx-auto mb-3 opacity-20" />
                <p>Salary research will appear here</p>
                <p className="text-sm mt-1">Results stream in real-time</p>
              </CardContent>
            </Card>
          )}

          {(streamOutput || loading) && (
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">Research Results</CardTitle>
                  {loading && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
                </div>
              </CardHeader>
              <CardContent>
                <div className="prose prose-sm max-w-none text-slate-700 whitespace-pre-wrap leading-relaxed">
                  {streamOutput}
                  {loading && <span className="inline-block w-1.5 h-4 bg-slate-400 animate-pulse ml-0.5 align-middle" />}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
