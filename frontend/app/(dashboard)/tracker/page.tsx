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

const statConfigs = (total: number, active: number, overdue: number, offers: number) => [
  {
    label: 'Total',
    value: total,
    icon: Briefcase,
    iconBg: 'bg-slate-100',
    iconColor: 'text-slate-600',
    valueBg: 'bg-white',
  },
  {
    label: 'Active',
    value: active,
    icon: TrendingUp,
    iconBg: 'bg-blue-100',
    iconColor: 'text-blue-600',
    valueBg: 'bg-white',
  },
  {
    label: 'Overdue',
    value: overdue,
    icon: AlertCircle,
    iconBg: 'bg-red-100',
    iconColor: 'text-red-600',
    valueBg: 'bg-white',
  },
  {
    label: 'Offers',
    value: offers,
    icon: CheckCircle,
    iconBg: 'bg-emerald-100',
    iconColor: 'text-emerald-600',
    valueBg: 'bg-white',
  },
]

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
  const stats = statConfigs(applications.length, active.length, overdue.length, offers.length)

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="page-header-icon bg-indigo-100">
            <Briefcase className="h-5 w-5 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Follow-Up Tracker</h1>
            <p className="text-slate-500 text-sm mt-0.5">Track every application — overdue follow-ups highlighted</p>
          </div>
        </div>
        <Button
          onClick={openCreate}
          className="gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl h-10 px-5"
        >
          <Plus className="h-4 w-4 mr-2" />
          Add Application
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {stats.map(({ label, value, icon: Icon, iconBg, iconColor }) => (
          <div key={label} className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 flex items-center gap-4">
            <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0', iconBg)}>
              <Icon className={cn('h-5 w-5', iconColor)} />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900 leading-none">{value}</p>
              <p className="text-xs text-slate-500 mt-1">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
              <p className="text-sm text-slate-400">Loading applications…</p>
            </div>
          </div>
        ) : applications.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-56 text-slate-400">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
              <Briefcase className="h-7 w-7 text-slate-300" />
            </div>
            <p className="font-medium text-slate-600">No applications yet</p>
            <p className="text-sm mt-1">Add your first one to get started</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50/50 border-b border-slate-100 hover:bg-slate-50/50">
                <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Company</TableHead>
                <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Role</TableHead>
                <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Applied</TableHead>
                <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Follow-up</TableHead>
                <TableHead className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Salary</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {applications.map((app) => {
                const overdueRow = isOverdue(app.follow_up_date) && !['Rejected', 'Withdrawn'].includes(app.status)
                return (
                  <TableRow
                    key={app.id}
                    className={cn(
                      'border-b border-slate-50 hover:bg-slate-50/50 transition-colors',
                      overdueRow && 'bg-red-50/40 hover:bg-red-50/60'
                    )}
                  >
                    <TableCell className="font-semibold text-slate-800">{app.company}</TableCell>
                    <TableCell className="text-slate-600">{app.role}</TableCell>
                    <TableCell>
                      <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', STATUS_COLORS[app.status])}>
                        {app.status}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-slate-500">{formatDate(app.applied_at)}</TableCell>
                    <TableCell>
                      {app.follow_up_date ? (
                        <span className={cn('flex items-center gap-1.5 text-sm', overdueRow ? 'text-red-600 font-medium' : 'text-slate-500')}>
                          {overdueRow && <Clock className="h-3 w-3" />}
                          {formatDate(app.follow_up_date)}
                        </span>
                      ) : <span className="text-slate-300 text-sm">—</span>}
                    </TableCell>
                    <TableCell className="text-sm text-slate-500">
                      {app.salary_min && app.salary_max
                        ? `${formatCurrency(app.salary_min)} – ${formatCurrency(app.salary_max)}`
                        : <span className="text-slate-300">—</span>
                      }
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <button
                          onClick={() => openEdit(app)}
                          className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => deleteApp(app.id)}
                          className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Add/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-lg rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">{editing ? 'Edit Application' : 'Add Application'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Company</Label>
                <Input placeholder="Acme Corp" className="rounded-xl" {...register('company')} />
                {errors.company && <p className="text-xs text-destructive">{errors.company.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Role</Label>
                <Input placeholder="Software Engineer" className="rounded-xl" {...register('role')} />
                {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Applied date</Label>
                <Input type="date" className="rounded-xl" {...register('applied_at')} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Status</Label>
                <Select value={watchStatus} onValueChange={(v) => setValue('status', v as ApplicationStatus)}>
                  <SelectTrigger className="rounded-xl">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {APPLICATION_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm font-medium">Follow-up date</Label>
              <Input type="date" className="rounded-xl" {...register('follow_up_date')} />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Salary min ($)</Label>
                <Input type="number" placeholder="80000" className="rounded-xl" {...register('salary_min')} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Salary max ($)</Label>
                <Input type="number" placeholder="120000" className="rounded-xl" {...register('salary_max')} />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm font-medium">Notes</Label>
              <Textarea rows={3} placeholder="Any notes about this application…" className="rounded-xl resize-none" {...register('notes')} />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowForm(false)} className="rounded-xl">Cancel</Button>
              <Button
                type="submit"
                disabled={saving}
                className="gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl"
              >
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
