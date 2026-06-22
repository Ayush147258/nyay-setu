"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

interface SidebarProps {
  user: any;
  open: boolean;
  setOpen: (val: boolean) => void;
}

export default function Sidebar({ user, open, setOpen }: SidebarProps) {
  const pathname = usePathname()
  
  const navItems = [
    { href: "/dashboard", label: "Dashboard", icon: <svg className="icon" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg> },
    { href: "/new-case", label: "New case", icon: <svg className="icon" viewBox="0 0 24 24"><path d="M12 18v3M8 21h8"/><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/></svg> },
    { href: "/cases", label: "Case library", icon: <svg className="icon" viewBox="0 0 24 24"><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H17a2 2 0 0 1 2 2v14H6.5A2.5 2.5 0 0 1 4 17.5z"/><path d="M19 4v16"/></svg>, badge: "184" },
    { href: "/arena", label: "Agent arena", icon: <svg className="icon" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="6" rx="1.5"/><rect x="3" y="11" width="18" height="10" rx="1.5"/><path d="M8 16h4"/></svg> },
    { href: "/tracking", label: "Tracking", icon: <svg className="icon" viewBox="0 0 24 24"><path d="M21 10c0 6-9 12-9 12S3 16 3 10a9 9 0 0 1 18 0Z"/><circle cx="12" cy="10" r="2.6"/></svg> },
    { href: "/insights", label: "AI insights", icon: <svg className="icon" viewBox="0 0 24 24"><path d="M3 17l5-6 4 4 7-9"/><path d="M14 6h5v5"/></svg> },
    { href: "/architecture", label: "Architecture", icon: <svg className="icon" viewBox="0 0 24 24"><path d="M12 3 3 8l9 5 9-5z"/><path d="M3 13l9 5 9-5"/></svg> },
  ]

  const displayName = user?.name || "Ayush Kumar"
  const role = "Case officer" // default

  return (
    <aside className={`sidebar ${open ? "open" : ""}`} id="sidebar" onClick={(e) => e.stopPropagation()}>
      <Link href="/dashboard" className="sidebar-brand" aria-label="NyaySetu home" onClick={() => setOpen(false)}>
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M5 8h14M12 8v11M7 19h10" stroke="#B23A2E" strokeWidth="2" strokeLinecap="round"/>
            <circle cx="5" cy="11" r="2.2" stroke="#B8965A" strokeWidth="1.3"/>
            <circle cx="19" cy="11" r="2.2" stroke="#B8965A" strokeWidth="1.3"/>
          </svg>
        </span>
        <span className="brand-name">NyaySetu<small>न्यायसेतु · docket</small></span>
      </Link>

      <nav className="sidebar-nav" aria-label="Primary">
        {navItems.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link 
              key={item.label}
              href={item.href} 
              className={`nav-item ${isActive ? "active" : ""}`}
              onClick={() => setOpen(false)}
            >
              {item.icon}
              {item.label}
              {item.badge && <span className="badge">{item.badge}</span>}
            </Link>
          )
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="help-card">
          <p className="help-title">Stuck on a filing?</p>
          <p className="help-sub">Hand a difficult case to the mediator agent for a second opinion.</p>
          <Link href="/mediator">
            <svg className="icon" style={{width: "14px", height: "14px"}} viewBox="0 0 24 24"><path d="M5 8h14M12 8v11M7 19h10"/></svg>
            Talk to mediator
          </Link>
        </div>
        <div className="account-row">
          <span className="avatar">{displayName.slice(0, 2).toUpperCase()}</span>
          <div className="who">
            <p>{displayName}</p>
            <span>{role}</span>
          </div>
          <svg className="icon" style={{width: "15px", height: "15px"}} viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>
    </aside>
  )
}
