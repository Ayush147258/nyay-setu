import { NextResponse } from "next/server"
import { and, eq } from "drizzle-orm"
import { z } from "zod"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { cases, casePriorityEnum, caseStatusEnum, caseTypeEnum } from "@/db/schema"

const updateCaseSchema = z.object({
  title: z.string().trim().min(3).max(160).optional(),
  rawComplaint: z.string().trim().max(10_000).optional(),
  language: z.string().trim().max(20).optional(),
  caseType: z.enum(caseTypeEnum.enumValues).optional(),
  status: z.enum(caseStatusEnum.enumValues).optional(),
  priority: z.enum(casePriorityEnum.enumValues).optional(),
  district: z.string().trim().max(120).optional(),
  state: z.string().trim().max(120).optional(),
  petitionText: z.string().trim().max(50_000).optional(),
})

function sessionUserId(session: { user?: { id?: string } } | null) {
  return session?.user ? (session.user as typeof session.user & { id?: string }).id : undefined
}

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const session = await auth()
    const userId = sessionUserId(session)
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

    const { id } = await params
    const [row] = await getDb()
      .select()
      .from(cases)
      .where(and(eq(cases.id, id), eq(cases.userId, userId)))
      .limit(1)

    if (!row) return NextResponse.json({ error: "Case not found" }, { status: 404 })
    return NextResponse.json({ case: row })
  } catch (error) {
    console.error("[cases:id:GET]", error)
    return NextResponse.json({ error: "Failed to load case" }, { status: 500 })
  }
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const session = await auth()
    const userId = sessionUserId(session)
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

    const parsed = updateCaseSchema.safeParse(await request.json().catch(() => null))
    if (!parsed.success) {
      return NextResponse.json({ error: "Invalid case update", issues: parsed.error.flatten() }, { status: 400 })
    }

    const { id } = await params
    const [updated] = await getDb()
      .update(cases)
      .set({ ...parsed.data, updatedAt: new Date() })
      .where(and(eq(cases.id, id), eq(cases.userId, userId)))
      .returning()

    if (!updated) return NextResponse.json({ error: "Case not found" }, { status: 404 })
    return NextResponse.json({ case: updated })
  } catch (error) {
    console.error("[cases:id:PATCH]", error)
    return NextResponse.json({ error: "Failed to update case" }, { status: 500 })
  }
}
