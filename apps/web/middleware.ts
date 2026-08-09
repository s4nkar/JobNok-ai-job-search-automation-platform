import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

const isAuthRoute = createRouteMatcher(['/login(.*)', '/signup(.*)', '/sso-callback(.*)'])
const isPublicMarketingRoute = createRouteMatcher(['/', '/contact(.*)', '/terms(.*)', '/privacy(.*)'])
const isApiRoute = createRouteMatcher(['/api(.*)'])

export default clerkMiddleware(async (auth, req) => {
  if (isApiRoute(req)) return NextResponse.next()

  const { userId } = await auth()

  if (!userId && !isAuthRoute(req) && !isPublicMarketingRoute(req)) {
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('redirect', req.nextUrl.pathname)
    return NextResponse.redirect(url)
  }

  if (userId && isAuthRoute(req)) {
    return NextResponse.redirect(new URL('/templates', req.url))
  }

  return NextResponse.next()
})

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
