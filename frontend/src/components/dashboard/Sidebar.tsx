"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  IconBooks,
  IconChevronRight,
  IconFiles,
  IconLayoutDashboard,
  IconMicrophone,
  IconScale,
  IconSparkles,
} from "@tabler/icons-react"
import type { AppRole } from "@/lib/roles"
import { roleMeta } from "@/lib/roles"

interface SidebarProps {
  user: any
  role: AppRole
  open: boolean
  setOpen: (value: boolean) => void
}

type NavItem = {
  href: string
  label: string
  icon: typeof IconScale
}

const navByRole: Record<AppRole, NavItem[]> = {
  lawyer: [
    { href: "/dashboard", label: "Hearing desk", icon: IconLayoutDashboard },
    { href: "/new-case", label: "New matter", icon: IconMicrophone },
    { href: "/documents", label: "Preparation rooms", icon: IconFiles },
    { href: "/cases", label: "Case library", icon: IconBooks },
  ],
  judge: [
    { href: "/dashboard", label: "Bench overview", icon: IconLayoutDashboard },
    { href: "/new-case", label: "New review", icon: IconMicrophone },
    { href: "/documents", label: "Document workspaces", icon: IconFiles },
    { href: "/cases", label: "Case library", icon: IconBooks },
  ],
  citizen: [
    { href: "/dashboard", label: "My case", icon: IconLayoutDashboard },
    { href: "/new-case", label: "Add case update", icon: IconMicrophone },
    { href: "/documents", label: "My documents", icon: IconFiles },
    { href: "/cases", label: "Case timeline", icon: IconBooks },
  ],
}

const helpByRole: Record<AppRole, { title: string; detail: string; link: string }> = {
  lawyer: {
    title: "Hearing approaching?",
    detail: "Open a preparation room and review the opponent challenge map.",
    link: "Open preparation rooms",
  },
  judge: {
    title: "Record incomplete?",
    detail: "Inspect integrity caveats before relying on the analysis.",
    link: "Review documents",
  },
  citizen: {
    title: "Unsure what to ask?",
    detail: "Open your case to see delay reasons and lawyer questions.",
    link: "Check my documents",
  },
}

export default function Sidebar({ user, role, open, setOpen }: SidebarProps) {
  const pathname = usePathname()
  const displayName = user?.name || "Ayush Kumar"
  const help = helpByRole[role]

  return (
    <aside className={`sidebar ${open ? "open" : ""}`} id="sidebar" onClick={(event) => event.stopPropagation()}>
      <Link href="/dashboard" className="sidebar-brand" aria-label="NyaySetu home" onClick={() => setOpen(false)}>
        <span className="brand-mark" aria-hidden="true"><IconScale size={20} /></span>
        <span className="brand-name">NyaySetu<small>Role-aware legal workspace</small></span>
      </Link>

      <nav className="sidebar-nav" aria-label="Primary">
        {navByRole[role].map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href || (
            item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`)
          )
          return (
            <Link
              key={item.label}
              href={item.href}
              className={`nav-item ${isActive ? "active" : ""}`}
              onClick={() => setOpen(false)}
            >
              <Icon className="icon" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="help-card">
          <p className="help-title">{help.title}</p>
          <p className="help-sub">{help.detail}</p>
          <Link href="/documents">
            <IconSparkles className="icon" size={14} />
            {help.link}
          </Link>
        </div>
        <Link href="/choose-role" className="account-row" onClick={() => setOpen(false)}>
          <span className="avatar">{displayName.slice(0, 2).toUpperCase()}</span>
          <div className="who">
            <p>{displayName}</p>
            <span>{roleMeta[role].label} view · switch role</span>
          </div>
          <IconChevronRight className="icon" size={15} />
        </Link>
      </div>
    </aside>
  )
}
