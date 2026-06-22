import Link from "next/link"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { getCasesForUser } from "@/db/schema"
import {
  IconDeviceLaptop,
  IconFileReport,
  IconHeartBroken,
  IconMap,
  IconShoppingCart,
  IconScale,
  IconPlus,
} from "@tabler/icons-react"
import EmptyState from "@/components/dashboard/EmptyState"

export const dynamic = "force-dynamic"

const typeConfig: Record<string, { label: string; className: string; icon: any; color: string }> = {
  fir: { label: "FIR", className: "pill-purple", icon: IconFileReport, color: "#8E44AD" },
  domestic_violence: { label: "Domestic Violence", className: "pill-red", icon: IconHeartBroken, color: "#B23A2E" },
  land_dispute: { label: "Land Dispute", className: "pill-amber", icon: IconMap, color: "#B8965A" },
  consumer: { label: "Consumer", className: "pill-green", icon: IconShoppingCart, color: "#2E7D4F" },
  cyber_fraud: { label: "Cyber Fraud", className: "pill-blue", icon: IconDeviceLaptop, color: "#4A5FBA" },
  wage_theft: { label: "Wage Theft", className: "pill-amber", icon: IconFileReport, color: "#B8965A" },
  crop_insurance: { label: "Crop Insurance", className: "pill-green", icon: IconFileReport, color: "#2E7D4F" },
  flood_relief: { label: "Flood Relief", className: "pill-blue", icon: IconMap, color: "#4A5FBA" },
  other: { label: "Other", className: "pill-gray", icon: IconFileReport, color: "#6B6457" },
}

const statusConfig: Record<string, { label: string; className: string }> = {
  intake: { label: "Intake", className: "pill-purple" },
  advocating: { label: "Advocating", className: "pill-amber" },
  under_attack: { label: "Under Attack", className: "pill-red" },
  mediating: { label: "Mediating", className: "pill-amber" },
  petition_ready: { label: "Petition Ready", className: "pill-green" },
  filed: { label: "Filed", className: "pill-blue" },
  resolved: { label: "Resolved", className: "pill-gray" },
}

function formatDate(date: Date | null) {
  if (!date) return "Unknown"
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(date))
}

