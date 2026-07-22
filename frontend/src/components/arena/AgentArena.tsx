"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import AgentBubble, { type ArenaAgent, type ArenaMessage } from "@/components/arena/AgentBubble"
import AgentPanel, { type AgentStatus } from "@/components/arena/AgentPanel"
import PetitionPreview from "@/components/arena/PetitionPreview"
import type { LegalCase } from "@/db/schema"

type StreamEvent =
  | ({ type: "agent_message" } & ArenaMessage)
  | { type: "agent_status"; agent: ArenaAgent; status: AgentStatus }
  | { type: "round_change"; round: number }
  | { type: "petition_update"; petition: string }
  | { type: "debate_complete"; petition?: string }
  | { type: "error"; message: string }

export default function AgentArena({
  legalCase,
  initialMessages,
  initialPetition,
}: {
  legalCase: LegalCase
  initialMessages: ArenaMessage[]
  initialPetition?: string | null
}) {
  const [messages, setMessages] = useState<ArenaMessage[]>(initialMessages)
  const [petition, setPetition] = useState(initialPetition)
  const [complete, setComplete] = useState(legalCase.status === "petition_ready" || legalCase.status === "filed")
  const [round, setRound] = useState(Math.max(legalCase.debateRound ?? 1, 1))
  const [activeAgent, setActiveAgent] = useState<ArenaAgent | undefined>()
  const [statuses, setStatuses] = useState<Partial<Record<ArenaAgent, AgentStatus>>>({})
  const [error, setError] = useState("")

  useEffect(() => {
    if (complete) return
    const eventSource = new EventSource(`/api/agent-stream/${legalCase.id}`)

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as StreamEvent
        if (payload.type === "agent_message") {
          setMessages((current) => [...current, payload])
          setActiveAgent(payload.agent)
        }
        if (payload.type === "agent_status") {
          setStatuses((current) => ({ ...current, [payload.agent]: payload.status }))
          setActiveAgent(payload.agent)
        }
        if (payload.type === "round_change") setRound(payload.round)
        if (payload.type === "petition_update") setPetition(payload.petition)
        if (payload.type === "debate_complete") {
          setComplete(true)
          if (payload.petition) setPetition(payload.petition)
          eventSource.close()
        }
        if (payload.type === "error") setError(payload.message)
      } catch {
        setError("Received an unreadable agent event.")
      }
    }

    eventSource.onerror = () => {
      setError("Agent stream disconnected. Reconnecting if the backend is still running.")
    }

    return () => eventSource.close()
  }, [complete, legalCase.id])

  const groupedFeed = useMemo(() => messages, [messages])

  return (
    <div className="arena-grid">
      <AgentPanel
        statuses={statuses}
        activeAgent={activeAgent}
        round={round}
        caseMeta={{
          caseType: legalCase.caseType,
          district: legalCase.district ?? undefined,
          language: legalCase.detectedLanguage ?? "hi-IN",
          priority: (legalCase.priority as "low" | "medium" | "high" | "urgent") ?? "medium",
        }}
      />
      <section className="dash-card arena-chat">
        <div className="ch">
          <div>
            <div className="ct">Agent Arena</div>
            <div className="cs">{legalCase.title}</div>
          </div>
          <div className="flex items-center gap-2">
            <Link href={`/cases/${legalCase.id}/workspace`} className="tbtn">
              Document workspace
            </Link>
            <span className={`pill ${complete ? "pill-green" : "pill-amber"}`}>
              {complete ? "Debate complete" : "Live debate in progress"}
            </span>
          </div>
        </div>
        <div className="arena-feed">
          <div className="system-message">-- Debate Round {round} Started --</div>
          {groupedFeed.length ? groupedFeed.map((message, index) => (
            <AgentBubble message={message} key={message.id ?? `${message.agent}-${index}`} />
          )) : (
            <div className="empty-state">Waiting for the first agent message from the Python backend SSE stream.</div>
          )}
          {error ? <div className="system-message">{error}</div> : null}
        </div>
        {complete ? (
          <div className="border-t border-[var(--color-border-tertiary)] p-3">
            <div className="flex gap-2">
              <input className="form-field m-0 flex-1" placeholder="Ask a question about your case..." />
              <button className="tbtn dark">Send</button>
            </div>
          </div>
        ) : null}
      </section>
      <PetitionPreview petition={petition} complete={complete} caseId={legalCase.id} />
    </div>
  )
}
