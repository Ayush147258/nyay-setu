import { and, eq } from "drizzle-orm"
import { NextResponse } from "next/server"
import { z } from "zod"
import { users } from "@/db/schema"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { appRoles } from "@/lib/roles"

const bodySchema = z.object({ role: z.enum(appRoles) })

export async function PATCH(request: Request) {
  const session = await auth()
  const user = session?.user as ({
    id?: string
    tenantId?: string
  }) | undefined
  if (!user?.id) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 })
  }

  const parsed = bodySchema.safeParse(await request.json().catch(() => null))
  if (!parsed.success) {
    return NextResponse.json({ error: "Choose a valid NyaySetu role" }, { status: 400 })
  }

  const db = getDb()
  const [updated] = await db
    .update(users)
    .set({ role: parsed.data.role, updatedAt: new Date() })
    .where(and(eq(users.id, user.id), eq(users.tenantId, user.tenantId ?? "default")))
    .returning({ role: users.role })

  if (!updated) {
    return NextResponse.json({ error: "User profile not found" }, { status: 404 })
  }
  return NextResponse.json({ role: updated.role })
}
