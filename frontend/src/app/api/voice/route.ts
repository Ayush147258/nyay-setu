import { NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ""

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()
    const res = await fetch(`${BACKEND}/api/voice`, {
      method: "POST",
      body: formData,
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: "Voice transcription unavailable. Please type your query." },
      { status: 503 }
    )
  }
}
