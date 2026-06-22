"use client"

import { useState } from "react"
import type { DebateRound } from "@/lib/types"

interface AgentTraceLogProps {
  debateRounds: DebateRound[]
  mediatorOverride: boolean
}

export default function AgentTraceLog({ debateRounds, mediatorOverride }: AgentTraceLogProps) {
  const [openRound, setOpenRound] = useState<number | null>(0)

  if (!debateRounds || debateRounds.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-6 text-center text-slate-400 text-sm">
        No debate rounds recorded — document was generated deterministically.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Mediator override banner */}
      {mediatorOverride && (
        <div className="rounded-2xl px-5 py-4 flex items-start gap-3"
             style={{ background: "linear-gradient(135deg, #fffbeb, #fef3c7)", border: "1px solid #fde68a" }}>
          <span className="text-xl mt-0.5">⚠️</span>
          <div>
            <p className="text-amber-800 font-bold text-sm">Mediator Override Activated</p>
            <p className="text-amber-600 text-xs mt-0.5">
              Maximum 2 debate rounds reached. Document compiled with annotations — check unresolved gaps below.
            </p>
          </div>
        </div>
      )}

      {/* Rounds */}
      {debateRounds.map((round, idx) => {
        const isOpen = openRound === idx

        return (
          <div key={idx}
               className={`glass-card rounded-2xl overflow-hidden transition-all slide-in
                 ${isOpen ? "shadow-lg" : ""}`}
               style={isOpen ? { borderColor: "rgba(99,102,241,0.2)" } : undefined}>

            {/* Header — clickable */}
            <button
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-indigo-50/30 transition-colors"
              onClick={() => setOpenRound(isOpen ? null : idx)}
            >
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-100 text-slate-500">
                  Round {round.roundNumber}
                </span>
                <span className={`text-xs font-bold px-3 py-1 rounded-full border
                  ${round.patchApplied
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : round.bureaucratObjections.length === 0
                    ? "bg-blue-50 text-blue-700 border-blue-200"
                    : "bg-red-50 text-red-700 border-red-200"}`}>
                  {round.patchApplied ? "✓ Patched" : round.bureaucratObjections.length === 0 ? "✓ Clean" : "⚠ Unresolved"}
                </span>
                {round.bureaucratObjections.length > 0 && (
                  <span className="text-xs text-slate-400 font-medium">
                    {round.bureaucratObjections.length} objection{round.bureaucratObjections.length > 1 ? "s" : ""}
                  </span>
                )}
              </div>
              <svg className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
                   fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Body */}
            {isOpen && (
              <div className="px-5 pb-5 border-t border-slate-100 pt-4 space-y-4">

                {/* Advocate draft */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                    <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider">⚖️ Advocate Draft</span>
                  </div>
                  <div className="rounded-xl p-4 text-xs text-slate-600 font-mono leading-relaxed"
                       style={{ background: "linear-gradient(135deg, #f8fafc, #f1f5f9)" }}>
                    {round.advocateDraft.slice(0, 200)}
                    {round.advocateDraft.length > 200 && (
                      <span className="text-slate-400"> ...({round.advocateDraft.length} chars total)</span>
                    )}
                  </div>
                </div>

                {/* Bureaucrat objections */}
                {round.bureaucratObjections.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                      <span className="text-xs font-bold text-red-600 uppercase tracking-wider">⚔️ Adversarial Findings</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {round.bureaucratObjections.map((obj, i) => (
                        <span key={i}
                              className="text-xs px-3 py-1.5 rounded-full font-medium
                                         bg-red-50 text-red-700 border border-red-200">
                          {obj}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Mediator verdict */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">🏛️ Mediator Verdict</span>
                  </div>
                  <p className="text-xs text-emerald-800 rounded-xl px-4 py-3 leading-relaxed"
                     style={{ background: "linear-gradient(135deg, #ecfdf5, #d1fae5)", border: "1px solid #a7f3d0" }}>
                    {round.mediatorVerdict || "Mediator compiled the document."}
                  </p>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
