// src/lib/types.ts
// Shared TypeScript types — mirror the backend Pydantic models exactly.
// snake_case fields are converted to camelCase by snakeToCamel() in backend.ts.

export type CaseType =
  | "fir_refusal"
  | "crop_insurance"
  | "flood_relief"
  | "wage_theft"
  | "rti_request"
  | "consumer_complaint"
  | "land_dispute"
  | "domestic_violence"
  | "labour_complaint"
  | "unknown"

export type DocumentStatus = "draft" | "hardened" | "annotated" | "filed"

export type UserTier = "free" | "premium"

export type Language = "en" | "hi" | "hinglish" | "bhojpuri" | "maithili" | "other"

// ─────────────────────────────────────────────────────────────
// Evidentiary mapping (README upgrade #2)
// ─────────────────────────────────────────────────────────────

export interface LegalPoint {
  argument: string
  statuteCited: string           // "Section 154 CrPC"
  sourceVerificationUrl: string  // live IndianKanoon link
  confidence: number
}

// ─────────────────────────────────────────────────────────────
// Debate models
// ─────────────────────────────────────────────────────────────

export interface DebateRound {
  roundNumber: number
  advocateDraft: string
  advocatePoints: LegalPoint[]
  bureaucratObjections: string[]
  objectionSeverity: string[]   // "critical" | "moderate" | "minor"
  mediatorVerdict: string
  patchApplied: boolean
  patchedDraft: string
}

export interface UnresolvedGap {
  field: string
  description: string
  howToFix: string
}

// ─────────────────────────────────────────────────────────────
// Core legal document
// ─────────────────────────────────────────────────────────────

export interface LegalDocument {
  caseType: CaseType
  documentTitle: string
  documentBody: string
  documentBodyHindi: string

  // Adversarial trace — shown in AgentTraceLog
  debateRounds: DebateRound[]
  totalRounds: number
  mediatorOverrideTriggered: boolean
  unresolvedGaps: UnresolvedGap[]

  // Legal context
  applicableSections: string[]
  authorityToFile: string
  filingInstructions: string
  filingInstructionsHindi: string
  requiredDocuments: string[]

  // Status
  status: DocumentStatus
  confidenceScore: number

  // AI-generated
  summary: string
  summaryHindi: string
  nextSteps: string[]
  lawyerNote: string  // premium only

  // Metadata
  tierUsed: UserTier
  processingTimeMs: number | null
  providerUsed: string
  sessionId: string
}

// ─────────────────────────────────────────────────────────────
// Chat
// ─────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

// ─────────────────────────────────────────────────────────────
// API request / response helpers
// ─────────────────────────────────────────────────────────────

export interface AnalyzeParams {
  text: string
  lang: Language | string
  tier: UserTier
  userName?: string
  userLocation?: string
}

export interface ChatParams {
  messages: ChatMessage[]
  documentData: string  // JSON.stringify(LegalDocument)
  lang: string
  tier: UserTier
}

// Case display labels (for UI)
export const CASE_TYPE_LABELS: Record<CaseType, { en: string; hi: string }> = {
  fir_refusal:        { en: "Police FIR Refusal",         hi: "पुलिस FIR दर्ज न करना" },
  crop_insurance:     { en: "Crop Insurance (PMFBY)",      hi: "फसल बीमा दावा (PMFBY)" },
  flood_relief:       { en: "Flood / Disaster Relief",     hi: "बाढ़ / आपदा राहत" },
  wage_theft:         { en: "Unpaid Wages",                hi: "तनख्वाह नहीं मिली" },
  rti_request:        { en: "RTI Request",                 hi: "सूचना का अधिकार" },
  consumer_complaint: { en: "Consumer Complaint",          hi: "उपभोक्ता शिकायत" },
  land_dispute:       { en: "Land / Property Dispute",     hi: "जमीन विवाद" },
  domestic_violence:  { en: "Domestic Violence",           hi: "घरेलू हिंसा" },
  labour_complaint:   { en: "Labour Rights Violation",     hi: "श्रम अधिकार उल्लंघन" },
  unknown:            { en: "General Legal Issue",         hi: "सामान्य कानूनी मुद्दा" },
}

export const STATUS_CONFIG: Record<DocumentStatus, { label: string; color: string }> = {
  draft:     { label: "Draft",    color: "bg-gray-500" },
  hardened:  { label: "Hardened", color: "bg-green-600" },
  annotated: { label: "Review",   color: "bg-yellow-500" },
  filed:     { label: "Filed",    color: "bg-blue-600" },
}
