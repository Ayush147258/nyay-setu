import Link from "next/link"
import {
  Scale,
  LayoutDashboard,
  Folder,
  Upload,
  Plus,
  Bot,
  Shield,
  Book,
  Users,
  Settings,
  HelpCircle,
  Gavel,
  TrendingUp,
  FileCheck,
  MessageSquare,
  FileText,
  HeartCrack,
  MapPin,
  ShoppingCart,
  Monitor,
  CloudUpload,
  Sparkles,
  ArrowRight,
} from "lucide-react"

const DEMO_STATS = [
  { label: "Active Cases", value: 3, sub: "Open legal matters", trend: "+2.4%", className: "si-p" },
  { label: "Documents Filed", value: 12, sub: "Evidence and records", trend: "+1.1%", className: "si-g" },
  { label: "AI Petitions", value: 7, sub: "Hardened by agents", trend: "+18%", className: "si-a" },
  { label: "Rights Queries", value: 24, sub: "Guidance requests", trend: "+12", className: "si-b" },
]

const DEMO_CASES = [
  {
    id: "demo-1",
    title: "FIR Non-Registration — Theft at Residence",
    type: "FIR",
    typeClass: "pill-purple",
    status: "Petition Ready",
    statusClass: "pill-green",
    district: "Bhagalpur, Bihar",
    priority: "High",
    date: "14 Jun 2026",
  },
  {
    id: "demo-2",
    title: "Domestic Violence — Protection Order",
    type: "Domestic Violence",
    typeClass: "pill-red",
    status: "Advocating",
    statusClass: "pill-amber",
    district: "Patna, Bihar",
    priority: "Urgent",
    date: "12 Jun 2026",
  },
  {
    id: "demo-3",
    title: "Consumer Complaint — Defective Electronics",
    type: "Consumer",
    typeClass: "pill-green",
    status: "Intake",
    statusClass: "pill-purple",
    district: "Lucknow, UP",
    priority: "Medium",
    date: "10 Jun 2026",
  },
  {
    id: "demo-4",
    title: "Crop Insurance Claim Rejected — Kharif 2025",
    type: "Crop Insurance",
    typeClass: "pill-green",
    status: "Filed",
    statusClass: "pill-blue",
    district: "Jaipur, Rajasthan",
    priority: "Medium",
    date: "08 Jun 2026",
  },
  {
    id: "demo-5",
    title: "Cyber Fraud — UPI Transaction Dispute",
    type: "Cyber Fraud",
    typeClass: "pill-blue",
    status: "Under Attack",
    statusClass: "pill-red",
    district: "Mumbai, Maharashtra",
    priority: "High",
    date: "05 Jun 2026",
  },
]

const SIDEBAR_SECTIONS = [
  {
    label: "Workspace",
    items: [
      { label: "Dashboard", icon: LayoutDashboard, active: true },
      { label: "My Cases", icon: Folder, badge: "5" },
      { label: "New Case", icon: Plus },
      { label: "Documents", icon: Upload },
    ],
  },
  {
    label: "Legal Tools",
    items: [
      { label: "Agent Arena", icon: Bot, badge: "Live", badgeClass: "g" },
      { label: "Rights Guide", icon: Shield },
      { label: "Research", icon: Book },
      { label: "Advocate Connect", icon: Users },
    ],
  },
  {
    label: "Account",
    items: [
      { label: "Settings", icon: Settings },
      { label: "Help", icon: HelpCircle },
    ],
  },
]

const TYPE_ICONS: Record<string, typeof FileText> = {
  FIR: FileText,
  "Domestic Violence": HeartCrack,
  Consumer: ShoppingCart,
  "Crop Insurance": FileCheck,
  "Cyber Fraud": Monitor,
}

