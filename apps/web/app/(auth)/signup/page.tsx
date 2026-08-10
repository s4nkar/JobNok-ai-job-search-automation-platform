'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useSignUp } from '@clerk/nextjs'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2 } from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'

const schema = z.object({
  full_name: z.string().min(2, 'Enter your name'),
  email: z.string().email('Enter a valid email'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
})

type FormData = z.infer<typeof schema>

export default function SignupPage() {
  const router = useRouter()
  const { isLoaded, signUp, setActive } = useSignUp()
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [oauthLoading, setOauthLoading] = useState<string | null>(null)
  const [awaitingCode, setAwaitingCode] = useState(false)
  const [code, setCode] = useState('')
  const [verifying, setVerifying] = useState(false)

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  async function onSubmit(data: FormData) {
    if (!isLoaded) return
    setLoading(true)
    try {
      const [firstName, ...rest] = data.full_name.trim().split(' ')
      const lastName = rest.join(' ') || undefined

      await signUp.create({ emailAddress: data.email, password: data.password, firstName, lastName })
      await signUp.prepareEmailAddressVerification({ strategy: 'email_code' })
      setAwaitingCode(true)
    } catch (err: any) {
      toast({ title: 'Signup failed', description: err?.errors?.[0]?.message || 'Please try again.', variant: 'destructive' })
    }
    setLoading(false)
  }

  async function verifyCode() {
    if (!isLoaded || !code) return
    setVerifying(true)
    try {
      const result = await signUp.attemptEmailAddressVerification({ code })
      if (result.status === 'complete') {
        await setActive({ session: result.createdSessionId })
        toast({ title: 'Account created!' })
        router.push('/dashboard')
      } else {
        toast({ title: 'Verification incomplete', description: 'Please try again.', variant: 'destructive' })
      }
    } catch (err: any) {
      toast({ title: 'Invalid code', description: err?.errors?.[0]?.message || 'Please try again.', variant: 'destructive' })
    }
    setVerifying(false)
  }

  const OAUTH_STRATEGIES = {
    google: 'oauth_google',
    github: 'oauth_github',
    linkedin: 'oauth_linkedin_oidc',
  } as const

  async function signUpWithOAuth(provider: keyof typeof OAUTH_STRATEGIES) {
    if (!isLoaded) return
    setOauthLoading(provider)
    await signUp.authenticateWithRedirect({
      strategy: OAUTH_STRATEGIES[provider],
      redirectUrl: '/sso-callback',
      redirectUrlComplete: '/dashboard',
    })
  }

  if (awaitingCode) {
    return (
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-8">
        <div className="mb-6">
          <h2 className="text-xl font-bold text-slate-900">Verify your email</h2>
          <p className="text-slate-500 text-sm mt-1">Enter the code we just sent you.</p>
        </div>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-sm font-medium text-slate-700">Verification code</Label>
            <Input
              value={code}
              onChange={e => setCode(e.target.value)}
              placeholder="123456"
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              onKeyDown={e => e.key === 'Enter' && verifyCode()}
            />
          </div>
          <Button
            onClick={verifyCode}
            disabled={verifying || !code}
            className="w-full h-10 gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl text-sm font-semibold"
          >
            {verifying && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Verify
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-8">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-slate-900">Create your account</h2>
        <p className="text-slate-500 text-sm mt-1">Set up your account to start automating your job search</p>
      </div>

      {/* OAuth buttons */}
      <div className="grid grid-cols-3 gap-2 mb-6">
        <button
          onClick={() => signUpWithOAuth('google')}
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
          onClick={() => signUpWithOAuth('github')}
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
          onClick={() => signUpWithOAuth('linkedin')}
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

      {/* Email form */}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-sm font-medium text-slate-700">Full name</Label>
          <Input
            placeholder="Jane Smith"
            className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
            {...register('full_name')}
          />
          {errors.full_name && <p className="text-xs text-destructive">{errors.full_name.message}</p>}
        </div>

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
          <Label className="text-sm font-medium text-slate-700">Password</Label>
          <Input
            type="password"
            placeholder="Min. 8 characters"
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
          Create account
        </Button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        Already have an account?{' '}
        <Link href="/login" className="text-indigo-600 font-medium hover:text-indigo-700 transition-colors">
          Sign in
        </Link>
      </p>
    </div>
  )
}
