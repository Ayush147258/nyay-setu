import Link from "next/link"
import { IconScale, IconPlus } from "@tabler/icons-react"

export default function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <div className="mb-6 rounded-full bg-[var(--cream)] p-6 text-[var(--muted)]">
        <IconScale size={48} stroke={1.5} />
      </div>
      <h2 className="text-2xl font-bold text-[var(--ink)] mb-3">Welcome to NyaySetu</h2>
      <p className="text-[var(--muted)] mb-8 max-w-md">
        You don't have any cases on your docket yet. Start your first case intake to launch the Agent Arena.
      </p>
      <Link href="/new-case" className="btn btn-hero flex items-center gap-2">
        <IconPlus size={18} /> File your first case
      </Link>
    </div>
  )
}
