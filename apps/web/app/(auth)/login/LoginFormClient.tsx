'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2, CheckCircle, ArrowLeft } from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'

const schema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
})

type FormData = z.infer<typeof schema>

export default function LoginFormClient() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const redirect = searchParams.get('redirect') || '/templates'

  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [oauthLoading, setOauthLoading] = useState<string | null>(null)
  const [showForgot, setShowForgot] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotSent, setForgotSent] = useState(false)

  const { register, handleSubmit, getValues, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  const supabase = createClient()

  async function onSubmit(data: FormData) {
    setLoading(true)
    const { error } = await supabase.auth.signInWithPassword(data)
    if (error) {
      toast({ title: 'Login failed', description: error.message, variant: 'destructive' })
    } else {
      router.push(redirect)
      router.refresh()
    }
    setLoading(false)
  }

  async function signInWithOAuth(provider: 'google' | 'github') {
    setOauthLoading(provider)
    await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/api/auth/callback?redirect=${encodeURIComponent(redirect)}`,
      },
    })
  }

  async function sendForgotPassword() {
    if (!forgotEmail) return
    setForgotLoading(true)
    const { error } = await supabase.auth.resetPasswordForEmail(forgotEmail, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    setForgotLoading(false)
    if (error) {
      toast({ title: 'Failed to send reset email', description: error.message, variant: 'destructive' })
    } else {
      setForgotSent(true)
    }
  }

  // ── Forgot password view ──────────────────────────────────────────
  if (showForgot) {
    return (
      <div className="relative rounded-2xl p-8 shadow-2xl bg-white/[0.04] border border-white/10 backdrop-blur-xl">
        <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
        <button
          onClick={() => { setShowForgot(false); setForgotSent(false); setForgotEmail('') }}
          className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm mb-6 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
        </button>

        {forgotSent ? (
          <div className="text-center space-y-3 py-4">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center mx-auto">
              <CheckCircle className="h-6 w-6 text-emerald-400" />
            </div>
            <h2 className="text-lg text-white" style={{ fontFamily: 'var(--font-display)', fontWeight: 600 }}>Check your email</h2>
            <p className="text-slate-400 text-sm">
              We sent a password reset link to <strong className="text-slate-200">{forgotEmail}</strong>
            </p>
            <p className="text-xs text-slate-500">Didn't receive it? Check your spam folder.</p>
          </div>
        ) : (
          <>
            <h2 className="text-xl text-white mb-1" style={{ fontFamily: 'var(--font-display)', fontWeight: 600 }}>Reset your password</h2>
            <p className="text-slate-400 text-sm mb-6">Enter your email and we'll send a reset link.</p>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-slate-300 text-sm">Email</Label>
                <Input
                  type="email"
                  value={forgotEmail}
                  onChange={e => setForgotEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 focus:border-indigo-500 focus:ring-indigo-500/20 rounded-xl h-11"
                  onKeyDown={e => e.key === 'Enter' && sendForgotPassword()}
                />
              </div>
              <Button
                onClick={sendForgotPassword}
                disabled={forgotLoading || !forgotEmail}
                className="w-full h-11 gradient-brand text-white font-semibold rounded-xl shadow-brand hover:opacity-90 transition-opacity border-0"
              >
                {forgotLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Send reset link
              </Button>
            </div>
          </>
        )}
      </div>
    )
  }

  // ── Sign in view ──────────────────────────────────────────────────
  return (
    <div className="relative rounded-2xl p-8 shadow-2xl bg-white/[0.04] border border-white/10 backdrop-blur-xl">
      <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
      <div className="mb-6">
        <h2 className="text-xl text-white" style={{ fontFamily: 'var(--font-display)', fontWeight: 600 }}>Welcome back</h2>
        <p className="text-slate-400 text-sm mt-1">Sign in to continue to QuickJob</p>
      </div>

      {/* OAuth buttons */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <button
          onClick={() => signInWithOAuth('google')}
          disabled={!!oauthLoading}
          className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-white/10 bg-white/5 text-slate-300 text-sm font-medium hover:bg-white/10 hover:text-white transition-all duration-150 disabled:opacity-50"
        >
          {oauthLoading === 'google' ? <Loader2 className="h-4 w-4 animate-spin" /> : (
            <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
          )}
          Google
        </button>
        <button
          onClick={() => signInWithOAuth('github')}
          disabled={!!oauthLoading}
          className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-white/10 bg-white/5 text-slate-300 text-sm font-medium hover:bg-white/10 hover:text-white transition-all duration-150 disabled:opacity-50"
        >
          {oauthLoading === 'github' ? <Loader2 className="h-4 w-4 animate-spin" /> : (
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
            </svg>
          )}
          GitHub
        </button>
      </div>

      {/* Divider */}
      <div className="relative flex items-center mb-6">
        <div className="flex-1 border-t border-white/10" />
        <span className="px-3 text-xs text-slate-500 uppercase tracking-wider">or</span>
        <div className="flex-1 border-t border-white/10" />
      </div>

      {/* Email/password form */}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-slate-300 text-sm">Email</Label>
          <Input
            type="email"
            placeholder="you@example.com"
            className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 focus:border-indigo-500 focus:ring-indigo-500/20 rounded-xl h-11"
            {...register('email')}
          />
          {errors.email && <p className="text-xs text-red-400">{errors.email.message}</p>}
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-slate-300 text-sm">Password</Label>
            <button
              type="button"
              onClick={() => {
                setForgotEmail(getValues('email') || '')
                setShowForgot(true)
              }}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Forgot password?
            </button>
          </div>
          <Input
            type="password"
            placeholder="••••••••"
            className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 focus:border-indigo-500 focus:ring-indigo-500/20 rounded-xl h-11"
            {...register('password')}
          />
          {errors.password && <p className="text-xs text-red-400">{errors.password.message}</p>}
        </div>

        <Button
          type="submit"
          className="w-full h-11 gradient-brand text-white font-semibold rounded-xl shadow-brand hover:opacity-90 transition-opacity border-0"
          disabled={loading}
        >
          {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Sign in
        </Button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        No account?{' '}
        <Link href="/signup" className="text-indigo-400 font-medium hover:text-indigo-300 transition-colors">
          Create one free
        </Link>
      </p>
    </div>
  )
}
