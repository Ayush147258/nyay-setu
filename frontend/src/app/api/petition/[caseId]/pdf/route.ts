import { NextResponse } from "next/server"
import { and, eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { cases } from "@/db/schema"

function sessionUserId(session: { user?: { id?: string } } | null) {
  return session?.user ? (session.user as typeof session.user & { id?: string }).id : undefined
}

export async function GET(_: Request, { params }: { params: Promise<{ caseId: string }> }) {
  try {
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

    const response = await fetch(`${backendUrl.replace(/\/$/, "")}/petition/${caseId}/pdf`, { cache: "no-store" })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.url) {
      return NextResponse.json({ error: payload?.detail ?? "PDF backend failed" }, { status: 502 })
    }

    return NextResponse.json({ url: payload.url })
  } catch (error) {
    console.error("[petition:pdf]", error)
    return NextResponse.json({ error: "Failed to generate PDF" }, { status: 500 })
  }
}
