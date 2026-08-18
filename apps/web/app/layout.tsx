import type { Metadata } from 'next'
import { Manrope } from 'next/font/google'
import { ClerkProvider } from '@clerk/nextjs'
import '@jobnok/ui/theme.css'
import './globals.css'
import { Toaster } from '@jobnok/ui'
import { QueryProvider } from '@/components/providers/QueryProvider'

const manrope = Manrope({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'JobNok | AI Job Search Toolkit',
  description: 'Smart templates, resume tailoring, LinkedIn auto-fill, interview prep, and bulk outreach — all in one free toolkit.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider signInUrl="/login" signUpUrl="/signup" afterSignInUrl="/dashboard" afterSignUpUrl="/dashboard">
      <html lang="en">
        <body className={manrope.className}>
          <QueryProvider>
            {children}
            <Toaster />
          </QueryProvider>
        </body>
      </html>
    </ClerkProvider>
  )
}
