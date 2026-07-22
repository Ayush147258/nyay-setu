import "server-only"

import { and, eq } from "drizzle-orm"

import { cases } from "@/db/schema"
import { getDb } from "@/lib/db"

type LiveRole = "lawyer" | "judge" | "citizen"

type LiveCaseUser = {
  id: string
  tenantId?: string | null
}

const roleCopy: Record<LiveRole, { title: string; description: string; rawInput: string }> = {
  lawyer: {
    title: "NyaySetu live counsel workspace",
    description: "Live document-intelligence workspace for counsel review, extraction, synthesis, and final answer generation.",
    rawInput: "User is uploading pleadings and evidence for counsel-facing document analysis.",
  },
  judge: {
    title: "NyaySetu live bench workspace",
    description: "Live document-intelligence workspace for neutral bench review, source-span tracing, and caveat analysis.",
    rawInput: "User is uploading case records for bench-facing chronology, evidence, and integrity review.",
  },
  citizen: {
    title: "NyaySetu live citizen workspace",
    description: "Live document-intelligence workspace for plain-language explanation, next steps, and source-grounded guidance.",
    rawInput: "User is uploading legal papers for citizen-facing explanation and next-step guidance.",
  },
}

export async function ensureLiveRoleCase(user: LiveCaseUser, role: LiveRole) {
  const tenantId = user.tenantId || "default"
  const copy = roleCopy[role]
  const db = getDb()

  const [existing] = await db
    .select({ id: cases.id })
    .from(cases)
    .where(and(
      eq(cases.userId, user.id),
      eq(cases.tenantId, tenantId),
      eq(cases.title, copy.title),
    ))
    .limit(1)

  if (existing?.id) return existing.id

  const [created] = await db
    .insert(cases)
    .values({
      userId: user.id,
      tenantId,
      title: copy.title,
      description: copy.description,
      rawInput: copy.rawInput,
      detectedLanguage: "en-IN",
      caseType: "other",
      status: "intake",
      priority: "medium",
      aiSummary: copy.description,
      updatedAt: new Date(),
    })
    .returning({ id: cases.id })

  return created.id
}
