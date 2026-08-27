import type { Metadata } from 'next'
import { ClerkProvider } from '@clerk/nextjs'
import '@jobnok/ui/theme.css'
import './globals.css'
import { Toaster } from '@jobnok/ui'
import { QueryProvider } from '@/components/providers/QueryProvider'
import { AdminNav } from '@/components/AdminNav'

export const metadata: Metadata = {
  title: 'JobNok Admin',
  description: 'Internal crawler observability.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider signInUrl="/sign-in" afterSignInUrl="/">
      <html lang="en">
        <body>
          <QueryProvider>
            <AdminNav />
            <main className="container py-8">{children}</main>
            <Toaster />
          </QueryProvider>
        </body>
      </html>
    </ClerkProvider>
  )
}
