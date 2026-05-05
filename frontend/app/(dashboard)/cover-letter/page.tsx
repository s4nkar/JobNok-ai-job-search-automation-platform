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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Cover Letter Generator</h1>
        <p className="text-slate-500 text-sm mt-1">AI writes a tailored cover letter — edit inline before sending</p>
      </div>

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>{config.rateLimits.coverLetterPerDay} letters/day</strong> on the free tier.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-2 gap-6">
        {/* Input Form */}
        <div>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Card>
              <CardContent className="pt-4 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Company name</Label>
                    <Input placeholder="Acme Corp" {...register('company')} />
                    {errors.company && <p className="text-xs text-destructive">{errors.company.message}</p>}
                  </div>
                  <div className="space-y-1">
                    <Label>Role / position</Label>
                    <Input placeholder="Senior Software Engineer" {...register('role')} />
                    {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
                  </div>
                </div>

                <div className="space-y-1">
                  <Label>Your key selling points</Label>
                  <p className="text-xs text-slate-500">What makes you the right fit? Be specific.</p>
                  <Textarea
                    {...register('selling_points')}
                    rows={5}
                    placeholder="5 years building React apps, led a team of 4 engineers, shipped 3 major product launches, strong background in TypeScript and performance optimization..."
                  />
                  {errors.selling_points && <p className="text-xs text-destructive">{errors.selling_points.message}</p>}
                </div>

                <div className="space-y-1">
                  <Label>Resume text <span className="text-slate-400">(optional)</span></Label>
                  <Textarea
                    {...register('resume_text')}
                    rows={4}
                    placeholder="Paste resume text to help AI tailor the letter more precisely..."
                    className="text-sm"
                  />
                </div>
              </CardContent>
            </Card>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
                : <><PenLine className="h-4 w-4 mr-2" /> Generate Cover Letter</>
              }
            </Button>
          </form>
        </div>

        {/* Output */}
        <div>
          {!output && !loading && (
            <Card className="min-h-[400px] flex items-center justify-center">
              <CardContent className="text-center text-slate-400 pt-6">
                <PenLine className="h-12 w-12 mx-auto mb-3 opacity-20" />
                <p>Your cover letter will appear here</p>
                <p className="text-sm mt-1">Streams in real-time as it&apos;s generated</p>
              </CardContent>
            </Card>
          )}

          {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}

          {(output || loading) && (
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Cover Letter</CardTitle>
                  {output && (
                    <Button size="sm" variant="outline" onClick={copy}>
                      {copied ? <Check className="h-3.5 w-3.5 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
                      {copied ? 'Copied!' : 'Copy'}
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <Textarea
                  value={output}
                  onChange={(e) => setOutput(e.target.value)}
                  rows={20}
                  className="text-sm leading-relaxed font-sans"
                  placeholder={loading ? 'Generating…' : ''}
                />
                {loading && (
                  <div className="flex items-center gap-2 mt-2 text-sm text-slate-500">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Writing…
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
