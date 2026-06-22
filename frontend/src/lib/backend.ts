import type { LegalDocument, ChatMessage } from "@/lib/types"

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "https://your-space.hf.space"

export async function analyzeCase(
  text: string,
  lang: string,
  tier: string,
  userName = "",
  userLocation = ""
): Promise<LegalDocument> {
  const form = new FormData()
  form.append("text", text)
  form.append("lang", lang)
  form.append("tier", tier)
  form.append("user_name", userName)
  form.append("user_location", userLocation)

  const res = await fetch(`${BACKEND_URL}/api/analyze`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || "Analysis failed")
  }
  const data = await res.json()
  return snakeToCamel(data) as LegalDocument
}

export async function chatWithCase(
  messages: ChatMessage[],
  documentData: string,
  lang: string,
  tier: string
): Promise<string> {
  const res = await fetch(`${BACKEND_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, document_data: documentData, lang, tier }),
  })
  if (!res.ok) throw new Error("Chat failed")
  const data = await res.json()
  return (data as { reply: string }).reply
}

export async function transcribeVoice(
  audioBlob: Blob,
  langHint = "hi"
): Promise<string> {
  const form = new FormData()
  form.append("file", audioBlob, "recording.webm")
  form.append("lang_hint", langHint)
  const res = await fetch(`${BACKEND_URL}/api/voice`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) throw new Error("Voice transcription failed")
  const data = await res.json()
  return (data as { transcript: string }).transcript
}

export function snakeToCamel(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(snakeToCamel)
  if (obj !== null && typeof obj === "object") {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase()),
        snakeToCamel(v),
      ])
    )
  }
  return obj
}
