"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { IconPlayerPlay, IconRefresh, IconSend, IconSquare, IconMicrophone } from "@tabler/icons-react"
import type { CasePriority, CaseType } from "@/db/schema"

const sarvamLanguages = [
  { code: "hi-IN", name: "Hindi" },
  { code: "as-IN", name: "Assamese" },
  { code: "bn-IN", name: "Bengali" },
  { code: "ur-IN", name: "Urdu" },
  { code: "kn-IN", name: "Kannada" },
  { code: "ne-IN", name: "Nepali" },
  { code: "ml-IN", name: "Malayalam" },
  { code: "kok-IN", name: "Konkani" },
  { code: "mr-IN", name: "Marathi" },
  { code: "ks-IN", name: "Kashmiri" },
  { code: "od-IN", name: "Odia" },
  { code: "sd-IN", name: "Sindhi" },
  { code: "pa-IN", name: "Punjabi" },
  { code: "sa-IN", name: "Sanskrit" },
  { code: "ta-IN", name: "Tamil" },
  { code: "sat-IN", name: "Santali" },
  { code: "te-IN", name: "Telugu" },
  { code: "mni-IN", name: "Manipuri" },
  { code: "en-IN", name: "English" },
  { code: "brx-IN", name: "Bodo" },
  { code: "gu-IN", name: "Gujarati" },
  { code: "mai-IN", name: "Maithili" },
  { code: "doi-IN", name: "Dogri" },
]

const caseTypes: Array<{ value: CaseType; label: string }> = [
  { value: "fir", label: "FIR Not Registered" },
  { value: "domestic_violence", label: "Domestic Violence" },
  { value: "land_dispute", label: "Land Dispute" },
  { value: "consumer", label: "Consumer" },
  { value: "cyber_fraud", label: "Cyber Fraud" },
  { value: "wage_theft", label: "Wage Theft" },
  { value: "crop_insurance", label: "Crop Insurance" },
  { value: "flood_relief", label: "Flood Relief" },
  { value: "other", label: "Other" },
]

