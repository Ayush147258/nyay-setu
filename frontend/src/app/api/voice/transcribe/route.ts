import { NextRequest, NextResponse } from "next/server"

export async function POST(req: NextRequest) {
  try {
    const backendUrl = process.env.PYTHON_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL
    if (!backendUrl) return NextResponse.json({ detail: "Voice backend is not configured." }, { status: 503 })

    const formData = await req.formData()
    const response = await fetch(`${backendUrl.replace(/\/$/, "")}/api/voice/transcribe`, {
      method: "POST",
      body: formData,
      cache: "no-store",
    })
    const data = await response.json().catch(() => null)
    return NextResponse.json(data ?? { detail: "Transcription failed" }, { status: response.status })
  } catch {
    return NextResponse.json({ detail: "Voice transcription unavailable. Please type the intake." }, { status: 503 })
  }
}
