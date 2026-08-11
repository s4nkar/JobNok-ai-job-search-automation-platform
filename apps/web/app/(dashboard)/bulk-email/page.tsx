'use client'

import { useState, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Papa from 'papaparse'
import { config } from '@/lib/config'
import { EmailCampaign, EmailRecipient } from '@/lib/types'
import { extractPlaceholders } from '@jobnok/ui'
import { queryKeys } from '@/lib/queryKeys'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Textarea } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import { Badge } from '@jobnok/ui'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@jobnok/ui'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@jobnok/ui'
import { useToast } from '@jobnok/ui'
import {
  Mail, Plus, Upload, Play, Pause, Loader2, CheckCircle, XCircle,
  Clock, Send, RefreshCw, Info
} from 'lucide-react'
import { apiFetch, apiGet } from '@/lib/api'

const STATUS_BADGE: Record<string, JSX.Element> = {
  queued:    <Badge variant="secondary"><Clock className="h-3 w-3 mr-1" />Queued</Badge>,
  sending:   <Badge variant="warning"><Loader2 className="h-3 w-3 mr-1 animate-spin" />Sending</Badge>,
  sent:      <Badge variant="success"><CheckCircle className="h-3 w-3 mr-1" />Sent</Badge>,
  failed:    <Badge variant="destructive"><XCircle className="h-3 w-3 mr-1" />Failed</Badge>,
  draft:     <Badge variant="outline">Draft</Badge>,
  completed: <Badge variant="success"><CheckCircle className="h-3 w-3 mr-1" />Completed</Badge>,
  paused:    <Badge variant="warning"><Pause className="h-3 w-3 mr-1" />Paused</Badge>,
}

interface RecipientRow { email: string; name: string; [key: string]: string }

