import { NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ""

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()

    const headers: Record<string, string> = {}
    const authHeader = req.headers.get("authorization")
    if (authHeader) headers["Authorization"] = authHeader

    const res = await fetch(`${BACKEND}/api/analyze`, {
      method: "POST",
      headers,
      body: formData,
    })

    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    return NextResponse.json(
      { detail: "Backend connection failed. The AI may be warming up — try again in 30 seconds." },
      { status: 503 }
    )
  }
}
