import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"

const PUBLIC_PATHS = new Set(["/", "/login", "/signup", "/sign-in", "/sign-up", "/analyze", "/upload", "/demo"])
const PROTECTED_PREFIXES = ["/dashboard", "/cases", "/new-case", "/documents", "/lawyer", "/judge", "/citizen"]

export default auth((request) => {
  const { pathname } = request.nextUrl
  const isPublic =
    PUBLIC_PATHS.has(pathname) ||
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon")

  if (isPublic) return NextResponse.next()

  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
  if (isProtected && !request.auth) {
    const loginUrl = new URL("/login", request.nextUrl)
    loginUrl.searchParams.set("callbackUrl", request.nextUrl.pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
})

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/cases/:path*",
    "/new-case/:path*",
    "/documents/:path*",
    "/lawyer/:path*",
    "/judge/:path*",
    "/citizen/:path*",
    "/api/cases/:path*",
    "/api/upload/:path*",
  ],
}

