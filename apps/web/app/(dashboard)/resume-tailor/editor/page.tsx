'use client'

import { useState, useEffect, useCallback, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import {
  CvData, CvExperience, CvEducation, CvSkill, CvProject, CvFeaturedProject, CvOtherSection,
  TemplateId, TemplateMeta,
} from '@/lib/types'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Textarea } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import { useToast } from '@jobnok/ui'
import { cn } from '@jobnok/ui'
import {
  ArrowLeft, Download, Loader2, Plus, Trash2, ChevronDown, ChevronUp,
  FileText, User, Briefcase, GraduationCap, Wrench, FolderOpen, BookOpen,
  Languages, AlertTriangle, Star, Lock, Eye, EyeOff, Layers, RotateCcw,
} from 'lucide-react'

// ── Template thumbnails ───────────────────────────────────────────

function SingleColThumb({ accent = '#1a1a1a' }: { accent?: string }) {
  return (
    <div className="w-full h-20 rounded-lg bg-white border border-slate-200 p-2 overflow-hidden space-y-1">
      <div className="h-2 rounded w-3/5 mx-auto" style={{ background: accent }} />
      <div className="h-1 bg-slate-300 rounded w-2/5 mx-auto" />
      <div className="h-px bg-slate-200 w-full mt-1" />
      <div className="h-1 bg-slate-400 rounded w-1/3 mt-1" />
      <div className="space-y-0.5 mt-0.5">
        <div className="h-0.5 bg-slate-200 rounded" />
        <div className="h-0.5 bg-slate-200 rounded w-5/6" />
        <div className="h-0.5 bg-slate-200 rounded w-4/5" />
      </div>
    </div>
  )
}

function TwoColThumb({ sideColor = '#475569', accent = '#1a1a1a' }: { sideColor?: string; accent?: string }) {
  return (
    <div className="w-full h-20 rounded-lg border border-slate-200 overflow-hidden flex">
      <div className="w-[35%] p-1.5 space-y-0.5" style={{ background: sideColor }}>
        <div className="h-2 rounded-full bg-white/30 w-4/5" />
        <div className="h-0.5 bg-white/20 rounded" />
        <div className="h-0.5 bg-white/20 rounded w-3/4" />
        <div className="h-0.5 bg-white/20 rounded w-3/4 mt-1" />
        <div className="h-0.5 bg-white/20 rounded" />
      </div>
      <div className="flex-1 bg-white p-1.5 space-y-0.5">
        <div className="h-1.5 rounded w-3/4 mb-1" style={{ background: accent }} />
        <div className="h-px bg-slate-300" />
        <div className="h-0.5 bg-slate-300 rounded" />
        <div className="h-0.5 bg-slate-300 rounded w-5/6" />
        <div className="h-0.5 bg-slate-300 rounded w-4/5" />
      </div>
    </div>
  )
}

function HeaderBandThumb({ bandColor = '#1e3a5f' }: { bandColor?: string }) {
  return (
    <div className="w-full h-20 rounded-lg border border-slate-200 overflow-hidden">
      <div className="h-6 px-2 flex items-center justify-between" style={{ background: bandColor }}>
        <div className="h-1.5 bg-white/70 rounded w-1/3" />
        <div className="space-y-0.5">
          <div className="h-0.5 bg-white/40 rounded w-10" />
          <div className="h-0.5 bg-white/40 rounded w-8" />
        </div>
      </div>
      <div className="flex" style={{ height: 'calc(100% - 24px)' }}>
        <div className="w-[35%] bg-slate-50 p-1 space-y-0.5 border-r border-slate-200">
          <div className="h-0.5 bg-slate-300 rounded" />
          <div className="h-0.5 bg-slate-200 rounded w-4/5" />
        </div>
        <div className="flex-1 bg-white p-1 space-y-0.5">
          <div className="h-0.5 bg-slate-400 rounded w-1/2" />
          <div className="h-0.5 bg-slate-200 rounded" />
          <div className="h-0.5 bg-slate-200 rounded w-5/6" />
        </div>
      </div>
    </div>
  )
}

const TEMPLATE_THUMBS: Record<TemplateId, React.ReactNode> = {
  standard:             <SingleColThumb />,
  modern:               <TwoColThumb sideColor="#f8f9fa" accent="#343a40" />,
  creative:             <SingleColThumb accent="#e05a2b" />,
  classic:              <SingleColThumb accent="#111" />,
  balanced:             <SingleColThumb accent="#2563eb" />,
  minimalist:           <SingleColThumb accent="#555" />,
  professional:         <SingleColThumb accent="#111" />,
  corporate:            <HeaderBandThumb bandColor="#1e3a5f" />,
  bold:                 <SingleColThumb accent="#1a1a1a" />,
  slate:                <TwoColThumb sideColor="#475569" accent="#475569" />,
  professional_compact: <SingleColThumb accent="#111" />,
  executive:            <TwoColThumb sideColor="#f0f2f5" accent="#2d4a7a" />,
  insight:              <TwoColThumb sideColor="#0f2844" accent="#0f2844" />,
  atelier:              <TwoColThumb sideColor="#faf8f5" accent="#2c1a0e" />,
  elegant:              <SingleColThumb accent="#5a3e2b" />,
  aqua:                 <HeaderBandThumb bandColor="#00897b" />,
  lebenslauf:           <TwoColThumb sideColor="#1b2d4f" accent="#1b2d4f" />,
}

