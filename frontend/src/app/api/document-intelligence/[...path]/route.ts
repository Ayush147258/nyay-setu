import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { createBackendAccessToken } from "@/lib/backend-token"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

type RouteContext = { params: Promise<{ path: string[] }> }

function backendBaseUrl() {
  const value = process.env.PYTHON_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL
  if (!value || value.includes("your-space")) return null
  return value.replace(/\/$/, "")
}

async function proxy(request: Request, context: RouteContext) {
  const session = await auth()
  const user = session?.user as
    | { id?: string; tenantId?: string; email?: string | null }
    | undefined
  if (!user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const baseUrl = backendBaseUrl()
  if (!baseUrl) {
    return NextResponse.json(
      { error: "The document intelligence backend is not configured." },
      { status: 503 },
    )
  }

  try {
    const { path } = await context.params
    const inboundUrl = new URL(request.url)
    const upstreamUrl = new URL(`${baseUrl}/api/${path.map(encodeURIComponent).join("/")}`)
    inboundUrl.searchParams.forEach((value, key) => upstreamUrl.searchParams.append(key, value))

    const token = await createBackendAccessToken({
      userId: user.id,
      email: user.email,
      tenantId: user.tenantId ?? "default",
      expiresInSeconds: 600,
    })
    const headers = new Headers({ Authorization: `Bearer ${token}` })
    for (const name of ["accept", "content-type", "last-event-id"]) {
      const value = request.headers.get(name)
      if (value) headers.set(name, value)
    }

    const hasBody = request.method !== "GET" && request.method !== "HEAD"
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: request.signal,
    })

    const responseHeaders = new Headers()
    for (const name of [
      "content-type",
      "content-disposition",
      "cache-control",
      "x-accel-buffering",
    ]) {
      const value = upstream.headers.get(name)
      if (value) responseHeaders.set(name, value)
    }
    if (!responseHeaders.has("cache-control")) {
      responseHeaders.set("cache-control", "no-store")
    }

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    })
  } catch (error) {
    console.error("[document-intelligence:proxy]", error)
    return NextResponse.json(
      { error: "The document intelligence backend is unavailable." },
      { status: 502 },
    )
  }
}

export const GET = proxy
export const POST = proxy
export const PATCH = proxy
export const DELETE = proxy
