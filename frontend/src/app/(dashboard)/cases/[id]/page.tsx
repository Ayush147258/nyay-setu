import { and, asc, desc, eq } from "drizzle-orm"
import { notFound } from "next/navigation"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { debateTurns, cases, petitions } from "@/db/schema"
import AgentArena from "@/components/arena/AgentArena"
import type { ArenaAgent, ArenaMessage } from "@/components/arena/AgentBubble"

export const dynamic = "force-dynamic"

function sessionUserId(session: { user?: { id?: string } } | null) {
  return session?.user ? (session.user as typeof session.user & { id?: string }).id : undefined
}

export default async function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await auth()
  const userId = sessionUserId(session)
  if (!userId) notFound()

  const { id } = await params
  const db = getDb()
  const [legalCase] = await db
    .select()
    .from(cases)
    .where(and(eq(cases.id, id), eq(cases.userId, userId)))
    .limit(1)

  if (!legalCase) notFound()

  const [messages, latestPetition] = await Promise.all([
    db.select().from(debateTurns).where(eq(debateTurns.caseId, id)).orderBy(asc(debateTurns.createdAt)).limit(100),
    db.select().from(petitions).where(eq(petitions.caseId, id)).orderBy(desc(petitions.filedAt)).limit(1),
  ])

  const initialMessages: ArenaMessage[] = messages.map((message) => ({
    id: message.id,
    agent: message.agentName as ArenaAgent,
    role: "argument",
    content: message.outputSummary ?? message.inputSummary ?? "",
    round: message.roundNumber ?? 1,
    citations: [],
    timestamp: message.createdAt?.toISOString() ?? new Date().toISOString(),
  }))

  return (
    <AgentArena
      legalCase={legalCase}
      initialMessages={initialMessages}
      initialPetition={latestPetition[0]?.finalDocumentText ?? null}
    />
  )
}
