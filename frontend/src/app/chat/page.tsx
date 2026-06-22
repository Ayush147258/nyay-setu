"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useNyayStore } from "@/store/useNyayStore"
import { chatWithCase } from "@/lib/backend"
import VoiceInput from "@/components/VoiceInput"
import { CASE_TYPE_LABELS, STATUS_CONFIG } from "@/lib/types"

const FREE_LIMIT = 10

const STATUS_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  "bg-gray-500":   { bg: "bg-slate-100", text: "text-slate-600", border: "border-slate-200" },
  "bg-green-600":  { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" },
  "bg-yellow-500": { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  "bg-blue-600":   { bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200" },
}

export default function ChatPage() {
  const router = useRouter()
  const { currentDocument, chatMessages, addMessage, lang, setLang, tier } = useNyayStore()
  const [input, setInput] = useState("")
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!currentDocument) router.replace("/analyze")
  }, [currentDocument, router])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [chatMessages])

  if (!currentDocument) return null

  const doc = currentDocument
  const caseLabel = CASE_TYPE_LABELS[doc.caseType]
  const statusConfig = STATUS_CONFIG[doc.status]
  const statusStyle = STATUS_STYLES[statusConfig.color] || STATUS_STYLES["bg-gray-500"]
  const userMsgCount = chatMessages.filter((m) => m.role === "user").length
  const atLimit = tier === "free" && userMsgCount >= FREE_LIMIT

  async function handleSend() {
    const trimmed = input.trim()
    if (!trimmed || isSending || atLimit) return
    setInput("")
    addMessage({ role: "user", content: trimmed })
    setIsSending(true)
    try {
      const allMsgs = [...chatMessages, { role: "user" as const, content: trimmed }]
      const reply = await chatWithCase(allMsgs, JSON.stringify(doc), lang, tier)
      addMessage({ role: "assistant", content: reply })
    } catch {
      addMessage({ role: "assistant", content: lang === "hi"
        ? "अभी कनेक्शन में समस्या है। कृपया थोड़ी देर बाद पुनः प्रयास करें।"
        : "Connection issue. Please try again in a moment." })
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col relative"
         style={{ background: "linear-gradient(180deg, #fafaf9 0%, #f5f3ff 50%, #fff7ed 100%)" }}>

      {/* Header */}
      <div className="relative z-10 border-b border-slate-200/60 px-4 py-3 flex items-center justify-between"
           style={{ background: "rgba(255,255,255,0.7)", backdropFilter: "blur(20px)" }}>
        <div className="flex items-center gap-3">
          <a href="/result" className="inline-flex items-center gap-1.5 text-slate-400 text-sm hover:text-indigo-600 transition-colors group">
            <svg className="w-4 h-4 group-hover:-translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Result
          </a>
          <div className="h-4 w-px bg-slate-200" />
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-700 font-semibold">{caseLabel.en}</span>
            <span className={`text-xs px-2.5 py-1 rounded-full font-semibold border
              ${statusStyle.bg} ${statusStyle.text} ${statusStyle.border}`}>
              {statusConfig.label}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Lang toggle */}
          <div className="flex gap-1 p-1 rounded-xl bg-slate-100/80">
            {(["hi", "en"] as const).map((l) => (
              <button key={l} onClick={() => setLang(l)}
                className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition-all
                  ${lang === l
                    ? "bg-white text-indigo-600 shadow-sm"
                    : "text-slate-400 hover:text-slate-600"}`}>
                {l === "hi" ? "हिंदी" : "EN"}
              </button>
            ))}
          </div>
          {/* Message counter */}
          {tier === "free" && (
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full
              ${userMsgCount >= FREE_LIMIT - 2
                ? "bg-amber-50 text-amber-600 border border-amber-200"
                : "text-slate-400"}`}>
              {userMsgCount} / {FREE_LIMIT}
            </span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 max-w-3xl mx-auto w-full relative z-10">
        {chatMessages.length === 0 && (
          <div className="text-center py-16">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl flex items-center justify-center text-3xl"
                 style={{ background: "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.08))" }}>
              💬
            </div>
            <p className="text-slate-600 font-semibold mb-1">
              {lang === "hi"
                ? "अपने दस्तावेज़ के बारे में कोई भी सवाल पूछें"
                : "Ask anything about your legal document"}
            </p>
            <p className="text-xs text-slate-400">
              Hindi, English, or Hinglish — we understand all three
            </p>
          </div>
        )}
        {chatMessages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} slide-in`}>
            <div className={`max-w-xs md:max-w-md rounded-2xl px-5 py-3 text-sm leading-relaxed
              ${msg.role === "user"
                ? "rounded-br-md text-white shadow-md"
                : "rounded-bl-md text-slate-700 glass-card"}`}
              style={msg.role === "user"
                ? { background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }
                : undefined}>
              {msg.content}
            </div>
          </div>
        ))}
        {isSending && (
          <div className="flex justify-start">
            <div className="glass-card rounded-2xl rounded-bl-md px-5 py-3.5">
              <div className="flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Limit banner */}
      {atLimit && (
        <div className="relative z-10 px-4 py-3 text-center"
             style={{ background: "linear-gradient(135deg, #fffbeb, #fef3c7)", borderTop: "1px solid #fde68a" }}>
          <p className="text-xs text-amber-700 font-semibold">
            {lang === "hi"
              ? "आपकी 10 free messages समाप्त हो गई हैं।"
              : "Free chat limit reached (10 messages). Upgrade for unlimited chat."}
          </p>
        </div>
      )}

      {/* Input area */}
      <div className="relative z-10 border-t border-slate-200/60 px-4 py-4"
           style={{ background: "rgba(255,255,255,0.7)", backdropFilter: "blur(20px)" }}>
        <div className="max-w-3xl mx-auto flex items-end gap-3">
          <VoiceInput onTranscript={(t) => setInput((p) => p ? p + " " + t : t)}
                      langHint={lang} disabled={isSending || atLimit} />
          <div className="flex-1 glass-card rounded-2xl p-1 transition-all focus-within:shadow-md focus-within:border-indigo-200">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              disabled={isSending || atLimit}
              rows={2}
              placeholder={lang === "hi"
                ? "अपना सवाल यहाँ लिखें... (Enter भेजने के लिए)"
                : "Type your question... (Enter to send)"}
              className={`w-full bg-transparent rounded-xl px-4 py-2.5
                text-slate-700 placeholder-slate-400 text-sm resize-none focus:outline-none
                ${lang === "hi" ? "devanagari" : ""}`}
              style={{ border: "none" }}
            />
          </div>
          <button onClick={handleSend} disabled={isSending || atLimit || !input.trim()}
            className="px-5 py-3 rounded-2xl font-semibold text-sm btn-primary
                       disabled:opacity-50 disabled:cursor-not-allowed transition-all">
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
