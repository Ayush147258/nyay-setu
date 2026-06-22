import { NextResponse } from "next/server"
import { and, desc, eq } from "drizzle-orm"
import { z } from "zod"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { activityLog, cases, casePriorityEnum, caseStatusEnum, caseTypeEnum } from "@/db/schema"

const createCaseSchema = z.object({
  title: z.string().trim().min(3).max(160),
  description: z.string().trim().max(10_000).optional(),
  rawInput: z.string().trim().max(10_000).optional(),
  rawComplaint: z.string().trim().max(10_000).optional(),
  language: z.string().trim().max(20).default("hi-IN"),
  caseType: z.enum(caseTypeEnum.enumValues).default("other"),
  status: z.enum(caseStatusEnum.enumValues).default("intake"),
  priority: z.enum(casePriorityEnum.enumValues).default("medium"),
  district: z.string().trim().max(120).optional(),
  state: z.string().trim().max(120).optional(),
  aiSummary: z.string().trim().max(10_000).optional(),
})

function getSessionUserId(session: { user?: { id?: string } } | null) {
  return session?.user ? (session.user as typeof session.user & { id?: string }).id || null : null
}

export async function GET() {
  try {
    const session = await auth()
    const userId = getSessionUserId(session)
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

    const rows = await getDb()
      .select()
      .from(cases)
      .where(eq(cases.userId, userId))
      .orderBy(desc(cases.updatedAt))
      .limit(50)

    return NextResponse.json({ cases: rows })
  } catch (error) {
    console.error("[cases:GET]", error)
    return NextResponse.json({ error: "Failed to list cases" }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const session = await auth()
    const userId = getSessionUserId(session)
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

    const parsed = createCaseSchema.safeParse(await request.json().catch(() => null))
    if (!parsed.success) {
      return NextResponse.json({ error: "Invalid case payload", issues: parsed.error.flatten() }, { status: 400 })
    }

    const complaint = parsed.data.rawInput ?? parsed.data.rawComplaint ?? parsed.data.description ?? ""
    if (!complaint.trim()) return NextResponse.json({ error: "Case narrative is required" }, { status: 400 })

    const db = getDb()
    const [createdCase] = await db
      .insert(cases)
      .values({
        userId,
        title: parsed.data.title,
        description: parsed.data.description ?? complaint,
        rawInput: complaint,
        detectedLanguage: parsed.data.language,
        caseType: parsed.data.caseType,
        status: parsed.data.status,
        priority: parsed.data.priority,
        district: parsed.data.district,
        state: parsed.data.state,
        aiSummary: parsed.data.aiSummary,
        updatedAt: new Date(),
      })
      .returning()

    await db.insert(activityLog).values({
      userId,
      caseId: createdCase.id,
      action: "case_created",
      metadata: { title: createdCase.title, caseType: createdCase.caseType },
    })

    const backendUrl = process.env.PYTHON_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL
    let agentRun: Record<string, unknown> | null = null
    if (backendUrl) {
      const response = await fetch(`${backendUrl.replace(/\/$/, "")}/api/run-agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: createdCase.id, raw_input: complaint }),
        cache: "no-store",
      })
      agentRun = await response.json().catch(() => null)
      if (!response.ok) {
        return NextResponse.json({ error: agentRun?.detail ?? "Agent backend failed to start", case: createdCase }, { status: 502 })
      }
    }

    const verifiedRows = await db
      .select()
      .from(cases)
      .where(and(eq(cases.id, createdCase.id), eq(cases.userId, userId)))
      .limit(1)

    return NextResponse.json({ case: verifiedRows[0], agentRun }, { status: 201 })
  } catch (error) {
    console.error("[cases:POST]", error)
    return NextResponse.json({ error: "Failed to create case" }, { status: 500 })
  }
}
