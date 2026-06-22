"use client"

import { useState, useRef, useCallback } from "react"

interface VoiceInputProps {
  onTranscript: (text: string) => void
  langHint?: string
  disabled?: boolean
}

export default function VoiceInput({ onTranscript, langHint = "hi", disabled = false }: VoiceInputProps) {
  const [state, setState] = useState<"idle" | "recording" | "processing" | "error">("idle")
  const [errorMsg, setErrorMsg] = useState("")
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startRecording = useCallback(async () => {
    setErrorMsg("")
    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMsg("Voice not supported in this browser.")
      setState("error")
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" })
      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: "audio/webm" })
        setState("processing")
        try {
          const form = new FormData()
          form.append("file", blob, "recording.webm")
          form.append("lang_hint", langHint)
          const res = await fetch("/api/voice", { method: "POST", body: form })
          if (!res.ok) throw new Error("Transcription failed")
          const data = await res.json()
          onTranscript(data.transcript || "")
          setState("idle")
        } catch {
          setErrorMsg("Could not transcribe. Please type your query.")
          setState("error")
        }
      }
      mediaRef.current = recorder
      recorder.start()
      setState("recording")
    } catch {
      setErrorMsg("Microphone permission denied.")
      setState("error")
    }
  }, [langHint, onTranscript])

  const stopRecording = useCallback(() => {
    mediaRef.current?.stop()
  }, [])

  return (
    <div className="flex flex-col items-center gap-1.5">
      <button
        type="button"
        disabled={disabled || state === "processing"}
        onClick={state === "recording" ? stopRecording : startRecording}
        className={`relative flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all
          ${state === "recording"
            ? "text-white shadow-lg"
            : state === "processing"
            ? "bg-slate-100 text-slate-400 cursor-not-allowed"
            : "btn-outline hover:border-indigo-300 hover:text-indigo-600"
          }`}
        style={state === "recording"
          ? { background: "linear-gradient(135deg, #ef4444, #dc2626)" }
          : undefined}
      >
        {state === "recording" && (
          <span className="pulse-dot w-2 h-2 rounded-full bg-white" />
        )}
        {state === "processing" && (
          <span className="w-3.5 h-3.5 border-2 border-slate-300 border-t-slate-500 rounded-full animate-spin" />
        )}
        {(state === "idle" || state === "error") && (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
          </svg>
        )}
        {state === "recording" ? "Stop" : state === "processing" ? "Transcribing..." : "Record"}
      </button>
      {errorMsg && <p className="text-xs text-red-500 font-medium">{errorMsg}</p>}
    </div>
  )
}
