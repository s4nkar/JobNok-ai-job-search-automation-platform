'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useUser } from '@clerk/nextjs'

const SCROLL_THRESHOLD = 60

export function Navbar() {
  const { isLoaded, isSignedIn } = useUser()
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > SCROLL_THRESHOLD)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={`fixed top-0 inset-x-0 z-40 transition-colors duration-300 border-b ${
        scrolled
          ? 'bg-white/80 backdrop-blur border-slate-100'
          : 'bg-transparent border-transparent'
      }`}
    >
      <div className="container flex items-center justify-between h-16">
        <Link href="/" className="flex items-center shrink-0">
          <img src="/logo.png" alt="JobNok" className="h-10 w-auto" />
        </Link>

        <nav className="hidden md:flex items-center gap-7 text-sm text-slate-600">
          <Link href="/#tools" className="hover:text-slate-900 transition-colors">Tools</Link>
          <Link href="/#pipeline" className="hover:text-slate-900 transition-colors">How it works</Link>
          <Link href="/contact" className="hover:text-slate-900 transition-colors">Contact</Link>
        </nav>

        <div className="flex items-center gap-2">
          {isLoaded && isSignedIn ? (
            <Link
              href="/dashboard"
              className="inline-flex items-center h-10 px-5 rounded-full text-sm font-medium gradient-brand text-white shadow-brand-sm hover:opacity-90 transition-opacity"
            >
              Dashboard
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="hidden sm:inline-flex items-center h-10 px-4 rounded-full text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors"
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className="inline-flex items-center h-10 px-5 rounded-full text-sm font-medium gradient-brand text-white shadow-brand-sm hover:opacity-90 transition-opacity"
              >
                Get started free
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