export default function DemoPage() {
  const today = new Intl.DateTimeFormat("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date())

  return (
    <div style={{ position: "relative" }}>
      {/* Demo Banner */}
      <div style={{
        position: "sticky",
        top: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        padding: "10px 20px",
        background: "linear-gradient(135deg, var(--ink), var(--ink2))",
        color: "#fff",
        fontSize: 13,
        fontWeight: 500,
        flexWrap: "wrap",
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Sparkles size={14} style={{ color: "var(--gold-light)" }} />
          You&apos;re viewing a demo dashboard with sample data
        </span>
        <Link href="/signup" style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          padding: "5px 14px",
          borderRadius: 8,
          background: "#fff",
          color: "var(--ink)",
          fontWeight: 600,
          fontSize: 12,
          textDecoration: "none",
          transition: "opacity 0.2s ease",
        }}>
          Sign up free
          <ArrowRight size={12} />
        </Link>
      </div>

      {/* Dashboard Layout */}
      <div className="db">
        {/* Sidebar */}
        <aside className="sb">
          <div className="sb-logo">
            <div className="sb-icon"><Scale size={16} /></div>
            <div>
              <div className="sb-name">NyaySetu</div>
              <div className="sb-tagline">Legal Rights Navigator</div>
            </div>
          </div>

          <nav className="sb-nav">
            {SIDEBAR_SECTIONS.map((section) => (
              <div key={section.label}>
                <span className="nav-sec">{section.label}</span>
                {section.items.map((item) => {
                  const Icon = item.icon
                  return (
                    <span
                      className={`ni ${"active" in item && item.active ? "on" : ""}`}
                      key={item.label}
                      style={{ cursor: "default" }}
                    >
                      <Icon size={15} />
                      {item.label}
                      {"badge" in item && item.badge ? (
                        <span className={`nb ${("badgeClass" in item && item.badgeClass) || ""}`}>{item.badge}</span>
                      ) : null}
                    </span>
                  )
                })}
              </div>
            ))}
          </nav>

          <div className="sb-mission">
            <p className="mq">Injustice anywhere is a threat to justice everywhere - MLK Jr.</p>
          </div>

          <div className="sb-ai">
            <div className="ai-row">
              <div className="ai-av"><Gavel size={14} /></div>
              <div>
                <div className="ai-nm">Agents Online</div>
                <div className="ai-st">Ready to argue</div>
              </div>
              <div className="odot" />
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <div className="main">
          {/* Top Bar */}
          <div className="topbar">
            <div className="tl">
              <h2>Dashboard</h2>
              <p>Good morning, Citizen. {today}</p>
            </div>
            <div className="tr">
              <Link href="/analyze" className="tbtn dark">
                <Plus size={14} />New Case
              </Link>
              <Link href="/upload" className="tbtn">
                <Upload size={14} />Upload Doc
              </Link>
            </div>
          </div>

          {/* Page Body */}
          <div className="pb">
            {/* Stats Grid */}
            <div className="sg">
              {DEMO_STATS.map((stat) => (
                <div className="sc" key={stat.label}>
                  <div className="sc-top">
                    <div className={`sico ${stat.className}`}>
                      {stat.label === "Active Cases" && <Folder size={16} />}
                      {stat.label === "Documents Filed" && <Upload size={16} />}
                      {stat.label === "AI Petitions" && <FileCheck size={16} />}
                      {stat.label === "Rights Queries" && <MessageSquare size={16} />}
                    </div>
                    <span className="strend"><TrendingUp size={12} />{stat.trend}</span>
                  </div>
                  <div className="slbl">{stat.label}</div>
                  <div className="snum">{stat.value}</div>
                  <div className="ssub">{stat.sub}</div>
                </div>
              ))}
            </div>

            {/* Cases + Upload Grid */}
            <div className="dash-grid">
              {/* Cases Table */}
              <div className="dash-card">
                <div className="ch">
                  <div>
                    <div className="ct">Recent Cases</div>
                    <div className="cs">Last 10 matters from your legal workspace</div>
                  </div>
                </div>
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
                      {DEMO_CASES.map((item) => {
                        const TypeIcon = TYPE_ICONS[item.type] || FileText
                        return (
                          <tr key={item.id}>
                            <td className="case-title-cell">{item.title}</td>
                            <td>
                              <span className={`pill ${item.typeClass}`}>
                                <TypeIcon size={13} />{item.type}
                              </span>
                            </td>
                            <td><span className={`pill ${item.statusClass}`}>{item.status}</span></td>
                            <td>{item.district}</td>
                            <td>{item.priority}</td>
                            <td>{item.date}</td>
                            <td>
                              <span style={{
                                color: "var(--gold)",
                                fontWeight: 500,
                                fontSize: 12,
                                cursor: "default",
                              }}>
                                Open Arena →
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* File Upload */}
              <div className="dash-card">
                <div className="ch">
                  <div>
                    <div className="ct">File Upload</div>
                    <div className="cs">PDF, DOCX, JPG, PNG, MP3, MP4 · max 50MB</div>
                  </div>
                </div>
                <div className="cb">
                  <Link
                    href="/upload"
                    className="upload-zone"
                    style={{
                      width: "100%",
                      textDecoration: "none",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 8,
                      cursor: "pointer",
                    }}
                  >
                    <CloudUpload size={30} />
                    <strong>Drop files here or click to upload</strong>
                    <span>Stored privately and attached to the selected case.</span>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
