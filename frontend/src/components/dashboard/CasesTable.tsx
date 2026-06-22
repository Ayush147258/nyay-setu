import Link from "next/link"
import {
  IconDeviceLaptop,
  IconFileReport,
  IconHeartBroken,
  IconMap,
  IconShoppingCart,
} from "@tabler/icons-react"
import type { CasePriority, CaseStatus, CaseType, LegalCase } from "@/db/schema"

const typeConfig: Record<CaseType, { label: string; className: string; icon: typeof IconFileReport }> = {
  fir: { label: "FIR", className: "pill-purple", icon: IconFileReport },
  domestic_violence: { label: "Domestic Violence", className: "pill-red", icon: IconHeartBroken },
  land_dispute: { label: "Land Dispute", className: "pill-amber", icon: IconMap },
  consumer: { label: "Consumer", className: "pill-green", icon: IconShoppingCart },
  cyber_fraud: { label: "Cyber Fraud", className: "pill-blue", icon: IconDeviceLaptop },
  wage_theft: { label: "Wage Theft", className: "pill-amber", icon: IconFileReport },
  crop_insurance: { label: "Crop Insurance", className: "pill-green", icon: IconFileReport },
  flood_relief: { label: "Flood Relief", className: "pill-blue", icon: IconMap },
  other: { label: "Other", className: "pill-gray", icon: IconFileReport },
}

const statusConfig: Record<CaseStatus, { label: string; className: string }> = {
  intake: { label: "Intake", className: "pill-purple" },
  advocating: { label: "Advocating", className: "pill-amber" },
  under_attack: { label: "Under Attack", className: "pill-red" },
  mediating: { label: "Mediating", className: "pill-amber" },
  petition_ready: { label: "Petition Ready", className: "pill-green" },
  filed: { label: "Filed", className: "pill-blue" },
  resolved: { label: "Resolved", className: "pill-gray" },
}

function formatDate(date: Date | string) {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(date))
}

function formatPriority(priority: CasePriority) {
  return priority.charAt(0).toUpperCase() + priority.slice(1)
}

export default function CasesTable({ cases }: { cases: LegalCase[] }) {
  if (cases.length === 0) {
    return <div className="empty-state">No cases yet. Start a new case to launch the Agent Arena.</div>
  }

  return (
    <div className="cases-table-wrap">
      <table className="cases-table">
        <thead>
          <tr>
            <th>Case Title</th>
            <th>Type</th>
            <th>Status</th>
            <th>District</th>
            <th>Priority</th>
            <th>Last Updated</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((item) => {
            const type = typeConfig[(item.caseType as CaseType) ?? "other"]
            const status = statusConfig[(item.status as CaseStatus) ?? "intake"]
            const Icon = type?.icon ?? IconFileReport
            return (
              <tr key={item.id}>
                <td className="case-title-cell">{item.title}</td>
                <td><span className={`pill ${type?.className ?? "pill-gray"}`}><Icon size={13} />{type?.label ?? "Other"}</span></td>
                <td><span className={`pill ${status?.className ?? "pill-gray"}`}>{status?.label ?? "Unknown"}</span></td>
                <td>{[item.district, item.state].filter(Boolean).join(", ") || "Not set"}</td>
                <td>{formatPriority((item.priority as CasePriority) ?? "medium")}</td>
                <td>{formatDate(item.updatedAt ?? new Date())}</td>
                <td><Link className="cl" href={`/cases/${item.id}`}>Open Arena →</Link></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
