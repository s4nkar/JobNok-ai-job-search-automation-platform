import type { Metadata } from 'next'
import { Manrope } from 'next/font/google'
import '@jobnok/ui/theme.css'
import { Navbar } from '@/components/Navbar'
import { Footer } from '@/components/Footer'

const manrope = Manrope({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'JobNok | AI Job Search Toolkit',
  description: 'Smart templates, resume tailoring, LinkedIn auto-fill, interview prep, and bulk outreach — all in one free toolkit.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={manrope.className}>
        <div className="min-h-screen flex flex-col bg-background">
          <Navbar />
          <main className="flex-1 pt-16">{children}</main>
          <Footer />
        </div>
      </body>
    </html>
  )
}
