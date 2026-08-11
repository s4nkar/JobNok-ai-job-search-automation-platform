'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useSignIn } from '@clerk/nextjs'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
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
  const redirect = searchParams.get('redirect') || '/dashboard'

  const { isLoaded, signIn, setActive } = useSignIn()
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [oauthLoading, setOauthLoading] = useState<string | null>(null)
  const [showForgot, setShowForgot] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotSent, setForgotSent] = useState(false)
  const [resetCode, setResetCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [resetLoading, setResetLoading] = useState(false)

  const { register, handleSubmit, getValues, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  async function onSubmit(data: FormData) {
    if (!isLoaded) return
    setLoading(true)
    try {
      const result = await signIn.create({ identifier: data.email, password: data.password })
      if (result.status === 'complete') {
        await setActive({ session: result.createdSessionId })
        router.push(redirect)
        router.refresh()
      } else {
        toast({ title: 'Login failed', description: 'Additional verification required.', variant: 'destructive' })
      }
    } catch (err: any) {
      toast({ title: 'Login failed', description: err?.errors?.[0]?.message || 'Check your credentials.', variant: 'destructive' })
    }
    setLoading(false)
  }

  const OAUTH_STRATEGIES = {
    google: 'oauth_google',
    github: 'oauth_github',
    linkedin: 'oauth_linkedin_oidc',
  } as const

  async function signInWithOAuth(provider: keyof typeof OAUTH_STRATEGIES) {
    if (!isLoaded) return
    setOauthLoading(provider)
    await signIn.authenticateWithRedirect({
      strategy: OAUTH_STRATEGIES[provider],
      redirectUrl: '/sso-callback',
      redirectUrlComplete: redirect,
    })
  }

  async function sendForgotPassword() {
    if (!isLoaded || !forgotEmail) return
    setForgotLoading(true)
    try {
      await signIn.create({ strategy: 'reset_password_email_code', identifier: forgotEmail })
      setForgotSent(true)
    } catch (err: any) {
      toast({ title: 'Failed to send reset email', description: err?.errors?.[0]?.message, variant: 'destructive' })
    }
    setForgotLoading(false)
  }

  async function submitNewPassword() {
    if (!isLoaded || !resetCode || !newPassword) return
    setResetLoading(true)
    try {
      const result = await signIn.attemptFirstFactor({
        strategy: 'reset_password_email_code',
        code: resetCode,
        password: newPassword,
      })
      if (result.status === 'complete') {
        await setActive({ session: result.createdSessionId })
        router.push(redirect)
        router.refresh()
      }
    } catch (err: any) {
      toast({ title: 'Could not reset password', description: err?.errors?.[0]?.message, variant: 'destructive' })
    }
    setResetLoading(false)
  }

  // ── Forgot password view ──────────────────────────────────────────
  if (showForgot) {
    return (
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-8">
        <button
          onClick={() => { setShowForgot(false); setForgotSent(false); setForgotEmail(''); setResetCode(''); setNewPassword('') }}
          className="flex items-center gap-1.5 text-slate-500 hover:text-slate-700 text-sm mb-6 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
        </button>

        {forgotSent ? (
          <div className="space-y-4">
            <div className="text-center space-y-2 py-2">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto">
                <CheckCircle className="h-6 w-6 text-emerald-500" />
              </div>
              <h2 className="text-lg font-bold text-slate-900">Check your email</h2>
              <p className="text-slate-500 text-sm">
                We sent a code to <strong className="text-slate-700">{forgotEmail}</strong>
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-sm font-medium text-slate-700">Reset code</Label>
              <Input
                value={resetCode}
                onChange={e => setResetCode(e.target.value)}
                placeholder="123456"
                className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-sm font-medium text-slate-700">New password</Label>
              <Input
                type="password"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                placeholder="••••••••"
                className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
                onKeyDown={e => e.key === 'Enter' && submitNewPassword()}
              />
            </div>
            <Button
              onClick={submitNewPassword}
              disabled={resetLoading || !resetCode || !newPassword}
              className="w-full h-10 gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl text-sm font-semibold"
            >
              {resetLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Set new password
            </Button>
          </div>
        ) : (
          <>
            <h2 className="text-xl font-bold text-slate-900 mb-1">Reset your password</h2>
            <p className="text-slate-500 text-sm mb-6">Enter your email and we&apos;ll send a reset code.</p>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-700">Email</Label>
                <Input
                  type="email"
                  value={forgotEmail}
                  onChange={e => setForgotEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
                  onKeyDown={e => e.key === 'Enter' && sendForgotPassword()}
                />
              </div>
              <Button
                onClick={sendForgotPassword}
                disabled={forgotLoading || !forgotEmail}
                className="w-full h-10 gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl text-sm font-semibold"
              >
                {forgotLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Send reset code
              </Button>
            </div>
          </>
        )}
      </div>
    )
  }

  // ── Sign in view ──────────────────────────────────────────────────
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-8">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-slate-900">Welcome back</h2>
        <p className="text-slate-500 text-sm mt-1">Sign in to continue to JobNok</p>
      </div>

      {/* OAuth buttons */}
      <div className="grid grid-cols-3 gap-2 mb-6">
        <button
          onClick={() => signInWithOAuth('google')}
          disabled={!!oauthLoading}
          className="flex items-center justify-center gap-1.5 h-9 px-2 rounded-xl border border-slate-200 text-slate-600 text-xs font-medium hover:text-slate-900 hover:border-slate-300 transition-all duration-150 disabled:opacity-50"
        >
          {oauthLoading === 'google' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : (
            <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
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
          className="flex items-center justify-center gap-1.5 h-9 px-2 rounded-xl border border-slate-200 text-slate-600 text-xs font-medium hover:text-slate-900 hover:border-slate-300 transition-all duration-150 disabled:opacity-50"
        >
          {oauthLoading === 'github' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : (
            <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
            </svg>
          )}
          GitHub
        </button>
        <button
          onClick={() => signInWithOAuth('linkedin')}
          disabled={!!oauthLoading}
          className="flex items-center justify-center gap-1.5 h-9 px-2 rounded-xl border border-slate-200 text-slate-600 text-xs font-medium hover:text-slate-900 hover:border-slate-300 transition-all duration-150 disabled:opacity-50"
        >
          {oauthLoading === 'linkedin' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : (
            <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="#0A66C2" aria-hidden="true">
              <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zM7.119 20.452H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
            </svg>
          )}
          LinkedIn
        </button>
      </div>

      {/* Divider */}
      <div className="relative flex items-center mb-6">
        <div className="flex-1 border-t border-slate-100" />
        <span className="px-3 text-xs text-slate-400 uppercase tracking-wider">or</span>
        <div className="flex-1 border-t border-slate-100" />
      </div>

      {/* Email/password form */}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-sm font-medium text-slate-700">Email</Label>
          <Input
            type="email"
            placeholder="you@example.com"
            className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
            {...register('email')}
          />
          {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium text-slate-700">Password</Label>
            <button
              type="button"
              onClick={() => {
                setForgotEmail(getValues('email') || '')
                setShowForgot(true)
              }}
              className="text-xs text-indigo-600 hover:text-indigo-700 transition-colors"
            >
              Forgot password?
            </button>
          </div>
          <Input
            type="password"
            placeholder="••••••••"
            className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
            {...register('password')}
          />
          {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
        </div>

        <Button
          type="submit"
          className="w-full h-10 gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl text-sm font-semibold"
          disabled={loading || !isLoaded}
        >
          {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Sign in
        </Button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        No account?{' '}
        <Link href="/signup" className="text-indigo-600 font-medium hover:text-indigo-700 transition-colors">
          Create one free
        </Link>
      </p>
    </div>
  )
}