export default function BulkEmailPage() {
  const queryClient = useQueryClient()
  const { data: campaigns = [] } = useQuery({
    queryKey: queryKeys.campaigns,
    queryFn: () => apiGet<EmailCampaign[]>('/api/campaigns'),
  })
  const [activeCampaign, setActiveCampaign] = useState<EmailCampaign | null>(null)
  const [recipients, setRecipients] = useState<EmailRecipient[]>([])
  const [polling, setPolling] = useState(false)

  // Builder state
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [delay, setDelay] = useState(config.bulkEmail.defaultDelaySeconds)
  const [csvRows, setCsvRows] = useState<RecipientRow[]>([])
  const [creating, setCreating] = useState(false)

  const fileRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  async function openCampaign(c: EmailCampaign) {
    setActiveCampaign(c)
    await fetchRecipients(c.id)
    if (['sending', 'queued'].includes(c.status)) startPolling(c.id)
  }

  async function fetchRecipients(campaignId: string) {
    const res = await apiFetch(`/api/campaigns/${campaignId}/recipients`)
    if (res.ok) setRecipients(await res.json())
  }

  function startPolling(campaignId: string) {
    setPolling(true)
    pollRef.current = setInterval(async () => {
      const res = await apiFetch(`/api/email/${campaignId}/status`)
      if (res.ok) {
        const json = await res.json()
        setRecipients(json.recipients || [])
        setActiveCampaign((prev) => prev ? { ...prev, status: json.status } : prev)
        if (['completed', 'paused', 'failed'].includes(json.status)) stopPolling()
      }
    }, 5000)
  }

  function stopPolling() {
    if (pollRef.current) clearInterval(pollRef.current)
    setPolling(false)
  }

  function handleCsvUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    Papa.parse<RecipientRow>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (result) => {
        if (!result.data[0]?.email) {
          toast({ title: 'CSV must have an "email" column', variant: 'destructive' })
          return
        }
        setCsvRows(result.data.slice(0, config.rateLimits.bulkEmailPerCampaign))
        toast({ title: `${result.data.length} recipients loaded` })
      },
    })
  }

  async function createCampaign() {
    if (!name || !subject || !body || csvRows.length === 0) {
      toast({ title: 'Fill all fields and upload recipients', variant: 'destructive' })
      return
    }
    if (delay < config.bulkEmail.minDelaySeconds) {
      toast({ title: `Minimum delay is ${config.bulkEmail.minDelaySeconds}s`, variant: 'destructive' })
      return
    }

    setCreating(true)
    const res = await apiFetch('/api/email/campaign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, subject, body, delay_seconds: delay, recipients: csvRows }),
    })

    if (res.ok) {
      const campaign = await res.json()
      queryClient.setQueryData<EmailCampaign[]>(queryKeys.campaigns, (prev) => [campaign, ...(prev || [])])
      toast({ title: 'Campaign launched!', description: 'Emails are being queued.' })
      setName(''); setSubject(''); setBody(''); setCsvRows([])
      openCampaign(campaign)
    } else {
      const json = await res.json()
      toast({ title: 'Error', description: json.detail, variant: 'destructive' })
    }
    setCreating(false)
  }

  async function pauseCampaign(id: string) {
    await apiFetch(`/api/email/${id}/pause`, { method: 'POST' })
    await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns })
    if (activeCampaign?.id === id) setActiveCampaign((p) => p ? { ...p, status: 'paused' } : p)
    stopPolling()
  }

  const sent = recipients.filter((r) => r.status === 'sent').length
  const total = recipients.length
  const progress = total ? Math.round((sent / total) * 100) : 0

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-violet-100">
          <Mail className="h-5 w-5 text-violet-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Bulk Email Sender</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Send personalized campaigns with rate control — {config.rateLimits.bulkEmailPerMonth.toLocaleString()} emails/month free
          </p>
        </div>
      </div>

      {/* Rate limit notice */}
      <div className="flex items-start gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500 mt-0.5" />
        <span>
          <strong>Max {config.rateLimits.bulkEmailPerCampaign} recipients/campaign.</strong>{' '}
          Minimum {config.bulkEmail.minDelaySeconds}s delay between sends to avoid spam filters.
          An unsubscribe link is auto-appended to every email.
        </span>
      </div>

      <Tabs defaultValue="builder">
        <TabsList className="mb-6 bg-slate-100 rounded-xl p-1">
          <TabsTrigger value="builder" className="rounded-lg"><Plus className="h-3.5 w-3.5 mr-1.5" />New Campaign</TabsTrigger>
          <TabsTrigger value="campaigns" className="rounded-lg"><Mail className="h-3.5 w-3.5 mr-1.5" />My Campaigns</TabsTrigger>
        </TabsList>

        {/* Campaign Builder */}
        <TabsContent value="builder">
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-4">
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 space-y-4">
                <p className="text-sm font-semibold text-slate-700">Campaign Setup</p>
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Campaign name</Label>
                  <Input placeholder="Q1 Recruiter Outreach" className="rounded-xl border-slate-200" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Email subject</Label>
                  <Input placeholder="{{name}}, exploring {{role}} opportunities" className="rounded-xl border-slate-200" value={subject} onChange={(e) => setSubject(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Email body</Label>
                  <p className="text-xs text-slate-500">Use <code className="bg-slate-100 px-1.5 py-0.5 rounded-md font-mono">{'{{placeholder}}'}</code> for personalization</p>
                  <Textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    rows={10}
                    placeholder={`Hi {{name}},\n\nI'm reaching out about...`}
                    className="text-sm font-mono rounded-xl border-slate-200 resize-none"
                  />
                  {body && extractPlaceholders(body).length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2 p-3 bg-indigo-50 rounded-xl">
                      <span className="text-xs text-indigo-600 font-medium">Placeholders:</span>
                      {extractPlaceholders(body).map((ph) => (
                        <span key={ph} className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-indigo-100 text-indigo-700 border border-indigo-200">
                          {'{{' + ph + '}}'}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Delay between sends (seconds)</Label>
                  <Input
                    type="number"
                    min={config.bulkEmail.minDelaySeconds}
                    className="rounded-xl border-slate-200"
                    value={delay}
                    onChange={(e) => setDelay(Number(e.target.value))}
                  />
                  <p className="text-xs text-slate-400">
                    Min {config.bulkEmail.minDelaySeconds}s · Recommended 30–60s to avoid spam
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                <p className="text-sm font-semibold text-slate-700 mb-1">Recipients</p>
                <p className="text-xs text-slate-500 mb-4">Upload a CSV with columns: email, name, and any custom variables</p>
                <div
                  onClick={() => fileRef.current?.click()}
                  className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center cursor-pointer hover:border-indigo-300 hover:bg-indigo-50/30 transition-all"
                >
                  <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                    <Upload className="h-5 w-5 text-slate-400" />
                  </div>
                  <p className="text-sm font-medium text-slate-600">Click to upload CSV</p>
                  <p className="text-xs text-slate-400 mt-1">Required columns: email, name</p>
                </div>
                <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleCsvUpload} />

                {csvRows.length > 0 && (
                  <div className="mt-4">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-semibold text-emerald-600 flex items-center gap-1.5">
                        <CheckCircle className="h-4 w-4" />
                        {csvRows.length} recipients loaded
                      </p>
                      <span className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded-md">
                        {Object.keys(csvRows[0] || {}).join(', ')}
                      </span>
                    </div>
                    <div className="max-h-40 overflow-y-auto rounded-xl border border-slate-100 text-xs">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-slate-50">
                            {Object.keys(csvRows[0] || {}).slice(0, 4).map((k) => <TableHead key={k}>{k}</TableHead>)}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {csvRows.slice(0, 5).map((row, i) => (
                            <TableRow key={i}>
                              {Object.values(row).slice(0, 4).map((v, j) => <TableCell key={j}>{v}</TableCell>)}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      {csvRows.length > 5 && <p className="text-slate-400 text-center py-1.5">+{csvRows.length - 5} more</p>}
                    </div>
                  </div>
                )}
              </div>

              <Button
                className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
                onClick={createCampaign}
                disabled={creating}
              >
                {creating
                  ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Launching campaign…</>
                  : <><Send className="h-4 w-4 mr-2" /> Launch Campaign</>
                }
              </Button>
            </div>
          </div>
        </TabsContent>

        {/* Campaign List */}
        <TabsContent value="campaigns">
          <div className="grid grid-cols-3 gap-6">
            <div className="col-span-1 space-y-1.5">
              {campaigns.length === 0 && (
                <div className="text-center py-12 text-slate-400">
                  <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                    <Mail className="h-6 w-6 text-slate-300" />
                  </div>
                  <p className="text-sm">No campaigns yet</p>
                </div>
              )}
              {campaigns.map((c) => (
                <button
                  key={c.id}
                  onClick={() => openCampaign(c)}
                  className={`w-full text-left p-3.5 rounded-xl border text-sm transition-all ${
                    activeCampaign?.id === c.id
                      ? 'bg-indigo-600 text-white border-indigo-600 shadow-brand-sm'
                      : 'bg-white hover:bg-slate-50 border-slate-100 shadow-card'
                  }`}
                >
                  <p className="font-semibold truncate text-[13px]">{c.name}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    {STATUS_BADGE[c.status]}
                  </div>
                </button>
              ))}
            </div>

            <div className="col-span-2">
              {!activeCampaign ? (
                <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[300px] flex items-center justify-center p-8">
                  <div className="text-center space-y-2">
                    <div className="w-12 h-12 rounded-2xl bg-violet-50 flex items-center justify-center mx-auto">
                      <Mail className="h-6 w-6 text-violet-200" />
                    </div>
                    <p className="font-semibold text-slate-500">Select a campaign to see details</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="font-bold text-slate-800">{activeCampaign.name}</h3>
                        <p className="text-sm text-slate-500 mt-0.5">{activeCampaign.subject}</p>
                      </div>
                      <div className="flex gap-2 items-center">
                        {STATUS_BADGE[activeCampaign.status]}
                        {activeCampaign.status === 'sending' && (
                          <Button size="sm" variant="outline" onClick={() => pauseCampaign(activeCampaign.id)} className="rounded-xl h-8">
                            <Pause className="h-3.5 w-3.5 mr-1" />Pause
                          </Button>
                        )}
                        {polling && (
                          <Button size="sm" variant="ghost" onClick={() => fetchRecipients(activeCampaign.id)} className="rounded-xl h-8">
                            <RefreshCw className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </div>

                    {total > 0 && (
                      <div>
                        <div className="flex justify-between text-xs text-slate-500 mb-2">
                          <span className="font-medium">{sent} / {total} sent</span>
                          <span>{progress}%</span>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full gradient-brand rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
                    <div className="max-h-96 overflow-y-auto scrollbar-thin">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-slate-50/50">
                            <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Recipient</TableHead>
                            <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Email</TableHead>
                            <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</TableHead>
                            <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Sent at</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {recipients.map((r) => (
                            <TableRow key={r.id} className="border-b border-slate-50">
                              <TableCell className="font-semibold text-slate-800">{r.name}</TableCell>
                              <TableCell className="text-slate-500 text-sm">{r.email}</TableCell>
                              <TableCell>{STATUS_BADGE[r.status] || r.status}</TableCell>
                              <TableCell className="text-sm text-slate-400">
                                {r.sent_at ? new Date(r.sent_at).toLocaleTimeString() : '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
