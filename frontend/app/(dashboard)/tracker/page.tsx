'use client'

import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { JobApplication, ApplicationStatus, APPLICATION_STATUSES, STATUS_COLORS } from '@/lib/types'
import { isOverdue, formatDate, formatCurrency, cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { Plus, Pencil, Trash2, Briefcase, Loader2, AlertCircle, TrendingUp, CheckCircle, Clock } from 'lucide-react'
import { apiFetch } from '@/lib/api'

const schema = z.object({
  company: z.string().min(1, 'Required'),
  role: z.string().min(1, 'Required'),
  applied_at: z.string().min(1, 'Required'),
  status: z.enum(APPLICATION_STATUSES as [ApplicationStatus, ...ApplicationStatus[]]),
  follow_up_date: z.string().optional(),
  salary_min: z.coerce.number().optional(),
  salary_max: z.coerce.number().optional(),
  notes: z.string().optional(),
})
type FormData = z.infer<typeof schema>

const today = new Date().toISOString().split('T')[0]

export default function TrackerPage() {
  const [applications, setApplications] = useState<JobApplication[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<JobApplication | null>(null)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const { register, handleSubmit, setValue, reset, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { applied_at: today, status: 'Applied' },
  })
  const watchStatus = watch('status')

  useEffect(() => { fetchApplications() }, [])

  async function fetchApplications() {
    const res = await apiFetch('/api/tracker')
    const json = await res.json()
    if (res.ok) setApplications(json)
    setLoading(false)
  }

  function openCreate() {
    reset({ applied_at: today, status: 'Applied' })
    setEditing(null)
    setShowForm(true)
  }

  function openEdit(app: JobApplication) {
    reset({
      company: app.company,
      role: app.role,
      applied_at: app.applied_at,
      status: app.status,
      follow_up_date: app.follow_up_date || undefined,
      salary_min: app.salary_min || undefined,
      salary_max: app.salary_max || undefined,
      notes: app.notes || undefined,
    })
    setEditing(app)
    setShowForm(true)
  }

  async function onSubmit(data: FormData) {
    setSaving(true)
    const method = editing ? 'PUT' : 'POST'
    const url = editing ? `/api/tracker/${editing.id}` : '/api/tracker'

    const res = await apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })

    if (res.ok) {
      await fetchApplications()
      setShowForm(false)
      toast({ title: editing ? 'Application updated' : 'Application added' })
    } else {
      toast({ title: 'Error', description: 'Something went wrong', variant: 'destructive' })
    }
    setSaving(false)
  }

  async function deleteApp(id: string) {
    const res = await apiFetch(`/api/tracker/${id}`, { method: 'DELETE' })
    if (res.ok) {
      setApplications((prev) => prev.filter((a) => a.id !== id))
      toast({ title: 'Application removed' })
    }
  }

  const overdue = applications.filter((a) => isOverdue(a.follow_up_date) && a.status !== 'Rejected' && a.status !== 'Withdrawn')
  const active = applications.filter((a) => !['Rejected', 'Withdrawn'].includes(a.status))
  const offers = applications.filter((a) => a.status === 'Offer')

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Follow-Up Tracker</h1>
          <p className="text-slate-500 text-sm mt-1">Track every application — overdue follow-ups highlighted in red</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Add Application
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Total', value: applications.length, icon: Briefcase, color: 'text-slate-600' },
          { label: 'Active', value: active.length, icon: TrendingUp, color: 'text-blue-600' },
          { label: 'Overdue', value: overdue.length, icon: AlertCircle, color: 'text-red-600' },
          { label: 'Offers', value: offers.length, icon: CheckCircle, color: 'text-green-600' },
        ].map(({ label, value, icon: Icon, color }) => (
          <Card key={label}>
            <CardContent className="pt-4 flex items-center gap-3">
              <Icon className={cn('h-5 w-5', color)} />
              <div>
                <p className="text-2xl font-bold text-slate-900">{value}</p>
                <p className="text-xs text-slate-500">{label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            </div>
          ) : applications.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-slate-400">
              <Briefcase className="h-10 w-10 mb-2 opacity-30" />
              <p>No applications yet</p>
              <p className="text-sm">Add your first one to get started</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Applied</TableHead>
                  <TableHead>Follow-up</TableHead>
                  <TableHead>Salary</TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {applications.map((app) => {
                  const overdueRow = isOverdue(app.follow_up_date) && !['Rejected', 'Withdrawn'].includes(app.status)
                  return (
                    <TableRow key={app.id} className={overdueRow ? 'bg-red-50/50' : undefined}>
                      <TableCell className="font-medium">{app.company}</TableCell>
                      <TableCell className="text-slate-600">{app.role}</TableCell>
                      <TableCell>
                        <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', STATUS_COLORS[app.status])}>
                          {app.status}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-slate-500">{formatDate(app.applied_at)}</TableCell>
                      <TableCell>
                        {app.follow_up_date ? (
                          <span className={cn('flex items-center gap-1 text-sm', overdueRow ? 'text-red-600 font-medium' : 'text-slate-500')}>
                            {overdueRow && <AlertCircle className="h-3 w-3" />}
                            {overdueRow && <Clock className="h-3 w-3" />}
                            {formatDate(app.follow_up_date)}
                          </span>
                        ) : <span className="text-slate-300">—</span>}
                      </TableCell>
                      <TableCell className="text-sm text-slate-500">
                        {app.salary_min && app.salary_max
                          ? `${formatCurrency(app.salary_min)} – ${formatCurrency(app.salary_max)}`
                          : '—'
                        }
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(app)}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-400 hover:text-red-500" onClick={() => deleteApp(app.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Add/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Application' : 'Add Application'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label>Company *</Label>
                <Input placeholder="Acme Corp" {...register('company')} />
                {errors.company && <p className="text-xs text-destructive">{errors.company.message}</p>}
              </div>
              <div className="space-y-1">
                <Label>Role *</Label>
                <Input placeholder="Software Engineer" {...register('role')} />
                {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label>Applied date *</Label>
                <Input type="date" {...register('applied_at')} />
              </div>
              <div className="space-y-1">
                <Label>Status</Label>
                <Select value={watchStatus} onValueChange={(v) => setValue('status', v as ApplicationStatus)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {APPLICATION_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1">
              <Label>Follow-up date</Label>
              <Input type="date" {...register('follow_up_date')} />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label>Salary min ($)</Label>
                <Input type="number" placeholder="80000" {...register('salary_min')} />
              </div>
              <div className="space-y-1">
                <Label>Salary max ($)</Label>
                <Input type="number" placeholder="120000" {...register('salary_max')} />
              </div>
            </div>

            <div className="space-y-1">
              <Label>Notes</Label>
              <Textarea rows={3} placeholder="Any notes about this application…" {...register('notes')} />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>
                {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {editing ? 'Save Changes' : 'Add Application'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
