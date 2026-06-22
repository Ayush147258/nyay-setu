import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"

const PUBLIC_PATHS = new Set(["/", "/login", "/signup", "/sign-in", "/sign-up", "/analyze", "/upload", "/demo"])

export default auth((request) => {
  const { pathname } = request.nextUrl
  const isPublic =
    PUBLIC_PATHS.has(pathname) ||
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon")

  if (isPublic) return NextResponse.next()

  if (
    (pathname.startsWith("/dashboard") ||
      pathname.startsWith("/cases") ||
      pathname.startsWith("/new-case") ||
      pathname.startsWith("/documents")) &&
    !request.auth
  ) {
    const loginUrl = new URL("/login", request.nextUrl)
    loginUrl.searchParams.set("callbackUrl", request.nextUrl.pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
})

export const config = {
  matcher: ["/dashboard/:path*", "/cases/:path*", "/new-case/:path*", "/documents/:path*", "/api/cases/:path*", "/api/upload/:path*"],
}
