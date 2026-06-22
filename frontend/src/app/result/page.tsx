"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useNyayStore } from "@/store/useNyayStore"
import AgentTraceLog from "@/components/AgentTraceLog"
import { CASE_TYPE_LABELS, STATUS_CONFIG } from "@/lib/types"

const STATUS_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  "bg-gray-500":   { bg: "bg-slate-100", text: "text-slate-600", border: "border-slate-200" },
  "bg-green-600":  { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" },
  "bg-yellow-500": { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  "bg-blue-600":   { bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200" },
}

export default function ResultPage() {
  const router = useRouter()
  const { currentDocument, lang } = useNyayStore()
  const [showHindi, setShowHindi] = useState(lang === "hi")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!currentDocument) router.replace("/analyze")
  }, [currentDocument, router])

  if (!currentDocument) return null

  const doc = currentDocument
  const caseLabel = CASE_TYPE_LABELS[doc.caseType]
  const statusConfig = STATUS_CONFIG[doc.status]
  const statusStyle = STATUS_STYLES[statusConfig.color] || STATUS_STYLES["bg-gray-500"]

  function handleCopy() {
    navigator.clipboard.writeText(doc.documentBody)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="min-h-screen relative overflow-hidden"
         style={{ background: "linear-gradient(180deg, #fafaf9 0%, #f5f3ff 50%, #fff7ed 100%)" }}>

      {/* Background orbs */}
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-3" />

      <div className="relative z-10 max-w-6xl mx-auto px-4 py-6">

        {/* Top bar */}
        <div className="flex items-center justify-between mb-8">
          <a href="/analyze" className="inline-flex items-center gap-2 text-slate-400 text-sm hover:text-indigo-600 transition-colors group">
            <svg className="w-4 h-4 group-hover:-translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            New Case
          </a>
          <div className="flex items-center gap-3">
            <span className={`text-xs px-3 py-1.5 rounded-full font-semibold border
              ${statusStyle.bg} ${statusStyle.text} ${statusStyle.border}`}>
              {statusConfig.label}
            </span>
            <span className="text-xs text-slate-400">
              {doc.processingTimeMs ? `${(doc.processingTimeMs / 1000).toFixed(1)}s` : ""}
              {doc.providerUsed ? ` · ${doc.providerUsed}` : ""}
            </span>
          </div>
        </div>

        {/* 2-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">

          {/* LEFT — Case info */}
          <div className="lg:col-span-1 space-y-5">

            {/* Case type card */}
            <div className="glass-card rounded-2xl p-6">
              <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-2">Case Type</div>
              <div className="font-bold text-slate-800 text-lg mb-0.5">{caseLabel.en}</div>
              <div className="text-slate-400 text-sm devanagari mb-4">{caseLabel.hi}</div>
              {/* Confidence bar */}
              <div className="space-y-1.5">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-500">Confidence</span>
                  <span className="text-xs font-bold text-indigo-600">{(doc.confidenceScore * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all duration-1000"
                       style={{
                         width: `${doc.confidenceScore * 100}%`,
                         background: "linear-gradient(90deg, #6366f1, #8b5cf6)"
                       }} />
                </div>
              </div>
            </div>

            {/* Applicable laws */}
            {doc.applicableSections.length > 0 && (
              <div className="glass-card rounded-2xl p-6">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                  Applicable Laws
                </div>
                <ul className="space-y-2">
                  {doc.applicableSections.map((s) => (
                    <li key={s} className="text-xs flex items-center gap-2.5 py-1.5 px-3 rounded-lg bg-indigo-50/50">
                      <span className="text-indigo-500">⚖</span>
                      <span className="text-indigo-700 font-medium">{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Required documents */}
            {doc.requiredDocuments.length > 0 && (
              <div className="glass-card rounded-2xl p-6">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                  Required Documents
                </div>
                <ul className="space-y-2">
                  {doc.requiredDocuments.map((d) => (
                    <li key={d} className="text-xs text-slate-600 flex items-start gap-2.5">
                      <span className="mt-0.5 w-4 h-4 rounded border border-slate-300 flex-shrink-0 flex items-center justify-center">
                        <span className="w-1.5 h-1.5 rounded-sm bg-slate-300" />
                      </span>
                      {d}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Filing instructions */}
            {doc.filingInstructions && (
              <div className="rounded-2xl p-6"
                   style={{ background: "linear-gradient(135deg, #eff6ff, #dbeafe)", border: "1px solid #bfdbfe" }}>
                <div className="text-xs font-semibold text-blue-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <span>📍</span> Where to File
                </div>
                <p className="text-xs text-blue-800 leading-relaxed">{doc.filingInstructions}</p>
              </div>
            )}
          </div>

          {/* CENTER — Document viewer */}
          <div className="lg:col-span-2 space-y-5">

            {/* Document */}
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200/60">
                <h2 className="text-sm font-bold text-slate-800 truncate">{doc.documentTitle}</h2>
                <div className="flex gap-2 shrink-0">
                  {doc.documentBodyHindi && (
                    <button onClick={() => setShowHindi(!showHindi)}
                      className="text-xs px-4 py-2 rounded-xl btn-outline font-semibold">
                      {showHindi ? "EN" : "हिंदी"}
                    </button>
                  )}
                  <button onClick={handleCopy}
                    className="text-xs px-4 py-2 rounded-xl btn-outline font-semibold">
                    {copied ? "✓ Copied" : "📋 Copy"}
                  </button>
                  <button onClick={() => window.print()}
                    className="text-xs px-4 py-2 rounded-xl btn-primary font-semibold no-print">
                    📥 Download PDF
                  </button>
                </div>
              </div>
              <div className="p-6 print-document">
                <pre className="whitespace-pre-wrap font-mono text-xs text-slate-700 leading-relaxed">
                  {showHindi && doc.documentBodyHindi ? doc.documentBodyHindi : doc.documentBody}
                </pre>
              </div>
            </div>

            {/* Summary */}
            {doc.summary && (
              <div className="glass-card rounded-2xl p-6">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-500" />
                  Summary
                </div>
                <p className="text-sm text-slate-600 leading-relaxed">
                  {lang === "hi" && doc.summaryHindi ? doc.summaryHindi : doc.summary}
                </p>
              </div>
            )}

            {/* Unresolved gaps warning */}
            {doc.unresolvedGaps.length > 0 && (
              <div className="rounded-2xl p-6"
                   style={{ background: "linear-gradient(135deg, #fffbeb, #fef3c7)", border: "1px solid #fde68a" }}>
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xl">⚠️</span>
                  <span className="text-sm font-bold text-amber-800">
                    {doc.unresolvedGaps.length} gap{doc.unresolvedGaps.length > 1 ? "s" : ""} need your input
                  </span>
                </div>
                <ul className="space-y-3">
                  {doc.unresolvedGaps.map((gap) => (
                    <li key={gap.field} className="text-xs bg-white/60 rounded-xl p-3">
                      <div className="text-amber-800 font-semibold mb-0.5">{gap.description}</div>
                      <div className="text-amber-600">→ {gap.howToFix}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* Agent trace log */}
        <div className="mb-8">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
            ⚔️ Adversarial Debate Trace
          </h3>
          <AgentTraceLog debateRounds={doc.debateRounds} mediatorOverride={doc.mediatorOverrideTriggered} />
        </div>

        {/* Next steps */}
        {doc.nextSteps.length > 0 && (
          <div className="glass-card rounded-2xl p-6 mb-8">
            <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Next Steps
            </h3>
            <ol className="space-y-3">
              {doc.nextSteps.map((step, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-slate-600">
                  <span className="text-xs font-bold text-white px-2 py-0.5 rounded-lg shrink-0 mt-0.5"
                        style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}>
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Chat CTA */}
        <div className="text-center pb-8">
          <button onClick={() => router.push("/chat")}
            className="px-8 py-4 rounded-2xl font-bold text-base btn-primary
                       inline-flex items-center gap-2">
            💬 Chat About This Document
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
