"use client"

import { create } from "zustand"
import type { LegalDocument, ChatMessage } from "@/lib/types"

interface NyayStore {
  currentDocument: LegalDocument | null
  chatMessages: ChatMessage[]
  isAnalyzing: boolean
  lang: "en" | "hi"
  tier: "free" | "premium"
  setDocument: (doc: LegalDocument) => void
  addMessage: (msg: ChatMessage) => void
  setAnalyzing: (v: boolean) => void
  setLang: (l: "en" | "hi") => void
  setTier: (t: "free" | "premium") => void
  reset: () => void
}

export const useNyayStore = create<NyayStore>((set) => ({
  currentDocument: null,
  chatMessages: [],
  isAnalyzing: false,
  lang: "hi",
  tier: "free",
  setDocument: (doc) => set({ currentDocument: doc }),
  addMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  setAnalyzing: (v) => set({ isAnalyzing: v }),
  setLang: (l) => set({ lang: l }),
  setTier: (t) => set({ tier: t }),
  reset: () => set({ currentDocument: null, chatMessages: [] }),
}))
