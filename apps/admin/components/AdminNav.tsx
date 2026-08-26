'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { UserButton, useUser } from '@clerk/nextjs'
import { cn } from '@jobnok/ui'

const links = [
  { href: '/', label: 'Overview' },
  { href: '/crawler/companies', label: 'Companies' },
  { href: '/crawler/jobs', label: 'Jobs' },
]

export function AdminNav() {
  const pathname = usePathname()
  const { isSignedIn } = useUser()

  if (!isSignedIn) return null

  return (
    <header className="border-b bg-card">
      <div className="container flex h-14 items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="font-semibold text-sm">JobNok Admin</span>
          <nav className="flex items-center gap-4">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  'text-sm text-muted-foreground hover:text-foreground transition-colors',
                  pathname === link.href && 'text-foreground font-medium'
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
        <UserButton afterSignOutUrl="/sign-in" />
      </div>
    </header>
  )
}
