'use client'

import { useState, useEffect, useRef } from 'react'
import { useUser } from '@clerk/nextjs'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { User, Camera, Save, Loader2, CheckCircle, KeyRound } from 'lucide-react'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import { useToast } from '@jobnok/ui'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { UserProfile } from '@/lib/types'

export default function ProfilePage() {
  const queryClient = useQueryClient()
  const { data: serverProfile, isLoading: loading, isError: loadError } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: () => apiGet<UserProfile>('/api/profile'),
  })
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const hasSyncedRef = useRef(false)
  const [saving, setSaving] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [showPasswordForm, setShowPasswordForm] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()
  const { user } = useUser()

  useEffect(() => {
    if (serverProfile && !hasSyncedRef.current) {
      hasSyncedRef.current = true
      setProfile(serverProfile)
      if (serverProfile.cv_photo_url) setPhotoPreview(serverProfile.cv_photo_url)
    }
  }, [serverProfile])

  useEffect(() => {
    if (loadError) toast({ title: 'Could not load profile', variant: 'destructive' })
  }, [loadError, toast])

  function handleField(field: keyof UserProfile, value: string) {
    setProfile(prev => prev ? { ...prev, [field]: value } : prev)
  }

  async function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      toast({ title: 'JPEG, PNG, or WebP only', variant: 'destructive' })
      return
    }
    setPhotoPreview(URL.createObjectURL(file))
    setUploadingPhoto(true)
    const form = new FormData()
    form.append('photo', file)
    try {
      const res = await apiFetch('/api/profile/photo', { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setProfile(prev => prev ? { ...prev, cv_photo_url: data.cv_photo_url } : prev)
      queryClient.setQueryData<UserProfile>(queryKeys.profile, (prev) => prev ? { ...prev, cv_photo_url: data.cv_photo_url } : prev)
      toast({ title: 'Photo uploaded!' })
    } catch (err) {
      toast({ title: 'Photo upload failed', description: err instanceof Error ? err.message : undefined, variant: 'destructive' })
    } finally {
      setUploadingPhoto(false)
    }
  }

  async function changePassword() {
    if (!user || !newPassword) return
    setChangingPassword(true)
    try {
      await user.updatePassword({
        newPassword,
        currentPassword: currentPassword || undefined,
      })
      toast({ title: 'Password updated' })
      setShowPasswordForm(false)
      setCurrentPassword('')
      setNewPassword('')
    } catch (err: any) {
      toast({ title: 'Could not update password', description: err?.errors?.[0]?.message, variant: 'destructive' })
    }
    setChangingPassword(false)
  }

  async function save() {
    if (!profile) return
    setSaving(true)
    try {
      const payload = {
        full_name: profile.full_name,
        job_title: profile.job_title,
        cv_email: profile.cv_email ?? profile.email,
        phone: profile.phone,
        address_street: profile.address_street,
        address_city: profile.address_city,
        address_postal_code: profile.address_postal_code,
        address_country: profile.address_country,
        date_of_birth: profile.date_of_birth,
        nationality: profile.nationality,
        linkedin_url: profile.linkedin_url,
        github_url: profile.github_url,
        website_url: profile.website_url,
        work_authorization: profile.work_authorization,
      }
      const res = await apiFetch('/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error()
      queryClient.setQueryData<UserProfile>(queryKeys.profile, (prev) => prev ? { ...prev, ...payload } : prev)
      setSaved(true)
      toast({ title: 'Profile saved!' })
      setTimeout(() => setSaved(false), 3000)
    } catch {
      toast({ title: 'Save failed', variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  const classicReady = !!(
    profile?.full_name && profile?.phone &&
    (profile?.address_city || profile?.address_country) &&
    profile?.cv_photo_url
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-slate-100">
          <User className="h-5 w-5 text-slate-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Profile</h1>
          <p className="text-slate-500 text-sm mt-0.5">Personal details used in generated CV templates</p>
        </div>
      </div>

      {/* Classic template readiness banner */}
      <div className={`flex items-center gap-3 rounded-xl px-4 py-3 mb-6 text-sm border ${
        classicReady
          ? 'bg-emerald-50 border-emerald-100 text-emerald-800'
          : 'bg-amber-50 border-amber-100 text-amber-800'
      }`}>
        {classicReady
          ? <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />
          : <Camera className="h-4 w-4 text-amber-500 flex-shrink-0" />
        }
        {classicReady
          ? 'Profile complete — Classic 2-column template is unlocked.'
          : `Complete the following to unlock the Classic template: ${[
              !profile?.cv_photo_url && 'profile photo',
              !profile?.full_name && 'full name',
              !profile?.phone && 'phone',
              !(profile?.address_city || profile?.address_country) && 'city / country',
            ].filter(Boolean).join(', ')}.`
        }
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Photo column */}
        <div className="col-span-1">
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-6 flex flex-col items-center gap-4">
            <div
              onClick={() => fileRef.current?.click()}
              className="relative w-32 h-32 rounded-full cursor-pointer group"
            >
              {photoPreview ? (
                <img src={photoPreview} alt="Profile" className="w-32 h-32 rounded-full object-cover border-4 border-indigo-100" />
              ) : (
                <div className="w-32 h-32 rounded-full bg-slate-100 border-4 border-dashed border-slate-200 flex items-center justify-center">
                  <User className="h-10 w-10 text-slate-300" />
                </div>
              )}
              <div className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                {uploadingPhoto
                  ? <Loader2 className="h-6 w-6 text-white animate-spin" />
                  : <Camera className="h-6 w-6 text-white" />
                }
              </div>
            </div>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handlePhotoChange} />
            <div className="text-center">
              <p className="text-sm font-semibold text-slate-700">CV Photo</p>
              <p className="text-xs text-slate-400 mt-1">Used in Classic 2-column template</p>
              <p className="text-xs text-slate-400">JPEG, PNG or WebP · max 5 MB</p>
            </div>
          </div>
        </div>

        {/* Fields column */}
        <div className="col-span-2 space-y-4">
          {/* Basic info */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Basic Information</p>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Full Name" value={profile?.full_name || ''} onChange={v => handleField('full_name', v)} placeholder="Sankar Dev Santhosh" />
              <Field label="Professional Title / Tagline" value={profile?.job_title || ''} onChange={v => handleField('job_title', v)} placeholder="Applied AI Engineer · NLP · RAG" />
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-700">CV Email</Label>
                <Input
                  value={profile?.cv_email ?? profile?.email ?? ''}
                  onChange={e => handleField('cv_email', e.target.value)}
                  placeholder={profile?.email || 's4nkar.connect@gmail.com'}
                  className="rounded-xl border-slate-200"
                />
                <p className="text-[11px] text-slate-400">Shown on your CV — can differ from your login email ({profile?.email})</p>
              </div>
              <Field label="Phone" value={profile?.phone || ''} onChange={v => handleField('phone', v)} placeholder="+44 7460 054747" />
              <Field label="Date of Birth" value={profile?.date_of_birth || ''} onChange={v => handleField('date_of_birth', v)} placeholder="1999-06-15" type="date" />
              <Field label="Nationality" value={profile?.nationality || ''} onChange={v => handleField('nationality', v)} placeholder="Indian" />
              <Field label="Work Authorization" value={profile?.work_authorization || ''} onChange={v => handleField('work_authorization', v)} placeholder="Eligible to work in Germany" className="col-span-2" />
            </div>
          </div>

          {/* Address */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Address</p>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Street" value={profile?.address_street || ''} onChange={v => handleField('address_street', v)} placeholder="221B Baker Street" className="col-span-2" />
              <Field label="City" value={profile?.address_city || ''} onChange={v => handleField('address_city', v)} placeholder="London" />
              <Field label="Postal Code" value={profile?.address_postal_code || ''} onChange={v => handleField('address_postal_code', v)} placeholder="NW1 6XE" />
              <Field label="Country" value={profile?.address_country || ''} onChange={v => handleField('address_country', v)} placeholder="United Kingdom" className="col-span-2" />
            </div>
          </div>

          {/* Online presence */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Online Presence</p>
            <div className="grid grid-cols-2 gap-4">
              <Field label="LinkedIn URL" value={profile?.linkedin_url || ''} onChange={v => handleField('linkedin_url', v)} placeholder="linkedin.com/in/s4nkar" />
              <Field label="GitHub URL" value={profile?.github_url || ''} onChange={v => handleField('github_url', v)} placeholder="github.com/s4nkar" />
              <Field label="Website / Portfolio" value={profile?.website_url || ''} onChange={v => handleField('website_url', v)} placeholder="s4nkar.online" className="col-span-2" />
            </div>
          </div>

          <Button
            onClick={save}
            disabled={saving}
            className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
          >
            {saving
              ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving…</>
              : saved
                ? <><CheckCircle className="h-4 w-4 mr-2" /> Saved!</>
                : <><Save className="h-4 w-4 mr-2" /> Save Profile</>
            }
          </Button>

          {/* Change password */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                  <KeyRound className="h-4 w-4 text-slate-400" />
                  Change Password
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Update the password for your login email
                </p>
              </div>
              {!showPasswordForm && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowPasswordForm(true)}
                  className="rounded-xl text-xs shrink-0"
                >
                  Change password
                </Button>
              )}
            </div>

            {showPasswordForm && (
              <div className="mt-4 space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-slate-600">Current password</Label>
                  <Input
                    type="password"
                    value={currentPassword}
                    onChange={e => setCurrentPassword(e.target.value)}
                    className="h-9 text-sm rounded-xl border-slate-200"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-slate-600">New password</Label>
                  <Input
                    type="password"
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    className="h-9 text-sm rounded-xl border-slate-200"
                    onKeyDown={e => e.key === 'Enter' && changePassword()}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={changePassword}
                    disabled={changingPassword || !newPassword}
                    className="rounded-xl text-xs gradient-brand text-white border-0"
                  >
                    {changingPassword
                      ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                      : <CheckCircle className="h-3.5 w-3.5 mr-1" />
                    }
                    Update password
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => { setShowPasswordForm(false); setCurrentPassword(''); setNewPassword('') }}
                    className="rounded-xl text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Field({
  label, value, onChange, placeholder, disabled, type = 'text', className = '',
}: {
  label: string; value: string; onChange?: (v: string) => void
  placeholder: string; disabled?: boolean; type?: string; className?: string
}) {
  return (
    <div className={`space-y-1.5 ${className}`}>
      <Label className="text-sm font-medium text-slate-700">{label}</Label>
      <Input
        type={type}
        value={value}
        onChange={e => onChange?.(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="rounded-xl border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
      />
    </div>
  )
}
