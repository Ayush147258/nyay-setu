import Link from "next/link"
import type { AppRole } from "@/lib/roles"

interface TopBarProps {
  name?: string | null
  role: AppRole
}

const copy: Record<AppRole, { title: string; subtitle: string; action: string }> = {
  lawyer: {
    title: "Hearing desk",
    subtitle: "Pressure-test active matters and prepare record-backed responses.",
    action: "New matter",
  },
  judge: {
    title: "Bench overview",
    subtitle: "Review the record, chronology, authorities, and unresolved caveats.",
    action: "New review",
  },
  citizen: {
    title: "My case",
    subtitle: "Track progress, understand delays, and prepare for your next lawyer meeting.",
    action: "Add case",
  },
}

export default function TopBar({ name, role }: TopBarProps) {
  const displayName = name?.split(" ")[0] ?? "Ayush"
  const mode = copy[role]

  return (
    <div className="topbar">
      <div>
        <h1>{mode.title}</h1>
        <p className="sub">Welcome back, {displayName}. {mode.subtitle}</p>
        <p className="docket-tag">Synced 2 minutes ago</p>
      </div>
      <div className="topbar-actions">
        <button className="icon-btn" aria-label="Search">
          <svg className="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
        </button>
        <button className="icon-btn" aria-label="Notifications">
          <svg className="icon" viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>
          <span className="dot" aria-hidden="true" />
        </button>
        <Link href="/new-case" className="btn-primary">
          <svg className="icon" style={{ width: "15px", height: "15px", color: "#fff" }} viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
          {mode.action}
        </Link>
      </div>
    </div>
  )
}
