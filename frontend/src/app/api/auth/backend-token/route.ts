import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { createBackendAccessToken } from "@/lib/backend-token"

export async function POST() {
  const session = await auth()
  const user = session?.user as
    | { id?: string; tenantId?: string; email?: string | null }
    | undefined
  if (!user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  try {
    const expiresIn = 300
    const accessToken = await createBackendAccessToken({
      userId: user.id,
      email: user.email,
      tenantId: user.tenantId ?? "default",
      expiresInSeconds: expiresIn,
    })
    return NextResponse.json(
      { accessToken, tokenType: "Bearer", expiresIn },
      { headers: { "Cache-Control": "no-store" } },
    )
  } catch {
    return NextResponse.json(
      { error: "Backend authentication is not configured" },
      { status: 503 },
    )
  }
}
