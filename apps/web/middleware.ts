import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

// Marketing pages ('/', '/contact', '/terms', '/privacy') now live in the
// separate apps/marketing app on jobnok.com — this app only serves the
// authenticated dashboard on app.jobnok.com, so none of those routes exist here.
const isAuthRoute = createRouteMatcher(['/login(.*)', '/signup(.*)', '/sso-callback(.*)'])
const isApiRoute = createRouteMatcher(['/api(.*)'])

export default clerkMiddleware(async (auth, req) => {
  if (isApiRoute(req)) return NextResponse.next()

  const { userId } = await auth()

  if (!userId && !isAuthRoute(req)) {
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('redirect', req.nextUrl.pathname)
    return NextResponse.redirect(url)
  }

  if (userId && isAuthRoute(req)) {
    return NextResponse.redirect(new URL('/dashboard', req.url))
  }

  if (userId && req.nextUrl.pathname === '/') {
    return NextResponse.redirect(new URL('/dashboard', req.url))
  }

  return NextResponse.next()
})

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
