import { redirect } from "next/navigation"
import RoleChooser from "@/components/roles/RoleChooser"
import { auth } from "@/lib/auth"
import { normalizeRole } from "@/lib/roles"

export const dynamic = "force-dynamic"

export default async function ChooseRolePage() {
  const session = await auth()
  if (!session?.user) redirect("/login")
  const role = normalizeRole((session.user as typeof session.user & { role?: string }).role)
  return <RoleChooser currentRole={role} />
}
