'use client'

import { useEffect, useState, useRef } from 'react'
import Papa from 'papaparse'
import { config } from '@/lib/config'
import { EmailCampaign, EmailRecipient } from '@/lib/types'
import { extractPlaceholders } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { Progress } from '@/components/ui/progress'
import {
  Mail, Plus, Upload, Play, Pause, Loader2, CheckCircle, XCircle,
  Clock, Send, RefreshCw, Info
} from 'lucide-react'
import { apiFetch } from '@/lib/api'

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
  const [campaigns, setCampaigns] = useState<EmailCampaign[]>([])
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

  useEffect(() => { fetchCampaigns() }, [])

  async function fetchCampaigns() {
    const res = await apiFetch('/api/campaigns')
    if (res.ok) setCampaigns(await res.json())
  }

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
      setCampaigns((prev) => [campaign, ...prev])
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
    await fetchCampaigns()
    if (activeCampaign?.id === id) setActiveCampaign((p) => p ? { ...p, status: 'paused' } : p)
    stopPolling()
  }

  const sent = recipients.filter((r) => r.status === 'sent').length
  const total = recipients.length
  const progress = total ? Math.round((sent / total) * 100) : 0

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Bulk Email Sender</h1>
        <p className="text-slate-500 text-sm mt-1">
          Send personalized campaigns with rate control — {config.rateLimits.bulkEmailPerMonth.toLocaleString()} emails/month free
        </p>
      </div>

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>Max {config.rateLimits.bulkEmailPerCampaign} recipients/campaign.</strong>{' '}
          Minimum {config.bulkEmail.minDelaySeconds}s delay between sends to avoid spam filters.
          An unsubscribe link is auto-appended to every email.
        </AlertDescription>
      </Alert>

      <Tabs defaultValue="builder">
        <TabsList className="mb-6">
          <TabsTrigger value="builder"><Plus className="h-3.5 w-3.5 mr-1.5" />New Campaign</TabsTrigger>
          <TabsTrigger value="campaigns"><Mail className="h-3.5 w-3.5 mr-1.5" />My Campaigns</TabsTrigger>
        </TabsList>

        {/* Campaign Builder */}
        <TabsContent value="builder">
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Campaign Setup</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-1">
                    <Label>Campaign name</Label>
                    <Input placeholder="Q1 Recruiter Outreach" value={name} onChange={(e) => setName(e.target.value)} />
                  </div>
                  <div className="space-y-1">
                    <Label>Email subject</Label>
                    <Input placeholder="{{name}}, exploring {{role}} opportunities" value={subject} onChange={(e) => setSubject(e.target.value)} />
                  </div>
                  <div className="space-y-1">
                    <Label>Email body</Label>
                    <p className="text-xs text-slate-500">Use <code className="bg-slate-100 px-1 rounded">{'{{placeholder}}'}</code> for personalization</p>
                    <Textarea
                      value={body}
                      onChange={(e) => setBody(e.target.value)}
                      rows={10}
                      placeholder={`Hi {{name}},\n\nI'm reaching out about...`}
                      className="text-sm font-mono"
                    />
                    {body && extractPlaceholders(body).length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {extractPlaceholders(body).map((ph) => (
                          <Badge key={ph} variant="secondary" className="text-xs">{'{{' + ph + '}}'}</Badge>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="space-y-1">
                    <Label>Delay between sends (seconds)</Label>
                    <Input
                      type="number"
                      min={config.bulkEmail.minDelaySeconds}
                      value={delay}
                      onChange={(e) => setDelay(Number(e.target.value))}
                    />
                    <p className="text-xs text-slate-400">
                      Min {config.bulkEmail.minDelaySeconds}s · Recommended 30–60s to avoid spam
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Recipients</CardTitle>
                  <CardDescription>Upload a CSV with columns: email, name, and any custom variables</CardDescription>
                </CardHeader>
                <CardContent>
                  <div
                    onClick={() => fileRef.current?.click()}
                    className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-slate-300 hover:bg-slate-50 transition-colors"
                  >
                    <Upload className="h-8 w-8 mx-auto text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Click to upload CSV</p>
                    <p className="text-xs text-slate-400 mt-1">Required columns: email, name</p>
                  </div>
                  <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleCsvUpload} />

                  {csvRows.length > 0 && (
                    <div className="mt-4">
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-green-600">
                          <CheckCircle className="h-4 w-4 inline mr-1" />
                          {csvRows.length} recipients loaded
                        </p>
                        <Badge variant="outline">{Object.keys(csvRows[0] || {}).join(', ')}</Badge>
                      </div>
                      <div className="max-h-40 overflow-y-auto text-xs">
                        <Table>
                          <TableHeader>
                            <TableRow>
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
                        {csvRows.length > 5 && <p className="text-slate-400 text-center py-1">+{csvRows.length - 5} more</p>}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Button className="w-full" onClick={createCampaign} disabled={creating}>
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
            <div className="col-span-1 space-y-2">
              {campaigns.length === 0 && (
                <div className="text-center py-12 text-slate-400">
                  <Mail className="h-10 w-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No campaigns yet</p>
                </div>
              )}
              {campaigns.map((c) => (
                <button
                  key={c.id}
                  onClick={() => openCampaign(c)}
                  className={`w-full text-left p-3 rounded-lg border text-sm transition-colors ${
                    activeCampaign?.id === c.id ? 'bg-primary text-primary-foreground border-primary' : 'bg-white hover:bg-slate-50 border-slate-200'
                  }`}
                >
                  <p className="font-medium truncate">{c.name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    {STATUS_BADGE[c.status]}
                  </div>
                </button>
              ))}
            </div>

            <div className="col-span-2">
              {!activeCampaign ? (
                <Card className="min-h-[300px] flex items-center justify-center">
                  <CardContent className="text-center text-slate-400 pt-6">
                    <Mail className="h-10 w-10 mx-auto mb-2 opacity-20" />
                    <p>Select a campaign to see details</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  <Card>
                    <CardContent className="pt-4">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <h3 className="font-semibold">{activeCampaign.name}</h3>
                          <p className="text-sm text-slate-500">{activeCampaign.subject}</p>
                        </div>
                        <div className="flex gap-2">
                          {STATUS_BADGE[activeCampaign.status]}
                          {activeCampaign.status === 'sending' && (
                            <Button size="sm" variant="outline" onClick={() => pauseCampaign(activeCampaign.id)}>
                              <Pause className="h-3.5 w-3.5 mr-1" />Pause
                            </Button>
                          )}
                          {polling && (
                            <Button size="sm" variant="ghost" onClick={() => fetchRecipients(activeCampaign.id)}>
                              <RefreshCw className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>

                      {total > 0 && (
                        <div>
                          <div className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>{sent} / {total} sent</span>
                            <span>{progress}%</span>
                          </div>
                          <Progress value={progress} className="h-2" />
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardContent className="p-0 max-h-96 overflow-y-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Recipient</TableHead>
                            <TableHead>Email</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Sent at</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {recipients.map((r) => (
                            <TableRow key={r.id}>
                              <TableCell className="font-medium">{r.name}</TableCell>
                              <TableCell className="text-slate-500 text-sm">{r.email}</TableCell>
                              <TableCell>{STATUS_BADGE[r.status] || r.status}</TableCell>
                              <TableCell className="text-sm text-slate-400">
                                {r.sent_at ? new Date(r.sent_at).toLocaleTimeString() : '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                </div>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
