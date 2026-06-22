import { IconFileCheck, IconFolder, IconMessageQuestion, IconTrendingUp, IconUpload } from "@tabler/icons-react"

export interface DashboardStats {
  activeCases: number
  documentsFiled: number
  petitionsGenerated: number
  rightsQueries: number
}

const statsConfig = [
  { key: "activeCases", label: "Active Cases", sub: "Open legal matters", icon: IconFolder, className: "si-p", trend: "+2.4%" },
  { key: "documentsFiled", label: "Documents Filed", sub: "Evidence and records", icon: IconUpload, className: "si-g", trend: "+1.1%" },
  { key: "petitionsGenerated", label: "AI Petitions", sub: "Hardened by agents", icon: IconFileCheck, className: "si-a", trend: "+18%" },
  { key: "rightsQueries", label: "Rights Queries", sub: "Guidance requests", icon: IconMessageQuestion, className: "si-b", trend: "+12" },
] as const

export default function StatsGrid({ stats }: { stats: DashboardStats }) {
  return (
    <div className="sg">
      {statsConfig.map((item) => {
        const Icon = item.icon
        return (
          <div className="sc" key={item.key}>
            <div className="sc-top">
              <div className={`sico ${item.className}`}><Icon size={16} /></div>
              <span className="strend"><IconTrendingUp size={12} />{item.trend}</span>
            </div>
            <div className="slbl">{item.label}</div>
            <div className="snum">{stats[item.key]}</div>
            <div className="ssub">{item.sub}</div>
          </div>
        )
      })}
    </div>
  )
}