const states = ["Bihar", "Delhi", "Karnataka", "Maharashtra", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal"]

type InputMode = "voice" | "text"
type RecorderStatus = "idle" | "recording" | "recorded" | "transcribing"

function formatDuration(seconds: number) {
  const mins = Math.floor(seconds / 60).toString().padStart(2, "0")
  const secs = Math.floor(seconds % 60).toString().padStart(2, "0")
  return `${mins}:${secs}`
}

export default function NewCasePage() {
  const router = useRouter()
  const [mode, setMode] = useState<InputMode>("voice")
  const [title, setTitle] = useState("")
  const [caseType, setCaseType] = useState<CaseType>("fir")
  const [priority, setPriority] = useState<CasePriority>("medium")
  const [language, setLanguage] = useState("hi-IN")
  const [district, setDistrict] = useState("")
  const [state, setState] = useState("Bihar")
  const [transcript, setTranscript] = useState("")
  const [status, setStatus] = useState<RecorderStatus>("idle")
  const [duration, setDuration] = useState(0)
  const [audioUrl, setAudioUrl] = useState("")
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [levels, setLevels] = useState<number[]>(Array(24).fill(10))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const frameRef = useRef<number | null>(null)

  const selectedLanguage = useMemo(
    () => sarvamLanguages.find((item) => item.code === language)?.name ?? language,
    [language]
  )

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
      streamRef.current?.getTracks().forEach((track) => track.stop())
      if (audioUrl) URL.revokeObjectURL(audioUrl)
    }
  }, [audioUrl])

  function stopTracks() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  async function startRecording() {
    setError("")
    setTranscript("")
    setAudioBlob(null)
    setAudioUrl((current) => {
      if (current) URL.revokeObjectURL(current)
      return ""
    })

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const chunks: BlobPart[] = []
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder
      setDuration(0)
      setStatus("recording")

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" })
        setAudioBlob(blob)
        setAudioUrl(URL.createObjectURL(blob))
        setStatus("recorded")
        stopTracks()
        transcribe(blob)
      }

      recorder.start()
      timerRef.current = setInterval(() => setDuration((value) => value + 1), 1000)
      drawWaveform(stream)
    } catch {
      setError("Microphone permission was denied or no microphone is available. Use text-only intake instead.")
      setMode("text")
      setStatus("idle")
    }
  }

  function drawWaveform(stream: MediaStream) {
    const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) return
    const context = new AudioCtx()
    const analyser = context.createAnalyser()
    analyser.fftSize = 64
    context.createMediaStreamSource(stream).connect(analyser)
    const data = new Uint8Array(analyser.frequencyBinCount)

    const draw = () => {
      analyser.getByteFrequencyData(data)
      setLevels(Array.from(data.slice(0, 24)).map((value) => Math.max(8, Math.round((value / 255) * 56))))
      frameRef.current = requestAnimationFrame(draw)
    }
    draw()
  }

  function stopRecording() {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    if (frameRef.current) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    recorderRef.current?.stop()
  }

  function rerecord() {
    setError("")
    setStatus("idle")
    setAudioBlob(null)
    setTranscript("")
    setDuration(0)
    setAudioUrl((current) => {
      if (current) URL.revokeObjectURL(current)
      return ""
    })
  }

  async function transcribe(blob: Blob) {
    setStatus("transcribing")
    setError("")
    const form = new FormData()
    form.append("file", blob, "case-intake.webm")
    form.append("lang_hint", language)

    try {
      const response = await fetch("/api/voice/transcribe", { method: "POST", body: form })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail ?? "Transcription failed")
      setTranscript(payload?.transcript ?? "")
      setStatus("recorded")
    } catch (err) {
      setStatus("recorded")
      setError(err instanceof Error ? err.message : "Could not transcribe audio. You can type the complaint below.")
    }
  }

  async function submitCase() {
    setError("")
    const narrative = transcript.trim()
    if (mode === "voice" && !audioBlob && !narrative) {
      setError("Record audio or switch to text-only intake before submitting.")
      return
    }
    if (!narrative) {
      setError("The transcript or typed complaint cannot be empty.")
      return
    }
    if (!title.trim()) {
      setError("Add a short case title so the judge can identify this matter later.")
      return
    }

    setSubmitting(true)
    try {
      const response = await fetch("/api/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, caseType, district, state, priority, language, rawInput: narrative, description: narrative }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.error ?? "Could not launch the case")
      router.push(`/cases/${payload.case.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network failure while creating the case.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen bg-[var(--cream)] p-5 md:p-8">
      <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[1fr_360px]">
        <section className="dash-card">
          <div className="ch">
            <div>
              <div className="ct">New Case Intake</div>
              <div className="cs">Record the facts, review the transcript, then launch the agent arena.</div>
            </div>
            <span className="pill pill-blue">{selectedLanguage}</span>
          </div>
          <div className="cb grid gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="form-field m-0">Case title
                <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Police refused to register FIR" />
              </label>
              <label className="form-field m-0">Language
                <select value={language} onChange={(event) => setLanguage(event.target.value)} className="h-11 rounded-[10px] border border-[var(--border)] bg-[var(--cream)] px-3 text-sm">
                  {sarvamLanguages.map((item) => <option key={item.code} value={item.code}>{item.name} ({item.code})</option>)}
                </select>
              </label>
            </div>
            <div className="grid gap-4 md:grid-cols-4">
              <label className="form-field m-0">Case type
                <select value={caseType} onChange={(event) => setCaseType(event.target.value as CaseType)} className="h-11 rounded-[10px] border border-[var(--border)] bg-[var(--cream)] px-3 text-sm">
                  {caseTypes.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
                </select>
              </label>
              <label className="form-field m-0">Priority
                <select value={priority} onChange={(event) => setPriority(event.target.value as CasePriority)} className="h-11 rounded-[10px] border border-[var(--border)] bg-[var(--cream)] px-3 text-sm">
                  {(["low", "medium", "high", "urgent"] as CasePriority[]).map((item) => <option value={item} key={item}>{item}</option>)}
                </select>
              </label>
              <label className="form-field m-0">District
                <input value={district} onChange={(event) => setDistrict(event.target.value)} placeholder="Bhagalpur" />
              </label>
              <label className="form-field m-0">State
                <select value={state} onChange={(event) => setState(event.target.value)} className="h-11 rounded-[10px] border border-[var(--border)] bg-[var(--cream)] px-3 text-sm">
                  {states.map((item) => <option value={item} key={item}>{item}</option>)}
                </select>
              </label>
            </div>

            <div className="flex rounded-[10px] border border-[var(--border)] bg-white p-1">
              {(["voice", "text"] as InputMode[]).map((item) => (
                <button key={item} type="button" onClick={() => setMode(item)} className={`flex-1 rounded-[8px] px-4 py-2 text-sm font-semibold ${mode === item ? "bg-[var(--ink)] text-white" : "text-[var(--muted)]"}`}>
                  {item === "voice" ? "Voice intake" : "Text-only fallback"}
                </button>
              ))}
            </div>

            {mode === "voice" ? (
              <div className="rounded-[12px] border border-[var(--border)] bg-white p-4">
                <div className="flex flex-col gap-4 md:flex-row md:items-center">
                  {status === "recording" ? (
                    <button type="button" className="tbtn dark justify-center" onClick={stopRecording}><IconSquare size={16} /> Stop</button>
                  ) : (
                    <button type="button" className="tbtn dark justify-center" onClick={startRecording} disabled={status === "transcribing"}><IconMicrophone size={16} /> Record</button>
                  )}
                  <div className="flex min-h-16 flex-1 items-end gap-1 rounded-[10px] bg-[var(--cream)] px-3 py-2">
                    {levels.map((height, index) => <span key={index} className="w-full rounded bg-[#b8860b]" style={{ height }} />)}
                  </div>
                  <span className="font-mono text-lg font-semibold">{formatDuration(duration)}</span>
                </div>
                {audioUrl ? (
                  <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
                    <audio className="w-full" controls src={audioUrl} />
                    <button type="button" className="tbtn justify-center" onClick={rerecord}><IconRefresh size={16} /> Re-record</button>
                  </div>
                ) : null}
                {status === "transcribing" ? <p className="mt-3 text-sm text-[var(--muted)]">Transcribing audio...</p> : null}
              </div>
            ) : null}

            <label className="form-field m-0">Editable transcript or typed complaint
              <textarea value={transcript} onChange={(event) => setTranscript(event.target.value)} rows={10} className="rounded-[10px] border border-[var(--border)] bg-[var(--cream)] p-3 text-sm" placeholder="Type or correct the case facts, dates, names, police station, documents, and the relief needed." />
            </label>

            {error ? <div className="rounded-[10px] border border-[#f2b8b5] bg-[#fff1f0] p-3 text-sm text-[#a32d2d]">{error}</div> : null}
            <button type="button" className="tbtn dark justify-center py-3" onClick={submitCase} disabled={submitting || status === "recording" || status === "transcribing"}>
              {submitting ? "Launching agents..." : <><IconSend size={16} /> Submit and Open Arena</>}
            </button>
          </div>
        </section>

        <aside className="dash-card self-start">
          <div className="ch"><div><div className="ct">Intake Checklist</div><div className="cs">Built for the first judge interaction.</div></div></div>
          <div className="cb grid gap-3 text-sm text-[var(--muted)]">
            <p><strong className="text-[var(--ink)]">Language:</strong> Sarvam Saaras v3 codes are used for 22 Indian languages plus English.</p>
            <p><strong className="text-[var(--ink)]">Audio:</strong> Record, stop, playback, re-record, then edit the transcript before launch.</p>
            <p><strong className="text-[var(--ink)]">Fallback:</strong> Text-only mode follows the same validation and submission path.</p>
            <button type="button" className="tbtn justify-center" disabled={!audioUrl}><IconPlayerPlay size={16} /> Playback appears after recording</button>
          </div>
        </aside>
      </div>
    </main>
  )
}
