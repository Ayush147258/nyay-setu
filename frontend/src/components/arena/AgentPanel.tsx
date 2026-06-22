"use client"

import type { ArenaAgent } from "@/components/arena/AgentBubble"

export type AgentStatus = "IDLE" | "THINKING..." | "ARGUING" | "COMPLETE" | "OVERRULED"

const agents: Array<{ key: ArenaAgent; name: string; role: string; color: string }> = [
  { key: "intake", name: "Intake Agent", role: "Classifies & routes your case", color: "#534AB7" },
  { key: "advocate", name: "Advocate Agent", role: "Builds strongest legal argument", color: "#3B6D11" },
  { key: "adversarial", name: "Adversarial Agent", role: "Attacks like a bureaucrat", color: "#A32D2D" },
  { key: "mediator", name: "Mediator Agent", role: "Scores debate, forces resolution", color: "#854F0B" },
  { key: "filing", name: "Filing Agent", role: "Routes, files, follows up", color: "#185FA5" },
]

export default function AgentPanel({
  statuses,
  activeAgent,
  round,
  caseMeta,
}: {
  statuses: Partial<Record<ArenaAgent, AgentStatus>>
  activeAgent?: ArenaAgent
  round: number
  caseMeta: { caseType: string; district?: string | null; language?: string | null; priority: string }
}) {
  return (
    <div className="flex flex-col gap-3">
      {agents.map((agent) => (
        <div className="agent-status-card" key={agent.key}>
          <div className="agent-card-head">
            <span className={`agent-dot ${activeAgent === agent.key ? "active" : ""}`} style={{ color: agent.color }} />
            <div>
              <div className="agent-name">{agent.name}</div>
              <div className="agent-role">{agent.role}</div>
            </div>
            <span className="pill pill-gray ml-auto">{statuses[agent.key] ?? "IDLE"}</span>
          </div>
          <div className="agent-last">Awaiting latest action...</div>
        </div>
      ))}
      <div className="agent-status-card">
        <div className="ct">Round {Math.min(round, 2)} of 2</div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#f0ece2]">
          <div
            className="h-full rounded-full"
            style={{
              width: `${Math.min(round, 2) * 50}%`,
              background: round >= 2 ? "#A32D2D" : "#BA7517",
            }}
          />
        </div>
      </div>
      <div className="agent-status-card">
        <div className="ct">Case Metadata</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="pill pill-purple">{caseMeta.caseType}</span>
          <span className="pill pill-amber">{caseMeta.priority}</span>
          <span className="pill pill-blue">{caseMeta.language ?? "hi"}</span>
          {caseMeta.district ? <span className="pill pill-gray">{caseMeta.district}</span> : null}
        </div>
      </div>
    </div>
  )
}
