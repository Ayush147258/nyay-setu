import { notFound, redirect } from "next/navigation"
import { and, eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { cases } from "@/db/schema"
import JudgeWorkspace from "@/components/workspace/JudgeWorkspace"
import { normalizeRole } from "@/lib/roles"

export const dynamic = "force-dynamic"

export default async function CaseWorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const session = await auth()
  if (!session?.user) redirect("/login")
  const userId = (session.user as typeof session.user & { id?: string }).id
  const audience = normalizeRole((session.user as typeof session.user & { role?: string }).role)
  if (!userId) redirect("/login")

  const { id } = await params
  const db = getDb()
  const [legalCase] = await db
    .select()
    .from(cases)
    .where(and(eq(cases.id, id), eq(cases.userId, userId)))
    .limit(1)
  if (!legalCase) notFound()

  return (
    <JudgeWorkspace
      caseId={legalCase.id}
      caseTitle={legalCase.title ?? `Case ${legalCase.id.slice(0, 8)}`}
      caseType={legalCase.caseType}
      district={legalCase.district ?? undefined}
      caseStatus={legalCase.status ?? undefined}
      audience={audience}
    />
  )
}

