import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import DashboardShell from "@/components/dashboard/DashboardShell"
import "./dashboard.css"

export const dynamic = "force-dynamic"

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await auth()
  if (!session?.user) redirect("/login")

  return (
    <DashboardShell user={session.user}>
      {children}
    </DashboardShell>
  )
}
