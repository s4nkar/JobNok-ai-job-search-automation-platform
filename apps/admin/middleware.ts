import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

// Session-level gate only - requires SOME authenticated Clerk user, same as
// apps/web. Whether that user is actually an admin is enforced server-side
// on every API call (require_role("admin") in the FastAPI backend), not
// here - this app has no self-serve signup, admins are provisioned directly
// via Clerk, so there's no separate /signup route to gate.
const isAuthRoute = createRouteMatcher(['/sign-in(.*)'])
const isApiRoute = createRouteMatcher(['/api(.*)'])

export default clerkMiddleware(async (auth, req) => {
  if (isApiRoute(req)) return NextResponse.next()

  const { userId } = await auth()

  if (!userId && !isAuthRoute(req)) {
    const url = req.nextUrl.clone()
    url.pathname = '/sign-in'
    url.searchParams.set('redirect', req.nextUrl.pathname)
    return NextResponse.redirect(url)
  }

  if (userId && isAuthRoute(req)) {
    return NextResponse.redirect(new URL('/', req.url))
  }

  return NextResponse.next()
})

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
