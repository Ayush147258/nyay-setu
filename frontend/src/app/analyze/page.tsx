"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useNyayStore } from "@/store/useNyayStore"
import { analyzeCase } from "@/lib/backend"
import VoiceInput from "@/components/VoiceInput"

const STEPS = [
  { icon: "🔍", text: "Classifying your case...", color: "#6366f1" },
  { icon: "📚", text: "Searching legal precedents...", color: "#f97316" },
  { icon: "⚖️", text: "Advocate Agent drafting document...", color: "#10b981" },
  { icon: "⚔️", text: "Adversarial Agent checking for gaps...", color: "#ef4444" },
  { icon: "✅", text: "Mediator compiling final document...", color: "#8b5cf6" },
]

const EXAMPLES = [
  { text: "Police ne meri FIR nahi ki", icon: "🚔" },
  { text: "Fasal beema reject ho gaya", icon: "🌾" },
  { text: "Baadh mein ghar toota, muavza nahi mila", icon: "🏠" },
  { text: "Dukan se kharab saman mila", icon: "🏪" },
]

export default function AnalyzePage() {
  const router = useRouter()
  const { lang, setLang, setDocument, setAnalyzing, tier } = useNyayStore()
  const [text, setText] = useState("")
  const [isAnalyzing, setIsAnalyzingLocal] = useState(false)
  const [stepIdx, setStepIdx] = useState(0)
  const [error, setError] = useState("")
  const [backendReady, setBackendReady] = useState<boolean | null>(null)

  // Warm-up HF Spaces on mount
  useEffect(() => {
    const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ""
    fetch(`${BACKEND}/api/health`, { signal: AbortSignal.timeout(6000) })
      .then((r) => setBackendReady(r.ok))
      .catch(() => setBackendReady(false))
  }, [])

  // Animate steps during analysis
  useEffect(() => {
    if (!isAnalyzing) { setStepIdx(0); return }
    const interval = setInterval(() => {
      setStepIdx((i) => (i < STEPS.length - 1 ? i + 1 : i))
    }, 1200)
    return () => clearInterval(interval)
  }, [isAnalyzing])

  async function handleAnalyze() {
    if (!text.trim() || text.trim().length < 10) {
      setError("Please describe your issue in at least 10 characters.")
      return
    }
    setError("")
    setIsAnalyzingLocal(true)
    setAnalyzing(true)
    try {
      const doc = await analyzeCase(text, lang, tier)
      setDocument(doc)
      router.push("/result")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed. Please try again.")
    } finally {
      setIsAnalyzingLocal(false)
      setAnalyzing(false)
    }
  }

  return (
    <div className="app-shell min-h-screen relative overflow-hidden">

      <div className="relative z-10 max-w-2xl mx-auto px-4 py-8">

        {/* Back + Logo */}
        <div className="flex items-center justify-between mb-8">
          <a href="/" className="inline-flex items-center gap-2 text-[var(--text-secondary)] text-sm hover:text-[var(--gold-primary)] transition-colors group">
            <svg className="w-4 h-4 group-hover:-translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back
          </a>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
                 style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}>
              ⚖️
            </div>
            <span className="font-display font-bold text-[var(--gold-primary)]">NyaySetu</span>
          </div>
        </div>

        {/* Title */}
        <div className="text-center mb-8 fade-up">
          <h1 className="text-3xl font-extrabold text-slate-800 mb-2">
            Describe Your Legal Issue
          </h1>
          <p className="text-slate-500 text-sm">
            Speak or type in Hindi, English, or Hinglish — we understand all three
          </p>
        </div>

        {/* Cold-start warning */}
        {backendReady === false && (
          <div className="mb-5 rounded-2xl px-5 py-4 flex items-center gap-3 text-sm"
               style={{ background: "linear-gradient(135deg, #fffbeb, #fef3c7)", border: "1px solid #fde68a" }}>
            <span className="text-xl">🔄</span>
            <span className="text-amber-700">AI is warming up — first analysis may take ~30 seconds.</span>
          </div>
        )}

        {/* Language toggle */}
        <div className="flex gap-2 mb-5 fade-up fade-up-delay-1">
          <button onClick={() => setLang("hi")}
            className={`px-5 py-2 rounded-xl text-sm font-semibold transition-all devanagari
              ${lang === "hi"
                ? "btn-primary shadow-md"
                : "btn-outline"}`}>
            हिंदी
          </button>
          <button onClick={() => setLang("en")}
            className={`px-5 py-2 rounded-xl text-sm font-semibold transition-all
              ${lang === "en"
                ? "btn-primary shadow-md"
                : "btn-outline"}`}>
            English
          </button>
        </div>

        {/* Textarea Card */}
        <div className="fade-up fade-up-delay-2 glass-card rounded-2xl p-1 mb-5">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={isAnalyzing}
            rows={6}
            placeholder={lang === "hi"
              ? "अपनी समस्या बताएं... जैसे: 'पुलिस ने मेरी FIR दर्ज नहीं की' या 'फसल बीमा reject हो गया'"
              : "Describe your legal issue... e.g. 'Police refused to register my FIR' or 'Crop insurance claim rejected'"}
            className={`w-full bg-transparent rounded-xl px-5 py-4 text-slate-700
              placeholder-slate-400 text-sm resize-none focus:outline-none
              transition-colors ${lang === "hi" ? "devanagari" : ""}`}
            style={{ border: "none" }}
          />
        </div>

        {/* Voice + char count */}
        <div className="flex items-center justify-between mb-5">
          <VoiceInput onTranscript={(t) => setText((prev) => prev ? prev + " " + t : t)} langHint={lang} disabled={isAnalyzing} />
          <span className="text-xs text-slate-400 font-medium">{text.length} / 5,000</span>
        </div>

        {/* Example chips */}
        <div className="flex flex-wrap gap-2 mb-6 fade-up fade-up-delay-3">
          {EXAMPLES.map((ex) => (
            <button key={ex.text} onClick={() => setText(ex.text)}
              className="inline-flex items-center gap-1.5 text-xs px-4 py-2 rounded-full glass-card
                         text-slate-600 hover:text-indigo-600 hover:border-indigo-200 transition-all cursor-pointer">
              <span>{ex.icon}</span>
              {ex.text}
            </button>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-5 rounded-2xl px-5 py-4 flex items-center gap-3 text-sm"
               style={{ background: "linear-gradient(135deg, #fef2f2, #fee2e2)", border: "1px solid #fecaca" }}>
            <span className="text-xl">⚠️</span>
            <span className="text-red-700">{error}</span>
          </div>
        )}

        {/* Analyze button */}
        <button onClick={handleAnalyze} disabled={isAnalyzing || !text.trim()}
          className="w-full py-4 rounded-2xl font-bold text-base btn-primary
                     disabled:opacity-50 disabled:cursor-not-allowed transition-all
                     flex items-center justify-center gap-2">
          {isAnalyzing ? (
            <>
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              Analyze My Case
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </>
          )}
        </button>

        {/* Agent trace log (loading animation) */}
        {isAnalyzing && (
          <div className="mt-6 glass-card rounded-2xl p-6 space-y-3 slide-in">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
              Agent Pipeline
            </p>
            {STEPS.map((step, i) => (
              <div key={i} className={`flex items-center gap-3 text-sm transition-all duration-300
                ${i < stepIdx ? "text-emerald-600" : i === stepIdx ? "text-indigo-600" : "text-slate-300"}`}>
                {i < stepIdx ? (
                  <div className="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center">
                    <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                ) : i === stepIdx ? (
                  <div className="w-6 h-6 rounded-full flex items-center justify-center"
                       style={{ background: `${step.color}15` }}>
                    <span className="w-3 h-3 border-2 rounded-full animate-spin"
                          style={{ borderColor: `${step.color}30`, borderTopColor: step.color }} />
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center">
                    <span className="w-2 h-2 rounded-full bg-slate-300" />
                  </div>
                )}
                <span className="font-medium">{step.icon} {step.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