// ── Accordion section ─────────────────────────────────────────────

function Section({ title, icon, children, defaultOpen = true, badge }: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
  badge?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="bg-white rounded-xl border border-slate-100 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
      >
        <span className="text-slate-500">{icon}</span>
        <span className="text-sm font-semibold text-slate-700 flex-1">{title}</span>
        {badge && (
          <span className="text-[10px] font-semibold bg-indigo-100 text-indigo-600 rounded-full px-2 py-0.5 mr-1">{badge}</span>
        )}
        {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>
      {open && <div className="px-4 pb-4 space-y-3 border-t border-slate-100 pt-3">{children}</div>}
    </div>
  )
}

// ── Empty experience template ─────────────────────────────────────

const EMPTY_EXP: CvExperience = {
  title: '', company: '', location: null, period: '', bullets: [''],
}

const EMPTY_EDU: CvEducation = {
  degree: '', institution: '', location: null, period: '', details: null,
}

const EMPTY_PROJ: CvProject = { name: '', tech: null, bullets: [''] }
const EMPTY_OTHER_SECTION: CvOtherSection = { heading: '', bullets: [''] }

// ── Editor inner ──────────────────────────────────────────────────

function EditorInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const { toast } = useToast()

  const [originalPdfUrl, setOriginalPdfUrl] = useState<string | null>(null)
  const [showOriginalPdf, setShowOriginalPdf] = useState(false)
  const [cvData, setCvData] = useState<CvData | null>(null)
  const [templates, setTemplates] = useState<TemplateMeta[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateId>('standard')
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [sessionError, setSessionError] = useState(false)
  const [sessionErrorMessage, setSessionErrorMessage] = useState<string | null>(null)
  const [profileOkForLebenslauf, setProfileOkForLebenslauf] = useState(false)
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [draftSaving, setDraftSaving] = useState(false)
  const [draftSavedAt, setDraftSavedAt] = useState<number | null>(null)
  const previewDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const draftDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Skips the autosave effect's very first fire (the initial load setting
  // cvData for the first time) — otherwise every editor visit immediately
  // PATCHes back the exact data it just fetched.
  const hasLoadedRef = useRef(false)

  // Load session's saved draft (if any) or base_cv_data + tailoring overlay,
  // plus template list + profile check. Pulled into its own callback (not
  // just inline in the effect) so the "Retry" button on a failed load can
  // re-run exactly this without a full navigation — most failures here are
  // a transient upstream AI outage/rate-limit, not a truly missing session,
  // so retrying in place is the right recovery action.
  const loadEditor = useCallback(() => {
    if (!sessionId) { setSessionErrorMessage(null); setSessionError(true); setLoading(false); return }
    setLoading(true)
    setSessionError(false)
    hasLoadedRef.current = false

    const pdfUrl = sessionStorage.getItem(`resume_original_pdf_url:${sessionId}`)
    if (pdfUrl) setOriginalPdfUrl(pdfUrl)

    Promise.all([
      apiFetch(`/api/ai/tailor/${sessionId}/editor`).then(async (r) => {
        if (r.ok) return r.json()
        const body = await r.json().catch(() => null)
        throw new Error(body?.detail || `Couldn't load resume data (HTTP ${r.status}).`)
      }),
      apiFetch('/api/profile').then(r => r.json()).catch(() => ({})),
    ]).then(([editorRes, profile]) => {
      if (editorRes.templates) setTemplates(editorRes.templates)
      if (editorRes.template_id) setSelectedTemplate(editorRes.template_id)
      if (editorRes.cv_data) {
        setCvData(editorRes.cv_data)
        if (editorRes.is_draft) toast({ title: 'Resumed your saved draft' })
      } else {
        throw new Error('Resume data came back empty.')
      }
      const ok = !!(profile?.full_name && profile?.phone &&
        (profile?.address_city || profile?.address_country) && profile?.cv_photo_url)
      setProfileOkForLebenslauf(ok)
    }).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : 'Failed to load resume data.'
      setSessionErrorMessage(message)
      toast({ title: 'Failed to load resume data', description: message, variant: 'destructive' })
      setSessionError(true)
    }).finally(() => {
      setLoading(false)
      hasLoadedRef.current = true
    })
  }, [sessionId, toast])

  useEffect(() => { loadEditor() }, [loadEditor])

  // Debounced autosave of edits — mirrors the live-preview debounce below,
  // but saves to the session's draft_cv_data instead of rendering HTML.
  useEffect(() => {
    if (!cvData || !sessionId || !hasLoadedRef.current) return
    if (draftDebounceRef.current) clearTimeout(draftDebounceRef.current)
    draftDebounceRef.current = setTimeout(async () => {
      setDraftSaving(true)
      try {
        const res = await apiFetch(`/api/ai/tailor/${sessionId}/draft`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cv_data: cvData }),
        })
        if (res.ok) setDraftSavedAt(Date.now())
      } catch { /* silent — autosave, user can still download manually */ }
      finally { setDraftSaving(false) }
    }, 1500)
    return () => {
      if (draftDebounceRef.current) clearTimeout(draftDebounceRef.current)
    }
  }, [cvData, sessionId])

  // Debounced live preview fetch
  useEffect(() => {
    if (!cvData) return
    if (!sessionId) return
    if (previewDebounceRef.current) clearTimeout(previewDebounceRef.current)
    const controller = new AbortController()
    previewDebounceRef.current = setTimeout(async () => {
      setPreviewLoading(true)
      try {
        const res = await apiFetch(`/api/ai/tailor/${sessionId}/preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ template_id: selectedTemplate, cv_data: cvData }),
          signal: controller.signal,
        })
        if (res.ok) {
          const html = await res.text()
          setPreviewHtml(html)
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') { /* silent — user can still download */ }
      } finally {
        if (!controller.signal.aborted) setPreviewLoading(false)
      }
    }, 1500)
    return () => {
      if (previewDebounceRef.current) clearTimeout(previewDebounceRef.current)
      controller.abort()
    }
  }, [cvData, selectedTemplate, sessionId])

  const set = useCallback(<K extends keyof CvData>(key: K, value: CvData[K]) => {
    setCvData(prev => prev ? { ...prev, [key]: value } : prev)
  }, [])

  // ── Experience helpers ──────────────────────────────────────────

  function updateExp(i: number, field: keyof CvExperience, value: string | string[] | null) {
    setCvData(prev => {
      if (!prev) return prev
      const exp = [...prev.experience]
      exp[i] = { ...exp[i], [field]: value }
      return { ...prev, experience: exp }
    })
  }

  function addExp() {
    setCvData(prev => prev ? { ...prev, experience: [...prev.experience, { ...EMPTY_EXP }] } : prev)
  }

  function removeExp(i: number) {
    setCvData(prev => prev ? { ...prev, experience: prev.experience.filter((_, idx) => idx !== i) } : prev)
  }

  function updateExpBullet(expIdx: number, bulletIdx: number, value: string) {
    setCvData(prev => {
      if (!prev) return prev
      const exp = [...prev.experience]
      const bullets = [...exp[expIdx].bullets]
      bullets[bulletIdx] = value
      exp[expIdx] = { ...exp[expIdx], bullets }
      return { ...prev, experience: exp }
    })
  }

  function addExpBullet(expIdx: number) {
    setCvData(prev => {
      if (!prev) return prev
      const exp = [...prev.experience]
      exp[expIdx] = { ...exp[expIdx], bullets: [...exp[expIdx].bullets, ''] }
      return { ...prev, experience: exp }
    })
  }

  function removeExpBullet(expIdx: number, bulletIdx: number) {
    setCvData(prev => {
      if (!prev) return prev
      const exp = [...prev.experience]
      exp[expIdx] = { ...exp[expIdx], bullets: exp[expIdx].bullets.filter((_, i) => i !== bulletIdx) }
      return { ...prev, experience: exp }
    })
  }

  // ── Education helpers ───────────────────────────────────────────

  function updateEdu(i: number, field: keyof CvEducation, value: string | null) {
    setCvData(prev => {
      if (!prev) return prev
      const education = [...prev.education]
      education[i] = { ...education[i], [field]: value }
      return { ...prev, education }
    })
  }

  function addEdu() {
    setCvData(prev => prev ? { ...prev, education: [...prev.education, { ...EMPTY_EDU }] } : prev)
  }

  function removeEdu(i: number) {
    setCvData(prev => prev ? { ...prev, education: prev.education.filter((_, idx) => idx !== i) } : prev)
  }

  // ── Skills helpers ──────────────────────────────────────────────

  function updateSkill(i: number, field: keyof CvSkill, value: string) {
    setCvData(prev => {
      if (!prev) return prev
      const skills = [...prev.skills]
      skills[i] = { ...skills[i], [field]: value }
      return { ...prev, skills }
    })
  }

  function addSkill() {
    setCvData(prev => prev ? { ...prev, skills: [...prev.skills, { category: '', items: '' }] } : prev)
  }

  function removeSkill(i: number) {
    setCvData(prev => prev ? { ...prev, skills: prev.skills.filter((_, idx) => idx !== i) } : prev)
  }

  // ── Project helpers ─────────────────────────────────────────────

  function updateProject(i: number, field: keyof CvProject, value: string | string[] | null) {
    setCvData(prev => {
      if (!prev) return prev
      const projects = [...prev.projects]
      projects[i] = { ...projects[i], [field]: value }
      return { ...prev, projects }
    })
  }

  function addProject() {
    setCvData(prev => prev ? { ...prev, projects: [...prev.projects, { ...EMPTY_PROJ }] } : prev)
  }

  function removeProject(i: number) {
    setCvData(prev => prev ? { ...prev, projects: prev.projects.filter((_, idx) => idx !== i) } : prev)
  }

  // ── Other-section helpers ────────────────────────────────────────
  // Catch-all for resume sections that don't fit any fixed category
  // (Volunteering, Patents, Awards, ...) — see CvOtherSection.

  function updateOtherSection(i: number, field: keyof CvOtherSection, value: string | string[]) {
    setCvData(prev => {
      if (!prev) return prev
      const sections = [...(prev.other_sections || [])]
      sections[i] = { ...sections[i], [field]: value }
      return { ...prev, other_sections: sections }
    })
  }

  function addOtherSection() {
    setCvData(prev => prev ? { ...prev, other_sections: [...(prev.other_sections || []), { ...EMPTY_OTHER_SECTION }] } : prev)
  }

  function removeOtherSection(i: number) {
    setCvData(prev => prev ? { ...prev, other_sections: (prev.other_sections || []).filter((_, idx) => idx !== i) } : prev)
  }

  // ── Featured project helpers ────────────────────────────────────

  function updateFeatured<K extends keyof CvFeaturedProject>(field: K, value: CvFeaturedProject[K]) {
    setCvData(prev => {
      if (!prev) return prev
      const fp = prev.featured_project ?? { name: '', year: null, tech: null, bullets: [], results: null }
      return { ...prev, featured_project: { ...fp, [field]: value } }
    })
  }

  function updateFeaturedBullet(bulletIdx: number, value: string) {
    setCvData(prev => {
      if (!prev?.featured_project) return prev
      const bullets = [...prev.featured_project.bullets]
      bullets[bulletIdx] = value
      return { ...prev, featured_project: { ...prev.featured_project, bullets } }
    })
  }

  function addFeaturedBullet() {
    setCvData(prev => {
      if (!prev) return prev
      const fp = prev.featured_project ?? { name: '', year: null, tech: null, bullets: [], results: null }
      return { ...prev, featured_project: { ...fp, bullets: [...fp.bullets, ''] } }
    })
  }

  function removeFeaturedBullet(bulletIdx: number) {
    setCvData(prev => {
      if (!prev?.featured_project) return prev
      return {
        ...prev,
        featured_project: {
          ...prev.featured_project,
          bullets: prev.featured_project.bullets.filter((_, i) => i !== bulletIdx),
        },
      }
    })
  }

  // ── Template selection with lebenslauf guard ────────────────────

  function selectTemplate(id: TemplateId) {
    if (id === 'lebenslauf' && !profileOkForLebenslauf) {
      toast({
        title: 'Profile incomplete',
        description: 'Lebenslauf requires a photo, phone, and city. Complete your profile first.',
        variant: 'destructive',
      })
      return
    }
    setSelectedTemplate(id)
  }

  // ── Download ────────────────────────────────────────────────────

  async function handleDownload() {
    if (!cvData || !sessionId) return
    setGenerating(true)
    try {
      const res = await apiFetch(`/api/ai/tailor/${sessionId}/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: selectedTemplate, cv_data: cvData }),
      })
      if (!res.ok) {
        const json = await res.json()
        toast({ title: json.detail || 'Generation failed', variant: 'destructive' })
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `tailored_cv_${selectedTemplate}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      toast({ title: 'PDF downloaded!' })
    } catch {
      toast({ title: 'Network error', variant: 'destructive' })
    } finally {
      setGenerating(false)
    }
  }

  // ── Empty / loading states ──────────────────────────────────────

  if (sessionError) {
    const noSession = !sessionId
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <AlertTriangle className="h-10 w-10 text-amber-400" />
        <p className="font-semibold text-slate-700">{noSession ? 'Session expired' : 'Could not load your resume'}</p>
        <p className="text-sm text-slate-500 max-w-sm text-center">
          {noSession
            ? 'Run a new analysis to open the editor.'
            : (sessionErrorMessage || 'Something went wrong loading this session.')}
        </p>
        <div className="flex gap-3">
          {!noSession && (
            <Button onClick={loadEditor} className="rounded-xl gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90">
              <RotateCcw className="h-4 w-4 mr-2" /> Retry
            </Button>
          )}
          <Button onClick={() => router.push('/resume-tailor')} variant="outline" className="rounded-xl">
            <ArrowLeft className="h-4 w-4 mr-2" /> Back to Resume Tailor
          </Button>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <Loader2 className="h-10 w-10 animate-spin text-indigo-500" />
        <p className="font-semibold text-slate-700">Structuring your resume…</p>
        <p className="text-sm text-slate-400">This takes about 10–20 seconds</p>
      </div>
    )
  }

  if (!cvData) return null

  const fp = cvData.featured_project

  return (
    <div className="animate-fade-in">
      {/* Top bar */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => router.push('/resume-tailor')}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors shrink-0"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <div className="flex items-center gap-2 mx-auto">
          <div className="page-header-icon bg-indigo-100">
            <FileText className="h-5 w-5 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Resume Editor</h1>
            <p className="text-slate-500 text-xs mt-0.5 flex items-center gap-1.5">
              Edit content · pick layout · download PDF
              {draftSaving && <span className="text-slate-400">· Saving…</span>}
              {!draftSaving && draftSavedAt && <span className="text-emerald-500">· Saved</span>}
            </p>
          </div>
        </div>
        <Button
          onClick={handleDownload}
          disabled={generating}
          className="h-10 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 rounded-xl font-semibold text-sm px-5 shrink-0"
        >
          {generating
            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
            : <><Download className="h-4 w-4 mr-2" /> Download PDF</>
          }
        </Button>
      </div>

      <div className="grid grid-cols-[440px_1fr] gap-6 items-start">

        {/* ── LEFT: Scrollable form ── */}
        <div className="space-y-3 overflow-y-auto pr-1" style={{ maxHeight: 'calc(100vh - 140px)' }}>

          {/* Personal Info */}
          <Section title="Personal Info" icon={<User className="h-4 w-4" />}>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Label className="text-xs text-slate-500 mb-1 block">Full Name</Label>
                <Input value={cvData.full_name} onChange={e => set('full_name', e.target.value)} className="h-8 text-sm rounded-lg" />
              </div>
              <div className="col-span-2">
                <Label className="text-xs text-slate-500 mb-1 block">Headline / Job Title</Label>
                <Input value={cvData.job_title} onChange={e => set('job_title', e.target.value)} className="h-8 text-sm rounded-lg" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Email</Label>
                <Input value={cvData.email} onChange={e => set('email', e.target.value)} className="h-8 text-sm rounded-lg" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Phone</Label>
                <Input value={cvData.phone ?? ''} onChange={e => set('phone', e.target.value || null)} className="h-8 text-sm rounded-lg" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Location</Label>
                <Input value={cvData.location} onChange={e => set('location', e.target.value)} className="h-8 text-sm rounded-lg" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Work Auth</Label>
                <Input value={cvData.work_authorization ?? ''} onChange={e => set('work_authorization', e.target.value || null)} className="h-8 text-sm rounded-lg" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">LinkedIn</Label>
                <Input value={cvData.linkedin ?? ''} onChange={e => set('linkedin', e.target.value || null)} className="h-8 text-sm rounded-lg" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">GitHub</Label>
                <Input value={cvData.github ?? ''} onChange={e => set('github', e.target.value || null)} className="h-8 text-sm rounded-lg" />
              </div>
              <div className="col-span-2">
                <Label className="text-xs text-slate-500 mb-1 block">Website</Label>
                <Input value={cvData.website ?? ''} onChange={e => set('website', e.target.value || null)} className="h-8 text-sm rounded-lg" />
              </div>
            </div>
          </Section>

          {/* Summary */}
          <Section title="Professional Summary" icon={<FileText className="h-4 w-4" />}>
            <Textarea
              value={cvData.summary}
              onChange={e => set('summary', e.target.value)}
              rows={5}
              className="text-sm rounded-lg border-slate-200 resize-none"
            />
          </Section>

          {/* Featured Project */}
          <Section
            title="Featured Project"
            icon={<Star className="h-4 w-4" />}
            defaultOpen={!!fp?.name}
            badge={fp?.name ? '1' : undefined}
          >
            {!fp?.name && !fp && (
              <Button
                variant="outline"
                size="sm"
                className="w-full rounded-lg border-dashed text-slate-500 text-xs"
                onClick={() => set('featured_project', { name: '', year: null, tech: null, bullets: [''], results: null })}
              >
                <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Featured Project
              </Button>
            )}
            {fp !== null && fp !== undefined && (
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-slate-500">Project</Label>
                  <button
                    onClick={() => set('featured_project', null)}
                    className="text-[10px] text-red-400 hover:text-red-600 flex items-center gap-0.5"
                  >
                    <Trash2 className="h-3 w-3" /> Remove
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <Label className="text-xs text-slate-500 mb-1 block">Name</Label>
                    <Input value={fp.name} onChange={e => updateFeatured('name', e.target.value)} className="h-8 text-sm rounded-lg" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Year</Label>
                    <Input value={fp.year ?? ''} onChange={e => updateFeatured('year', e.target.value || null)} className="h-8 text-sm rounded-lg" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Tech stack</Label>
                    <Input value={fp.tech ?? ''} onChange={e => updateFeatured('tech', e.target.value || null)} className="h-8 text-sm rounded-lg" />
                  </div>
                  <div className="col-span-2">
                    <Label className="text-xs text-slate-500 mb-1 block">Key result / impact</Label>
                    <Input value={fp.results ?? ''} onChange={e => updateFeatured('results', e.target.value || null)} className="h-8 text-sm rounded-lg" />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <Label className="text-xs text-slate-500">Bullets</Label>
                    <button onClick={addFeaturedBullet} className="text-[10px] text-indigo-500 hover:text-indigo-700 font-medium flex items-center gap-0.5">
                      <Plus className="h-3 w-3" /> Add
                    </button>
                  </div>
                  <div className="space-y-1.5">
                    {fp.bullets.map((b, bi) => (
                      <div key={bi} className="flex gap-1.5">
                        <Textarea
                          value={b}
                          onChange={e => updateFeaturedBullet(bi, e.target.value)}
                          rows={2}
                          className="text-xs rounded-lg border-slate-200 resize-none flex-1"
                        />
                        <button onClick={() => removeFeaturedBullet(bi)} className="text-slate-300 hover:text-red-400 mt-1 shrink-0">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </Section>

          {/* Experience */}
          <Section
            title="Experience"
            icon={<Briefcase className="h-4 w-4" />}
            badge={String(cvData.experience.length)}
          >
            <div className="space-y-3">
              {cvData.experience.map((exp, i) => (
                <div key={i} className="border border-slate-100 rounded-xl p-3 space-y-2.5 bg-slate-50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-slate-500">Entry {i + 1}</span>
                    <button
                      onClick={() => removeExp(i)}
                      className="text-slate-300 hover:text-red-400 flex items-center gap-0.5 text-[10px]"
                    >
                      <Trash2 className="h-3 w-3" /> Remove
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="col-span-2">
                      <Label className="text-xs text-slate-500 mb-1 block">Job Title</Label>
                      <Input value={exp.title} onChange={e => updateExp(i, 'title', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                    <div>
                      <Label className="text-xs text-slate-500 mb-1 block">Company</Label>
                      <Input value={exp.company} onChange={e => updateExp(i, 'company', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                    <div>
                      <Label className="text-xs text-slate-500 mb-1 block">Period</Label>
                      <Input value={exp.period} onChange={e => updateExp(i, 'period', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                    <div className="col-span-2">
                      <Label className="text-xs text-slate-500 mb-1 block">Location</Label>
                      <Input value={exp.location ?? ''} onChange={e => updateExp(i, 'location', e.target.value || null)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <Label className="text-xs text-slate-500">Bullets</Label>
                      <button onClick={() => addExpBullet(i)} className="text-[10px] text-indigo-500 hover:text-indigo-700 font-medium flex items-center gap-0.5">
                        <Plus className="h-3 w-3" /> Add
                      </button>
                    </div>
                    <div className="space-y-1.5">
                      {exp.bullets.map((b, bi) => (
                        <div key={bi} className="flex gap-1.5">
                          <Textarea
                            value={b}
                            onChange={e => updateExpBullet(i, bi, e.target.value)}
                            rows={2}
                            className="text-xs rounded-lg border-slate-200 resize-none flex-1 bg-white"
                          />
                          <button onClick={() => removeExpBullet(i, bi)} className="text-slate-300 hover:text-red-400 mt-1 shrink-0">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full rounded-lg border-dashed text-slate-500 text-xs mt-1"
              onClick={addExp}
            >
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Experience Entry
            </Button>
          </Section>

          {/* Education */}
          <Section
            title="Education"
            icon={<GraduationCap className="h-4 w-4" />}
            badge={String(cvData.education.length)}
            defaultOpen={false}
          >
            <div className="space-y-3">
              {cvData.education.map((edu, i) => (
                <div key={i} className="border border-slate-100 rounded-xl p-3 space-y-2 bg-slate-50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-slate-500">Entry {i + 1}</span>
                    <button onClick={() => removeEdu(i)} className="text-slate-300 hover:text-red-400 flex items-center gap-0.5 text-[10px]">
                      <Trash2 className="h-3 w-3" /> Remove
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="col-span-2">
                      <Label className="text-xs text-slate-500 mb-1 block">Degree</Label>
                      <Input value={edu.degree} onChange={e => updateEdu(i, 'degree', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                    <div>
                      <Label className="text-xs text-slate-500 mb-1 block">Institution</Label>
                      <Input value={edu.institution} onChange={e => updateEdu(i, 'institution', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                    <div>
                      <Label className="text-xs text-slate-500 mb-1 block">Period</Label>
                      <Input value={edu.period} onChange={e => updateEdu(i, 'period', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                    <div className="col-span-2">
                      <Label className="text-xs text-slate-500 mb-1 block">Details (GPA, honours, etc.)</Label>
                      <Input value={edu.details ?? ''} onChange={e => updateEdu(i, 'details', e.target.value || null)} className="h-8 text-sm rounded-lg bg-white" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full rounded-lg border-dashed text-slate-500 text-xs mt-1"
              onClick={addEdu}
            >
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Education Entry
            </Button>
          </Section>

          {/* Skills */}
          <Section
            title="Skills"
            icon={<Wrench className="h-4 w-4" />}
            badge={`${cvData.skills.length} categories`}
            defaultOpen={false}
          >
            <div className="space-y-2">
              {cvData.skills.map((skill, i) => (
                <div key={i} className="border border-slate-100 rounded-xl p-3 space-y-2 bg-slate-50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-slate-500 font-medium">{skill.category || `Category ${i + 1}`}</span>
                    <button onClick={() => removeSkill(i)} className="text-slate-300 hover:text-red-400">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Category name</Label>
                    <Input value={skill.category} onChange={e => updateSkill(i, 'category', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Items (comma-separated)</Label>
                    <Input value={skill.items} onChange={e => updateSkill(i, 'items', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                  </div>
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full rounded-lg border-dashed text-slate-500 text-xs mt-1"
              onClick={addSkill}
            >
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Skill Category
            </Button>
          </Section>

          {/* Projects */}
          <Section
            title="Projects"
            icon={<FolderOpen className="h-4 w-4" />}
            badge={cvData.projects.length > 0 ? String(cvData.projects.length) : undefined}
            defaultOpen={false}
          >
            <div className="space-y-3">
              {cvData.projects.map((proj, i) => (
                <div key={i} className="border border-slate-100 rounded-xl p-3 space-y-2 bg-slate-50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-slate-500">{proj.name || `Project ${i + 1}`}</span>
                    <button onClick={() => removeProject(i)} className="text-slate-300 hover:text-red-400 flex items-center gap-0.5 text-[10px]">
                      <Trash2 className="h-3 w-3" /> Remove
                    </button>
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Name</Label>
                    <Input value={proj.name} onChange={e => updateProject(i, 'name', e.target.value)} className="h-8 text-sm rounded-lg bg-white" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Tech stack</Label>
                    <Input value={proj.tech ?? ''} onChange={e => updateProject(i, 'tech', e.target.value || null)} className="h-8 text-sm rounded-lg bg-white" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Bullets (one per line)</Label>
                    <Textarea
                      value={proj.bullets.join('\n')}
                      onChange={e => updateProject(i, 'bullets', e.target.value.split('\n'))}
                      rows={3}
                      className="text-xs rounded-lg border-slate-200 resize-none bg-white"
                    />
                  </div>
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full rounded-lg border-dashed text-slate-500 text-xs mt-1"
              onClick={addProject}
            >
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Project
            </Button>
          </Section>

          {/* Publications */}
          {cvData.publications.length > 0 && (
            <Section
              title="Publications"
              icon={<BookOpen className="h-4 w-4" />}
              badge={String(cvData.publications.length)}
              defaultOpen={false}
            >
              {cvData.publications.map((pub, i) => (
                <div key={i} className="border border-slate-100 rounded-xl p-3 space-y-2 bg-slate-50">
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Title</Label>
                    <Input value={pub.title} onChange={e => {
                      const pubs = [...cvData.publications]
                      pubs[i] = { ...pubs[i], title: e.target.value }
                      set('publications', pubs)
                    }} className="h-8 text-sm rounded-lg bg-white" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Venue</Label>
                    <Input value={pub.venue} onChange={e => {
                      const pubs = [...cvData.publications]
                      pubs[i] = { ...pubs[i], venue: e.target.value }
                      set('publications', pubs)
                    }} className="h-8 text-sm rounded-lg bg-white" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Year</Label>
                    <Input value={pub.year ?? ''} onChange={e => {
                      const pubs = [...cvData.publications]
                      pubs[i] = { ...pubs[i], year: e.target.value || null }
                      set('publications', pubs)
                    }} className="h-8 text-sm rounded-lg bg-white" />
                  </div>
                </div>
              ))}
            </Section>
          )}

          {/* Languages */}
          <Section title="Languages" icon={<Languages className="h-4 w-4" />} defaultOpen={false}>
            <Label className="text-xs text-slate-500 mb-1 block">One per line</Label>
            <Textarea
              value={cvData.languages.join('\n')}
              onChange={e => set('languages', e.target.value.split('\n').filter(Boolean))}
              rows={3}
              className="text-sm rounded-lg border-slate-200 resize-none"
            />
          </Section>

          {/* Other Sections — catch-all for anything that doesn't fit a fixed
              category above (Volunteering, Patents, Awards, ...). Rendered
              only in the "standard" template today; other layouts pass the
              data through without displaying it yet. */}
          <Section
            title="Other Sections"
            icon={<Layers className="h-4 w-4" />}
            badge={(cvData.other_sections || []).length > 0 ? String(cvData.other_sections.length) : undefined}
            defaultOpen={false}
          >
            <div className="space-y-3">
              {(cvData.other_sections || []).map((section, i) => (
                <div key={i} className="border border-slate-100 rounded-xl p-3 space-y-2 bg-slate-50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-slate-500">{section.heading || `Section ${i + 1}`}</span>
                    <button onClick={() => removeOtherSection(i)} className="text-slate-300 hover:text-red-400 flex items-center gap-0.5 text-[10px]">
                      <Trash2 className="h-3 w-3" /> Remove
                    </button>
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Heading</Label>
                    <Input
                      value={section.heading}
                      onChange={e => updateOtherSection(i, 'heading', e.target.value)}
                      placeholder="e.g. Volunteering, Patents, Awards"
                      className="h-8 text-sm rounded-lg bg-white"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500 mb-1 block">Bullets (one per line)</Label>
                    <Textarea
                      value={section.bullets.join('\n')}
                      onChange={e => updateOtherSection(i, 'bullets', e.target.value.split('\n'))}
                      rows={3}
                      className="text-xs rounded-lg border-slate-200 resize-none bg-white"
                    />
                  </div>
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full rounded-lg border-dashed text-slate-500 text-xs mt-1"
              onClick={addOtherSection}
            >
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Section
            </Button>
          </Section>

        </div>

        {/* ── RIGHT: Live preview + template picker ── */}
        <div className="space-y-4 sticky top-4" style={{ maxHeight: 'calc(100vh - 140px)', overflowY: 'auto' }}>

          {/* Live preview */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2">
              <Eye className="h-4 w-4 text-slate-400" />
              <span className="text-xs font-semibold text-slate-600 flex-1">Live Preview</span>
              {previewLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />}
              {originalPdfUrl && (
                <button
                  onClick={() => setShowOriginalPdf(v => !v)}
                  className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-600 transition-colors"
                  title="Toggle original PDF reference"
                >
                  {showOriginalPdf ? <EyeOff className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                  {showOriginalPdf ? 'Hide original' : 'Original PDF'}
                </button>
              )}
            </div>
            {previewHtml ? (
              <iframe
                srcDoc={previewHtml}
                className="w-full border-0"
                style={{ height: '680px' }}
                title="Resume live preview"
                sandbox=""
              />
            ) : (
              <div className="flex flex-col items-center justify-center gap-2 text-slate-400" style={{ height: '680px' }}>
                {previewLoading
                  ? <><Loader2 className="h-6 w-6 animate-spin text-indigo-400" /><span className="text-xs">Rendering preview…</span></>
                  : <><Eye className="h-6 w-6" /><span className="text-xs">Preview will appear here</span></>
                }
              </div>
            )}
          </div>

          {/* Original PDF (collapsible reference) */}
          {originalPdfUrl && showOriginalPdf && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
              <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2">
                <FileText className="h-4 w-4 text-slate-400" />
                <span className="text-xs font-semibold text-slate-600">Original Resume (reference)</span>
              </div>
              <iframe
                src={originalPdfUrl}
                className="w-full"
                style={{ height: '300px' }}
                title="Original resume PDF"
              />
            </div>
          )}

          {/* Template picker */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-4">
            <p className="text-sm font-semibold text-slate-700 mb-3">Select Layout</p>

            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">Single Column</p>
            <div className="grid grid-cols-3 gap-2 mb-4">
              {templates.filter(t => t.columns === 1).map(t => (
                <button
                  key={t.id}
                  onClick={() => selectTemplate(t.id as TemplateId)}
                  title={t.desc}
                  className={cn(
                    'text-left rounded-xl border-2 p-2 transition-all',
                    selectedTemplate === t.id ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-slate-300'
                  )}
                >
                  {TEMPLATE_THUMBS[t.id as TemplateId]}
                  <p className="text-[10px] font-semibold text-slate-700 mt-1.5 leading-tight">{t.label}</p>
                  <p className="text-[9px] text-slate-400 mt-0.5 truncate">{t.font.split(',')[0]}</p>
                </button>
              ))}
            </div>

            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">Two Column</p>
            <div className="grid grid-cols-3 gap-2">
              {templates.filter(t => t.columns === 2).map(t => {
                const locked = t.id === 'lebenslauf' && !profileOkForLebenslauf
                return (
                  <button
                    key={t.id}
                    onClick={() => selectTemplate(t.id as TemplateId)}
                    title={locked ? 'Requires profile photo, phone and city' : t.desc}
                    className={cn(
                      'text-left rounded-xl border-2 p-2 transition-all relative',
                      selectedTemplate === t.id ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-slate-300',
                      locked && 'opacity-60'
                    )}
                  >
                    {TEMPLATE_THUMBS[t.id as TemplateId]}
                    <p className="text-[10px] font-semibold text-slate-700 mt-1.5 leading-tight">{t.label}</p>
                    <p className="text-[9px] text-slate-400 mt-0.5 truncate">{t.font.split(',')[0]}</p>
                    {locked && (
                      <div className="absolute top-1.5 right-1.5 bg-amber-100 text-amber-700 rounded px-1 py-0.5 flex items-center gap-0.5">
                        <Lock className="h-2.5 w-2.5" />
                        <span className="text-[8px] font-semibold">Photo req.</span>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Download CTA */}
          <Button
            onClick={handleDownload}
            disabled={generating}
            className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 rounded-xl font-semibold"
          >
            {generating
              ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating PDF…</>
              : <><Download className="h-4 w-4 mr-2" /> Download {templates.find(t => t.id === selectedTemplate)?.label ?? selectedTemplate} PDF</>
            }
          </Button>
        </div>

      </div>
    </div>
  )
}

export default function ResumeEditorPage() {
  return (
    <Suspense>
      <EditorInner />
    </Suspense>
  )
}
