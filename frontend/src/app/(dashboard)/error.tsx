"use client" // Error boundaries must be Client Components

import { useEffect } from "react"
import { IconAlertTriangle, IconRefresh } from "@tabler/icons-react"

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Optionally log the error to an error reporting service
    console.error("Dashboard caught an error:", error)
  }, [error])

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <div className="mb-6 rounded-full bg-[#fff1f0] p-6 text-[#a32d2d] border border-[#f2b8b5]">
        <IconAlertTriangle size={48} stroke={1.5} />
      </div>
      <h2 className="text-2xl font-bold text-[var(--ink)] mb-3">Something went wrong!</h2>
      <p className="text-[var(--muted)] mb-8 max-w-md">
        We encountered an error while trying to load this page. It might be a temporary database connection issue.
      </p>
      
      <div className="bg-[var(--cream)] border border-[var(--color-border-tertiary)] rounded-md p-4 mb-8 max-w-lg w-full overflow-auto text-left">
        <p className="text-sm font-mono text-[var(--muted)] break-words">
          {error.message || "Unknown error occurred"}
        </p>
      </div>

      <div className="flex gap-4">
        <button
          onClick={() => reset()}
          className="btn btn-hero flex items-center gap-2"
        >
          <IconRefresh size={18} /> Try again
        </button>
      </div>
    </div>
  )
}