export default async function DashboardPage() {
  const session = await auth()
  if (!session?.user?.id) redirect("/login")

  const cases = await getCasesForUser(session.user.id)

  if (cases.length === 0) {
    return <EmptyState />
  }

  // Aggregate stats
  const totalCases = cases.length
  let inProgressCount = 0
  let readyCount = 0
  let filedCount = 0

  cases.forEach((c) => {
    if (c.status === "petition_ready") {
      readyCount++
    } else if (c.status === "filed" || c.status === "resolved") {
      filedCount++
    } else {
      inProgressCount++
    }
  })

  // Prepare chart data (last 7 days of petitions/cases created)
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  
  const last7Days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now)
    d.setDate(d.getDate() - (6 - i))
    return {
      date: d,
      label: d.toLocaleDateString("en-US", { weekday: "short" }),
      count: 0,
    }
  })

  cases.forEach((c) => {
    if (!c.createdAt) return
    const caseDate = new Date(c.createdAt)
    caseDate.setHours(0, 0, 0, 0)
    
    const dayIndex = last7Days.findIndex(d => d.date.getTime() === caseDate.getTime())
    if (dayIndex !== -1) {
      last7Days[dayIndex].count++
    }
  })

  const maxCount = Math.max(...last7Days.map((d) => d.count), 0)
  const maxDisplay = Math.max(3, Math.ceil(maxCount / 3) * 3)

  const getY = (val: number) => 190 - (val / maxDisplay) * 150
  const getX = (index: number) => 60 + index * 100

  // Generate smooth curve for SVG
  const lineData = last7Days.map((d, i) => {
    if (i === 0) return `M${getX(i)},${getY(d.count)}`
    const prevX = getX(i - 1)
    const prevY = getY(last7Days[i - 1].count)
    const currX = getX(i)
    const currY = getY(d.count)
    const cp1x = prevX + 40
    const cp1y = prevY
    const cp2x = currX - 40
    const cp2y = currY
    return `C${cp1x},${cp1y} ${cp2x},${cp2y} ${currX},${currY}`
  }).join(" ")
  
  const areaData = `${lineData} L660,190 L60,190 Z`

  const yesterdayCount = last7Days[5].count

  const recentCases = [...cases].sort((a, b) => (b.updatedAt?.getTime() ?? 0) - (a.updatedAt?.getTime() ?? 0)).slice(0, 10)

  return (
    <>
      <section className="stats-grid" aria-label="Docket summary">
        <div className="stat-card" style={{ "--stat-accent": "#3B4F6B", "--stat-bg": "#EAEEF3" } as React.CSSProperties}>
          <div className="stat-top">
            <span className="stat-icon"><svg className="icon" viewBox="0 0 24 24"><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H17a2 2 0 0 1 2 2v14H6.5A2.5 2.5 0 0 1 4 17.5z"/><path d="M19 4v16"/></svg></span>
            <span className="stat-trend flat">total</span>
          </div>
          <p className="stat-num">{totalCases}</p>
          <p className="stat-label">Total cases on docket</p>
        </div>

        <div className="stat-card" style={{ "--stat-accent": "var(--indigo)", "--stat-bg": "var(--indigo-tint)" } as React.CSSProperties}>
          <div className="stat-top">
            <span className="stat-icon"><svg className="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg></span>
            <span className="stat-trend flat">live</span>
          </div>
          <p className="stat-num">{inProgressCount}</p>
          <p className="stat-label">In progress with agents</p>
        </div>

        <div className="stat-card" style={{ "--stat-accent": "#92702E", "--stat-bg": "var(--brass-tint)" } as React.CSSProperties}>
          <div className="stat-top">
            <span className="stat-icon"><svg className="icon" viewBox="0 0 24 24"><path d="M9 12.5l2 2 4-4.5"/><rect x="4" y="4" width="16" height="16" rx="2.5"/></svg></span>
            <span className="stat-trend flat">queue</span>
          </div>
          <p className="stat-num">{readyCount}</p>
          <p className="stat-label">Ready to file</p>
        </div>

        <div className="stat-card" style={{ "--stat-accent": "var(--green)", "--stat-bg": "var(--green-tint)" } as React.CSSProperties}>
          <div className="stat-top">
            <span className="stat-icon"><svg className="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5.5"/></svg></span>
            <span className="stat-trend flat">filed</span>
          </div>
          <p className="stat-num">{filedCount}</p>
          <p className="stat-label">Filed with magistrate</p>
        </div>
      </section>

      <section className="content-grid">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>Petitions drafted overview</h2>
              <p className="panel-sub">Across all case types, this docket</p>
            </div>
            <select className="select" aria-label="Date range">
              <option>Last 7 days</option>
            </select>
          </div>

          <div className="chart-wrap">
            <svg viewBox="0 0 700 250" role="img" aria-label="Line chart of petitions drafted per day">
              <defs>
                <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#B23A2E" stopOpacity="0.16"/>
                  <stop offset="100%" stopColor="#B23A2E" stopOpacity="0"/>
                </linearGradient>
              </defs>
              <line x1="60" y1="40" x2="660" y2="40" stroke="#E8E2D2" strokeWidth="1" strokeDasharray="3 4"/>
              <line x1="60" y1="90" x2="660" y2="90" stroke="#E8E2D2" strokeWidth="1" strokeDasharray="3 4"/>
              <line x1="60" y1="140" x2="660" y2="140" stroke="#E8E2D2" strokeWidth="1" strokeDasharray="3 4"/>
              <line x1="60" y1="190" x2="660" y2="190" stroke="#E8E2D2" strokeWidth="1" strokeDasharray="3 4"/>

              <text x="48" y="44" textAnchor="end" fontFamily="IBM Plex Mono, monospace" fontSize="11" fill="#9A917F">{maxDisplay}</text>
              <text x="48" y="94" textAnchor="end" fontFamily="IBM Plex Mono, monospace" fontSize="11" fill="#9A917F">{maxDisplay * 2 / 3}</text>
              <text x="48" y="144" textAnchor="end" fontFamily="IBM Plex Mono, monospace" fontSize="11" fill="#9A917F">{maxDisplay / 3}</text>
              <text x="48" y="194" textAnchor="end" fontFamily="IBM Plex Mono, monospace" fontSize="11" fill="#9A917F">0</text>

              <path d={areaData} fill="url(#areaFill)"/>
              <path d={lineData} fill="none" stroke="#B23A2E" strokeWidth="2.5" strokeLinecap="round"/>

              <g fill="#B23A2E">
                {last7Days.map((d, i) => (
                  <circle key={i} cx={getX(i)} cy={getY(d.count)} r={i === 6 ? "5" : "4"} fill={i === 6 ? "#B23A2E" : "#fff"} stroke={i === 6 ? "#fff" : "#B23A2E"} strokeWidth={i === 6 ? "2" : "2.5"}/>
                ))}
              </g>

              <g fontFamily="IBM Plex Sans, sans-serif" fontSize="11.5" fill="#6B6457" textAnchor="middle">
                {last7Days.map((d, i) => (
                  <text key={i} x={getX(i)} y="216">{d.label}</text>
                ))}
              </g>
            </svg>
          </div>
          <div className="chart-foot">
            <span className="live-dot" aria-hidden="true"></span>
            {yesterdayCount} petitions drafted yesterday
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>Recent cases</h2>
              <p className="panel-sub">Latest activity on the docket</p>
            </div>
            <Link href="/cases" className="link-sm">View all
              <svg className="icon" style={{width: "13px", height: "13px"}} viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
            </Link>
          </div>

          <div className="case-list">
            {recentCases.map((item) => {
              const type = typeConfig[item.caseType] || typeConfig.other
              const status = statusConfig[item.status ?? "intake"] || statusConfig.intake
              
              // Extract initials from title or use CaseType abbreviation
              const initials = item.title 
                ? item.title.split(' ').map(w => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase()
                : type.label.substring(0, 2).toUpperCase()

              return (
                <Link href={`/cases/${item.id}`} className="case-row hover:bg-[var(--cream)] transition-colors cursor-pointer" key={item.id}>
                  <span className="case-avatar" style={{background: type.color}}>{initials}</span>
                  <div className="case-body">
                    <p className="name">{item.title}</p>
                    <p className="meta">{type.label} &middot; <span className="file-no">{item.priority} priority</span></p>
                    <p className="time">{formatDate(item.updatedAt)}</p>
                  </div>
                  <div className="case-side">
                    <span className={`pill ${status.className}`}>{status.label}</span>
                    <button className="more-btn" aria-label="More options" onClick={(e) => e.preventDefault()}>
                      <svg className="icon" style={{width: "15px", height: "15px"}} viewBox="0 0 24 24"><circle cx="12" cy="5" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="19" r="1.2" fill="currentColor" stroke="none"/></svg>
                    </button>
                  </div>
                </Link>
              )
            })}
          </div>
        </div>

      </section>
    </>
  )
}
