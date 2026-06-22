"use client"

export type ArenaAgent = "intake" | "advocate" | "adversarial" | "mediator" | "filing"

export interface ArenaCitation {
  section: string
  title?: string
  url?: string
}

export interface ArenaMessage {
  id?: string
  agent: ArenaAgent
  role: "thinking" | "argument" | "attack" | "ruling" | "action"
  content: string
  round: number
  citations?: ArenaCitation[]
  timestamp?: string
}

const config: Record<ArenaAgent, { label: string; tag: string; color: string; bg: string; initial: string }> = {
  intake: { label: "Intake Agent", tag: "CLASSIFYING", color: "#534AB7", bg: "#EEEDFE", initial: "I" },
  advocate: { label: "Advocate Agent", tag: "ARGUING", color: "#3B6D11", bg: "#EAF3DE", initial: "A" },
  adversarial: { label: "Adversarial Agent", tag: "⚔ ATTACKING DRAFT", color: "#A32D2D", bg: "#FCEBEB", initial: "X" },
  mediator: { label: "Mediator Agent", tag: "⚖ MEDIATOR RULING", color: "#854F0B", bg: "#FAEEDA", initial: "M" },
  filing: { label: "Filing Agent", tag: "FILING ACTION", color: "#185FA5", bg: "#E6F1FB", initial: "F" },
}

export default function AgentBubble({ message }: { message: ArenaMessage }) {
  const item = config[message.agent]

  return (
    <article
      className={`agent-bubble ${message.agent === "mediator" ? "mediator" : ""}`}
      style={{ borderLeftColor: item.color, background: item.bg }}
    >
      <div className="agent-bubble-head">
        <div className="agent-meta">
          <span className="agent-avatar" style={{ background: item.color }}>{item.initial}</span>
          <span>
            <span className="agent-name">{item.label}</span>
            <span className={`pill ${message.agent === "adversarial" ? "pill-red" : message.agent === "mediator" ? "pill-amber" : "pill-gray"} ml-2`}>{item.tag}</span>
          </span>
        </div>
        <span className="pill pill-gray">{message.role === "ruling" ? "RULING" : `R${message.round}`}</span>
      </div>
      <div className="agent-bubble-content">{message.content}</div>
      {message.citations?.length ? (
        <div className="citation-row">
          {message.citations.map((citation) => (
            citation.url ? (
              <a className="citation-tag" href={citation.url} target="_blank" rel="noreferrer" key={`${citation.section}-${citation.url}`}>
                {citation.section}
              </a>
            ) : (
              <span className="citation-tag" key={citation.section}>{citation.section}</span>
            )
          ))}
        </div>
      ) : null}
    </article>
  )
}
