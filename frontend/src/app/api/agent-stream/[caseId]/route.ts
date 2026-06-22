import { NextResponse } from "next/server"
import { and, eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { cases } from "@/db/schema"

function sessionUserId(session: { user?: { id?: string } } | null) {
  return session?.user ? (session.user as typeof session.user & { id?: string }).id : undefined
}

export async function GET(_: Request, { params }: { params: Promise<{ caseId: string }> }) {
  const session = await auth()
  const userId = sessionUserId(session)
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { caseId } = await params
  const [ownedCase] = await getDb()
    .select({ id: cases.id })
    .from(cases)
    .where(and(eq(cases.id, caseId), eq(cases.userId, userId)))
    .limit(1)

  if (!ownedCase) return NextResponse.json({ error: "Case not found" }, { status: 404 })

  const backendUrl = process.env.PYTHON_BACKEND_URL
  if (!backendUrl) {
    return NextResponse.json({ error: "PYTHON_BACKEND_URL is not configured" }, { status: 500 })
  }

  const upstream = await fetch(`${backendUrl.replace(/\/$/, "")}/stream/${caseId}`, {
    headers: { Accept: "text/event-stream" },
    cache: "no-store",
  })

  if (!upstream.ok || !upstream.body) {
    return NextResponse.json({ error: "Agent backend stream unavailable" }, { status: 502 })
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  })
}
