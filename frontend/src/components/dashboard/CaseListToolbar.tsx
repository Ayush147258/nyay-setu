"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { useTransition, useState, useEffect } from "react"
import { IconSearch } from "@tabler/icons-react"

export default function CaseListToolbar() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [isPending, startTransition] = useTransition()

  const [q, setQ] = useState(searchParams.get("q") || "")

  // Update URL on input change, debounced
  useEffect(() => {
    const delay = setTimeout(() => {
      const current = new URLSearchParams(Array.from(searchParams.entries()))
      if (q) current.set("q", q)
      else current.delete("q")
      current.delete("page") // reset page on search

      startTransition(() => {
        router.push(`?${current.toString()}`)
      })
    }, 300)

    return () => clearTimeout(delay)
  }, [q, router, searchParams])

  const handleFilter = (key: string, value: string) => {
    const current = new URLSearchParams(Array.from(searchParams.entries()))
    if (value) current.set(key, value)
    else current.delete(key)
    current.delete("page")
    
    startTransition(() => {
      router.push(`?${current.toString()}`)
    })
  }

  return (
    <div className="flex flex-col sm:flex-row gap-3 mb-6 items-center">
      <div className="relative flex-1 w-full">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" size={16} />
        <input
          type="text"
          placeholder="Search cases by title or summary..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="form-field w-full pl-9 m-0"
        />
        {isPending && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--muted)] animate-pulse">Loading...</span>}
      </div>
      
      <select 
        className="form-field m-0 w-full sm:w-auto min-w-[140px]"
        value={searchParams.get("type") || ""}
        onChange={(e) => handleFilter("type", e.target.value)}
      >
        <option value="">All Case Types</option>
        <option value="fir">FIR</option>
        <option value="domestic_violence">Domestic Violence</option>
        <option value="land_dispute">Land Dispute</option>
        <option value="consumer">Consumer</option>
        <option value="cyber_fraud">Cyber Fraud</option>
        <option value="wage_theft">Wage Theft</option>
        <option value="crop_insurance">Crop Insurance</option>
        <option value="flood_relief">Flood Relief</option>
        <option value="other">Other</option>
      </select>

      <select 
        className="form-field m-0 w-full sm:w-auto min-w-[140px]"
        value={searchParams.get("status") || ""}
        onChange={(e) => handleFilter("status", e.target.value)}
      >
        <option value="">All Statuses</option>
        <option value="intake">Intake</option>
        <option value="advocating">Advocating</option>
        <option value="under_attack">Under Attack</option>
        <option value="mediating">Mediating</option>
        <option value="petition_ready">Petition Ready</option>
        <option value="filed">Filed</option>
        <option value="resolved">Resolved</option>
      </select>

      <select 
        className="form-field m-0 w-full sm:w-auto min-w-[140px]"
        value={searchParams.get("sort") || "desc"}
        onChange={(e) => handleFilter("sort", e.target.value)}
      >
        <option value="desc">Newest First</option>
        <option value="asc">Oldest First</option>
      </select>
    </div>
  )
}
