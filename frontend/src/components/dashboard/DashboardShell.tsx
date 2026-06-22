"use client"

import { useState } from "react"
import Sidebar from "./Sidebar"
import TopBar from "./TopBar"

export default function DashboardShell({ 
  children, 
  user 
}: { 
  children: React.ReactNode, 
  user: any 
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="nyaysetu-dashboard-theme shell">
      <Sidebar user={user} open={menuOpen} setOpen={setMenuOpen} />
      
      <main className="main" onClick={() => menuOpen && setMenuOpen(false)}>
        <div className="mobile-bar">
          <button 
            className="icon-btn" 
            id="menuBtn" 
            aria-label="Open menu" 
            aria-expanded={menuOpen} 
            onClick={(e) => { 
              e.stopPropagation(); 
              setMenuOpen(!menuOpen); 
            }}
          >
            <svg className="icon" viewBox="0 0 24 24"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
          </button>
          <span className="brand-name" style={{fontSize: "15px"}}>NyaySetu</span>
        </div>
        
        <TopBar name={user?.name} image={user?.image} />

        {children}
      </main>
    </div>
  )
}
