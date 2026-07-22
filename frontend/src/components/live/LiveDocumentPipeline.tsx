"use client"

import { useCallback, useEffect, useMemo, useRef, useState, type WheelEvent } from "react"
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  Clock3,
  Database,
  FileCheck2,
  GitBranch,
  FileText,
  Lightbulb,
  Loader2,
  MessageSquare,
  Play,
  RefreshCw,
  SearchCheck,
  Sparkles,
  SendHorizontal,
  ShieldCheck,
  Workflow,
  UploadCloud,
} from "lucide-react"

import styles from "./LiveDocumentPipeline.module.css"

type Role = "lawyer" | "judge" | "citizen"
type ApiRole = "lawyer" | "judge" | "analyst"

type DocumentVersion = {
  document_id: string
  version_id: string
  original_name: string
  media_type: string
  document_format: string
  sha256: string
  size_bytes: number
  status: string
  parser_name: string
  warnings: string[]
  created_at: string
}

type Evidence = {
  evidence_id: string
  kind: string
  label: string
  value: string
  confidence: number
  review_state: string
  source_spans: Array<{ exact_quote: string; page_number: number; block_id: string }>
}

type Citation = {
  citation_id: string
  display_label: string
  source_type?: "uploaded_evidence" | "external_authority" | null
  source_url?: string | null
  source_span?: { exact_quote: string; page_number: number; block_id: string } | null
}

type AgentTraceStep = {
  agent: string
  status: "complete" | "needs_review"
  summary: string
}

type CaseChatResponse = {
  answer: string
  citations: Citation[]
  caveats: string[]
  next_actions?: string[]
  agent_trace?: AgentTraceStep[]
  role: ApiRole
}

type ChatTurn = {
  id: string
  role: "user" | "assistant"
  content: string
  citations?: Citation[]
  caveats?: string[]
  nextActions?: string[]
  agentTrace?: AgentTraceStep[]
  targetDocuments?: DocumentVersion[]
}

type ReportClaim = {
  claim_id: string
  statement: string
  kind: string
  confidence: number
  caveat?: string | null
}

type Report = {
  report_id: string
  version: number
  title: string
  status: string
  sections: Array<{ section_id: string; title: string; claims: ReportClaim[] }>
  timeline: Array<{ event_id: string; date_text: string; normalized_date?: string | null; description: string; confidence: number }>
  caveats: Array<{ caveat_id: string; severity: "info" | "warning" | "blocking"; title: string; detail: string }>
  created_at: string
}

type Integrity = {
  valid: boolean
  issues: Array<{ code: string; severity: "warning" | "blocking"; message: string }>
  checked_claims: number
  checked_evidence: number
  checked_spans: number
}

type Job = {
  job_id: string
  status: string
  attempts: number
  max_attempts: number
  report_id?: string | null
  error?: { message?: string } | null
  updated_at: string
}

type JobEvent = {
  sequence: number
  event_type: string
  status: string
  agent?: string | null
  message: string
  created_at: string
}

type Workspace = {
  documents: DocumentVersion[]
  jobs: Job[]
  reports: Report[]
  latest_report: Report | null
  evidence: Evidence[]
  integrity: Integrity | null
  review_items: Array<{ review_id: string; severity: "warning" | "blocking"; reason: string; status: string }>
}

type UploadRow = {
  id: string
  file: File
  state: "queued" | "uploading" | "ready" | "partial" | "failed"
  detail: string
}

const terminalStatuses = new Set(["completed", "needs_review", "failed", "cancelled"])
const eventNames = ["queued", "claimed", "stage", "completed", "failed", "retry_scheduled", "manual_retry", "cancelled"]

const copy: Record<Role, { title: string; subtitle: string; run: string; final: string; apiRole: ApiRole }> = {
  lawyer: {
    title: "Live counsel pipeline",
    subtitle: "Upload pleadings, run extraction, verify weak points, and generate a counsel-facing final answer.",
    run: "Run counsel analysis",
    final: "Lawyer final answer",
    apiRole: "lawyer",
  },
  judge: {
    title: "Live bench pipeline",
    subtitle: "Upload a case bundle, trace every claim to source spans, and produce neutral bench observations.",
    run: "Run bench analysis",
    final: "Judge final answer",
    apiRole: "judge",
  },
  citizen: {
    title: "Live citizen pipeline",
    subtitle: "Upload papers, watch the agents read them, and receive a simple next-step answer grounded in the record.",
    run: "Check my papers",
    final: "Citizen final answer",
    apiRole: "analyst",
  },
}

function label(value?: string | null) {
  return (value || "idle").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function fileSize(bytes: number) {
  if (!Number.isFinite(bytes)) return "Unknown size"
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function responseError(response: Response) {
  if (response.status === 401) return "Sign in to use the live document backend."
  if (response.status === 503) return "The document intelligence backend is not configured or is unavailable."
  const payload = await response.json().catch(() => ({})) as { detail?: string; error?: string }
  return payload.detail || payload.error || `Request failed with status ${response.status}`
}

function flattenClaims(report: Report | null) {
  return report?.sections.flatMap((section) => section.claims.map((claim) => ({ ...claim, section: section.title }))) ?? []
}

function withDemo(url: string, demo: boolean) {
  return demo ? `${url}${url.includes("?") ? "&" : "?"}demo=1` : url
}

function emptyWorkspace(documents: DocumentVersion[] = [], jobs: Job[] = []): Workspace {
  return {
    documents,
    jobs,
    reports: [],
    latest_report: null,
    evidence: [],
    integrity: null,
    review_items: [],
  }
}

function fileFormat(file: File) {
  const suffix = file.name.split(".").pop()?.toLowerCase()
  return suffix || "document"
}

function cleanPreview(value: string, fallback: string) {
  const cleaned = value.replace(/\0/g, " ").replace(/\s+/g, " ").trim()
  if (!cleaned) return fallback
  return cleaned.length > 420 ? `${cleaned.slice(0, 417).trim()}...` : cleaned
}

function decodePdfLiteral(value: string) {
  return value
    .replace(/\\n/g, " ")
    .replace(/\\r/g, " ")
    .replace(/\\t/g, " ")
    .replace(/\\\(/g, "(")
    .replace(/\\\)/g, ")")
    .replace(/\\\\/g, "\\")
    .replace(/\\[0-7]{1,3}/g, " ")
}

async function extractDemoPreview(file: File) {
  const lowerName = file.name.toLowerCase()
  const fallback = `Uploaded source file preserved for this demo: ${file.name}. Sign in for backend OCR and exact PDF text extraction.`

  try {
    if (file.type.startsWith("text/") || /\.(txt|md|csv|json|eml|html?)$/.test(lowerName)) {
      return cleanPreview(await file.text(), fallback)
    }

    if (file.type === "application/pdf" || lowerName.endsWith(".pdf")) {
      const raw = new TextDecoder("windows-1252").decode(await file.slice(0, 600000).arrayBuffer())
      const candidates = Array.from(raw.matchAll(/\(([^()]{24,260})\)/g))
        .map((match) => cleanPreview(decodePdfLiteral(match[1]), ""))
        .filter((candidate) => {
          const letters = candidate.match(/[A-Za-z]/g)?.length ?? 0
          return letters >= 12 && !/^(obj|endobj|stream|xref|trailer)$/i.test(candidate)
        })
      return cleanPreview(candidates.slice(0, 4).join(" "), fallback)
    }
  } catch {
    return fallback
  }

  return fallback
}

function demoDocument(row: UploadRow, preview = ""): DocumentVersion {
  const id = crypto.randomUUID()
  return {
    document_id: id,
    version_id: crypto.randomUUID(),
    original_name: row.file.name,
    media_type: row.file.type || "application/octet-stream",
    document_format: fileFormat(row.file),
    sha256: id.replaceAll("-", "").padEnd(64, "0").slice(0, 64),
    size_bytes: row.file.size,
    status: "ready",
    parser_name: row.file.name.toLowerCase().endsWith(".pdf") ? "demo-pdf-preview" : "demo-file-preview",
    warnings: preview ? [preview] : [],
    created_at: new Date().toISOString(),
  }
}

function roleEvidenceValue(role: Role, document: DocumentVersion, quote: string) {
  if (role === "judge") return `Bench view is tied to ${document.original_name}. The cited span is treated as the record anchor: ${quote}`
  if (role === "lawyer") return `Counsel view is tied to ${document.original_name}. Use this cited span as the argument anchor and check whether every claim has matching proof: ${quote}`
  return `Plain-language view is tied to ${document.original_name}. This is the part of the record being used to explain the next step: ${quote}`
}

function demoEvidence(role: Role, documents: DocumentVersion[] = []): Evidence[] {
  if (documents.length) {
    const sourceEvidence: Evidence[] = documents.slice(0, 3).map((document, index) => {
      const quote = cleanPreview(
        document.warnings[0] ?? "",
        `Uploaded source file preserved: ${document.original_name}. Exact page text will be extracted by the live backend after sign-in.`,
      )
      return {
        evidence_id: crypto.randomUUID(),
        kind: document.document_format === "pdf" ? "pdf_source" : "document_source",
        label: `${document.original_name} - page ${index + 1}`,
        value: roleEvidenceValue(role, document, quote),
        confidence: document.warnings[0]?.startsWith("Uploaded source file preserved") ? 0.7 : 0.9,
        review_state: "verified",
        source_spans: [{ exact_quote: quote, page_number: index + 1, block_id: `demo-${document.document_id}` }],
      }
    })

    return [
      ...sourceEvidence,
      {
        evidence_id: crypto.randomUUID(),
        kind: "review_gap",
        label: "Reviewer gap from uploaded record",
        value: "The reviewer will attack any legal conclusion that is not tied back to a visible page, annexure, date, signature, receipt, or order-sheet entry.",
        confidence: 0.86,
        review_state: "verified",
        source_spans: [{ exact_quote: "Every final answer must remain tied to the source cards above.", page_number: 1, block_id: "demo-review-gap" }],
      },
    ]
  }

  const emphasis = role === "judge" ? "neutral chronology" : role === "lawyer" ? "argument risk" : "plain-language next step"
  return [
    {
      evidence_id: crypto.randomUUID(),
      kind: "sample_source",
      label: "Sample record - page 1",
      value: `Demo extractor prepared ${emphasis} evidence for review. Upload a PDF to replace this sample with file-specific source cards.`,
      confidence: 0.78,
      review_state: "verified",
      source_spans: [{ exact_quote: "Sample source span shown until a document is uploaded.", page_number: 1, block_id: "demo-block-1" }],
    },
    {
      evidence_id: crypto.randomUUID(),
      kind: "review_gap",
      label: "Follow-up required",
      value: "Reviewer recommends attaching any missing annexure or receipt before relying on the final answer.",
      confidence: 0.84,
      review_state: "verified",
      source_spans: [{ exact_quote: "Reviewer note: missing proof should be collected before filing.", page_number: 1, block_id: "demo-block-2" }],
    },
  ]
}

function demoReport(role: Role, documents: DocumentVersion[] = []): Report {
  const sourceName = documents[0]?.original_name ?? "the uploaded record"
  const statement = role === "judge"
    ? `The record from ${sourceName} is ready for a preliminary bench-style review, with source cards separated from caveats.`
    : role === "lawyer"
      ? `The counsel answer should cite ${sourceName}, lead with verified facts, and flag any proof gap before final filing.`
      : `Your papers in ${sourceName} have been read in demo mode. Keep copies, attach missing proof, and ask for filing guidance.`

  return {
    report_id: crypto.randomUUID(),
    version: 1,
    title: "Demo document intelligence report",
    status: "completed",
    sections: [
      {
        section_id: "demo-section-1",
        title: "Final answer",
        claims: [
          {
            claim_id: crypto.randomUUID(),
            statement,
            kind: "recommendation",
            confidence: 0.88,
            caveat: "Demo output is not legal advice.",
          },
        ],
      },
    ],
    timeline: [],
    caveats: [
      {
        caveat_id: crypto.randomUUID(),
        severity: "info",
        title: "Demo mode",
        detail: "This is a local demo pipeline and does not store documents in a real user workspace.",
      },
    ],
    created_at: new Date().toISOString(),
  }
}

function demoIntegrity(): Integrity {
  return {
    valid: true,
    issues: [],
    checked_claims: 1,
    checked_evidence: 2,
    checked_spans: 2,
  }
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

const suggestedQuestions: Record<Role, string[]> = {
  lawyer: [
    "What is the strongest argument from this record?",
    "What proof is missing before filing?",
    "What weak point will the other side attack?",
  ],
  judge: [
    "What facts are supported by source spans?",
    "What caveats should the bench notice?",
    "Which issues need clarification from parties?",
  ],
  citizen: [
    "What does this document mean for me?",
    "What should I do next?",
    "What should I ask my lawyer or court clerk?",
  ],
}

const roleNextActions: Record<Role, string[]> = {
  lawyer: ["Check cited source cards", "Draft argument around verified facts", "Collect missing proof before export"],
  judge: ["Review caveats separately", "Check source span cards", "List questions for parties"],
  citizen: ["Keep copies of all papers", "Ask for missing receipt or order sheet", "Do not treat demo output as legal advice"],
}

const finalAgentName: Record<Role, string> = {
  lawyer: "Lawyer final agent",
  judge: "Judge final agent",
  citizen: "Citizen final agent",
}

function fallbackAgentTrace(role: Role, citations: Citation[] = [], caveats: string[] = []): AgentTraceStep[] {
  const needsReview = citations.length < 2 || caveats.length > 1
  return [
    {
      agent: "Query router",
      status: "complete",
      summary: `Routed the question to the ${role} answer lens.`,
    },
    {
      agent: "Extractor agent",
      status: citations.length ? "complete" : "needs_review",
      summary: citations.length
        ? `Selected ${citations.length} source card(s) from the uploaded record.`
        : "No usable source card was returned for this question.",
    },
    {
      agent: "Synthesis agent",
      status: citations.length ? "complete" : "needs_review",
      summary: "Converted retrieved text into a role-specific answer format.",
    },
    {
      agent: "Reviewer agent",
      status: needsReview ? "needs_review" : "complete",
      summary: needsReview
        ? "Kept uncertainty visible because source coverage is limited."
        : "Checked caveats and citation coverage before final answer.",
    },
    {
      agent: finalAgentName[role],
      status: needsReview ? "needs_review" : "complete",
      summary: "Prepared the final answer for this panel.",
    },
  ]
}

function answerLines(content: string) {
  return content.split(/\n+/).map((line) => line.trim()).filter(Boolean)
}

function isAnswerHeading(line: string) {
  return line.endsWith(":") && line.length <= 64
}

function citationKind(citation: Citation) {
  if (citation.source_type === "external_authority") return "External authority"
  if (citation.display_label.toLowerCase().includes(".pdf")) return "PDF source"
  return "Record source"
}

function shortDocumentName(name: string) {
  return name.length > 34 ? `${name.slice(0, 31)}...` : name
}

function quoteDocumentMention(document: DocumentVersion) {
  const safeName = document.original_name.replace(/\\/g, "\\\\").replace(/"/g, "'")
  return `@"${safeName}"`
}

function normalizeMention(value: string) {
  return value
    .toLowerCase()
    .replace(/\.[a-z0-9]+$/i, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
}

function matchMentionToDocument(mention: string, documents: DocumentVersion[]) {
  const normalizedMention = normalizeMention(mention)
  if (!normalizedMention) return null

  return documents.find((document) => document.original_name.toLowerCase() === mention.toLowerCase())
    ?? documents.find((document) => {
      const normalizedName = normalizeMention(document.original_name)
      return normalizedName === normalizedMention
        || normalizedName.includes(normalizedMention)
        || normalizedMention.includes(normalizedName)
    })
    ?? null
}

function resolveQuestionScope(question: string, documents: DocumentVersion[]) {
  const mentions: string[] = []
  const quoted = question.matchAll(/@"([^"]+)"/g)
  for (const match of quoted) mentions.push(match[1])

  const withoutQuoted = question.replace(/@"[^"]+"/g, " ")
  const unquoted = withoutQuoted.matchAll(/(^|\s)@([^\s"@]+)/g)
  for (const match of unquoted) mentions.push(match[2])

  const targetMap = new Map<string, DocumentVersion>()
  const unmatchedMentions: string[] = []
  for (const mention of mentions) {
    const document = matchMentionToDocument(mention, documents)
    if (document) targetMap.set(document.version_id, document)
    else unmatchedMentions.push(mention)
  }

  const cleanedQuestion = question
    .replace(/@"[^"]+"/g, " ")
    .replace(/(^|\s)@([^\s"@]+)/g, " ")
    .replace(/\s+/g, " ")
    .trim()

  return {
    cleanedQuestion: cleanedQuestion || question.trim(),
    targetDocuments: Array.from(targetMap.values()),
    unmatchedMentions,
  }
}

function demoChatResponse(role: Role, question: string, workspace: Workspace | null, scopedDocuments: DocumentVersion[] = []): CaseChatResponse {
  const documents = scopedDocuments.length ? scopedDocuments : (workspace?.documents ?? [])
  const evidence = documents.length
    ? demoEvidence(role, documents)
    : workspace?.evidence?.length
      ? workspace.evidence
      : demoEvidence(role)
  const report = workspace?.latest_report ?? demoReport(role, documents)
  const primary = evidence[0]
  const sourceName = documents[0]?.original_name ?? primary.label
  const sourceQuote = primary.source_spans[0]?.exact_quote ?? primary.value
  const lowerQuestion = question.toLowerCase()
  const roleLine = role === "lawyer"
    ? "For counsel, I am limiting the answer to the uploaded record and the source cards below."
    : role === "judge"
      ? "For bench review, I am separating the cited record from caveats and inferences."
      : "For citizen view, I am explaining only what the uploaded paper supports."
  const focus = role === "lawyer" && lowerQuestion.includes("weak")
    ? "The weak point is any claim that cannot be tied to a visible page excerpt, annexure, date, receipt, signature, or order-sheet entry."
    : role === "lawyer" && lowerQuestion.includes("proof")
      ? "The missing-proof check should focus on dates, annexures, receipts, signatures, and authority/order references not visible in the cited source card."
      : role === "judge"
        ? "The safe bench-facing answer is to rely on the cited source card first, then list unresolved gaps separately."
        : "The safe next step is to keep this paper, compare it with the source card, and ask for help on any missing proof."

  return {
    answer: `${roleLine} I am using ${sourceName} as the record source. ${focus} Source card used: "${sourceQuote}". ${report.sections[0]?.claims[0]?.statement ?? ""}`,
    citations: evidence.slice(0, 3).map((item, index) => ({
      citation_id: `demo-citation-${index + 1}`,
      display_label: item.label,
      source_type: "uploaded_evidence",
      source_span: item.source_spans[0] ?? null,
    })),
    caveats: documents.length
      ? ["Demo mode uses browser-readable file previews and preserved source metadata.", "Sign in to run full backend PDF/OCR extraction with exact stored page spans."]
      : ["Upload a PDF or document to replace this sample record.", "For real case work, sign in and use the live backend workspace."],
    next_actions: roleNextActions[role],
    agent_trace: fallbackAgentTrace(role, evidence.slice(0, 3).map((item, index) => ({
      citation_id: `demo-citation-${index + 1}`,
      display_label: item.label,
      source_type: "uploaded_evidence",
      source_span: item.source_spans[0] ?? null,
    })), documents.length ? ["Demo source preview"] : ["Sample source"]),
    role: role === "citizen" ? "analyst" : role,
  }
}

export default function LiveDocumentPipeline({ role, caseId, demo = false }: { role: Role; caseId: string; demo?: boolean }) {
  const mode = copy[role]
  const inputRef = useRef<HTMLInputElement>(null)
  const chatThreadRef = useRef<HTMLDivElement>(null)
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [activeJob, setActiveJob] = useState<Job | null>(null)
  const [events, setEvents] = useState<JobEvent[]>([])
  const [uploads, setUploads] = useState<UploadRow[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [chatBusy, setChatBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState("")
  const [question, setQuestion] = useState("")
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([])

  const loadWorkspace = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    setError("")
    if (demo) {
      setWorkspace((current) => current ?? emptyWorkspace())
      setLoading(false)
      return
    }
    try {
      const response = await fetch(withDemo(`/api/document-intelligence/case-files/${caseId}/workspace`, demo), { cache: "no-store" })
      if (!response.ok) throw new Error(await responseError(response))
      const payload = await response.json() as Workspace
      setWorkspace(payload)
      setActiveJob(payload.jobs[0] ?? null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not connect to the document backend.")
    } finally {
      setLoading(false)
    }
  }, [caseId, demo])

  useEffect(() => {
    void loadWorkspace()
  }, [loadWorkspace])

  const jobId = activeJob?.job_id
  useEffect(() => {
    if (demo || !jobId || terminalStatuses.has(activeJob?.status ?? "")) return
    const source = new EventSource(withDemo(`/api/document-intelligence/analysis-jobs/${jobId}/events`, demo))

    const receive = (event: MessageEvent) => {
      try {
        const item = JSON.parse(event.data) as JobEvent
        setEvents((current) => current.some((known) => known.sequence === item.sequence)
          ? current
          : [...current, item].sort((a, b) => a.sequence - b.sequence))
        setActiveJob((current) => current ? { ...current, status: item.status } : current)
        if (terminalStatuses.has(item.status)) {
          source.close()
          window.setTimeout(() => void loadWorkspace(true), 350)
        }
      } catch {
        setError("Live progress event could not be read.")
      }
    }

    eventNames.forEach((name) => source.addEventListener(name, receive as EventListener))
    source.onerror = () => {
      source.close()
      setError("Live progress disconnected. Reload the workspace to reconnect.")
    }
    return () => source.close()
  }, [jobId, activeJob?.status, loadWorkspace, demo])

  const documents = useMemo(() => {
    const byDocument = new Map<string, DocumentVersion>()
    for (const document of workspace?.documents ?? []) byDocument.set(document.document_id, document)
    return [...byDocument.values()]
  }, [workspace?.documents])

  useEffect(() => {
    const thread = chatThreadRef.current
    if (!thread) return
    thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" })
  }, [chatTurns.length, chatBusy])

  function insertDocumentMention(document: DocumentVersion) {
    const mention = quoteDocumentMention(document)
    setQuestion((current) => {
      const prefix = current.trimEnd()
      return `${prefix}${prefix ? " " : ""}${mention} `
    })
  }

  function handleChatWheel(event: WheelEvent<HTMLDivElement>) {
    const thread = event.currentTarget
    const atTop = thread.scrollTop <= 0
    const atBottom = thread.scrollTop + thread.clientHeight >= thread.scrollHeight - 1
    const shouldPassToPage = (event.deltaY < 0 && atTop) || (event.deltaY > 0 && atBottom)
    if (!shouldPassToPage) return

    const page = document.scrollingElement || document.documentElement
    const before = page.scrollTop
    window.scrollBy({ top: event.deltaY, behavior: "auto" })
    if (page.scrollTop !== before) event.preventDefault()
  }

  const report = workspace?.latest_report ?? null
  const claims = flattenClaims(report)
  const hasRunningJob = Boolean(activeJob && !terminalStatuses.has(activeJob.status))

  const stageState = (stage: "store" | "extract" | "synthesis" | "review" | "final") => {
    const status = activeJob?.status
    if (stage === "store") return documents.length || uploads.some((item) => item.state === "ready") ? "complete" : uploads.some((item) => item.state === "uploading") ? "running" : "idle"
    if (stage === "extract") return status === "extracting" ? "running" : (workspace?.evidence.length ?? 0) > 0 ? "complete" : "idle"
    if (stage === "synthesis") return ["relating", "retrieving", "synthesizing"].includes(status ?? "") ? "running" : report ? "complete" : "idle"
    if (stage === "review") return status === "verifying" ? "running" : workspace?.integrity ? "complete" : "idle"
    return report && activeJob && terminalStatuses.has(activeJob.status) ? "complete" : hasRunningJob ? "running" : "idle"
  }

  const pipeline = [
    { key: "store" as const, icon: Database, title: "Document store", detail: `${documents.length} preserved source file(s)` },
    { key: "extract" as const, icon: SearchCheck, title: "Extractor agent", detail: `${workspace?.evidence.length ?? 0} evidence atom(s)` },
    { key: "synthesis" as const, icon: BookOpenCheck, title: "Synthesis agent", detail: report ? `Report v${report.version}` : "Waiting for extraction" },
    { key: "review" as const, icon: ShieldCheck, title: "Reviewer agent", detail: workspace?.integrity ? `${workspace.integrity.checked_spans} span(s) checked` : "Integrity pending" },
    { key: "final" as const, icon: FileCheck2, title: mode.final, detail: report ? label(report.status) : "No final answer yet" },
  ]

  function updateUpload(id: string, update: Partial<UploadRow>) {
    setUploads((current) => current.map((row) => row.id === id ? { ...row, ...update } : row))
  }

  async function uploadFiles(files: File[]) {
    if (!files.length) return
    setError("")
    const rows = files.map((file) => ({ id: crypto.randomUUID(), file, state: "queued" as const, detail: "Waiting" }))
    setUploads((current) => [...current, ...rows])

    if (demo) {
      const readyRows = await Promise.all(rows.map(async (row) => ({
        ...row,
        state: "ready" as const,
        detail: `${fileFormat(row.file).toUpperCase()} source card ready`,
        preview: await extractDemoPreview(row.file),
      })))
      const demoDocuments = readyRows.map((row) => demoDocument(row, row.preview))
      setUploads((current) => current.map((row) => {
        const ready = readyRows.find((item) => item.id === row.id)
        return ready ? { id: ready.id, file: ready.file, state: ready.state, detail: ready.detail } : row
      }))
      setWorkspace((current) => {
        const base = current ?? emptyWorkspace()
        const nextDocuments = [...demoDocuments, ...base.documents]
        return { ...base, documents: nextDocuments, evidence: demoEvidence(role, nextDocuments), latest_report: demoReport(role, nextDocuments) }
      })
      return
    }

    for (const row of rows) {
      updateUpload(row.id, { state: "uploading", detail: "Uploading and parsing" })
      const form = new FormData()
      form.append("file", row.file)
      form.append("case_id", caseId)
      try {
        const response = await fetch(withDemo("/api/document-intelligence/documents/upload", demo), { method: "POST", body: form })
        if (!response.ok) throw new Error(await responseError(response))
        const payload = await response.json() as { document: DocumentVersion; duplicate: boolean }
        updateUpload(row.id, {
          state: payload.document.status === "ready" ? "ready" : "partial",
          detail: payload.duplicate ? "Already preserved" : `${label(payload.document.status)} via ${payload.document.parser_name}`,
        })
      } catch (caught) {
        updateUpload(row.id, { state: "failed", detail: caught instanceof Error ? caught.message : "Upload failed" })
        setError(caught instanceof Error ? caught.message : "Upload failed")
      }
    }
    await loadWorkspace(true)
  }

  async function runPipeline() {
    if (!documents.length) {
      setError("Upload at least one document before running the agent pipeline.")
      return
    }
    setBusy(true)
    setEvents([])
    setError("")

    if (demo) {
      const now = new Date().toISOString()
      const baseJob: Job = {
        job_id: crypto.randomUUID(),
        status: "extracting",
        attempts: 1,
        max_attempts: 1,
        report_id: null,
        error: null,
        updated_at: now,
      }
      setActiveJob(baseJob)
      setWorkspace((current) => ({ ...(current ?? emptyWorkspace()), jobs: [baseJob] }))
      setBusy(false)

      const steps = [
        { status: "extracting", agent: "Extractor agent", message: "Demo extractor pulled facts and source spans from the uploaded bundle." },
        { status: "synthesizing", agent: "Synthesis agent", message: "Demo synthesis compiled the evidence into a role-specific report." },
        { status: "verifying", agent: "Reviewer agent", message: "Demo reviewer checked claims, caveats, and source span coverage." },
        { status: "completed", agent: mode.final, message: "Demo final answer is ready." },
      ]

      for (let index = 0; index < steps.length; index += 1) {
        await wait(index === 0 ? 250 : 700)
        const step = steps[index]
        const updated: Job = {
          ...baseJob,
          status: step.status,
          report_id: step.status === "completed" ? "demo-report" : null,
          updated_at: new Date().toISOString(),
        }
        setActiveJob(updated)
        setEvents((current) => [...current, {
          sequence: current.length,
          event_type: step.status === "completed" ? "completed" : "stage",
          status: step.status,
          agent: step.agent,
          message: step.message,
          created_at: new Date().toISOString(),
        }])

        if (step.status === "completed") {
          const report = demoReport(role, documents)
          setWorkspace((current) => ({
            ...(current ?? emptyWorkspace()),
            jobs: [updated],
            reports: [report],
            latest_report: report,
            evidence: demoEvidence(role, documents),
            integrity: demoIntegrity(),
            review_items: [],
          }))
        }
      }
      return
    }

    try {
      const response = await fetch(withDemo(`/api/document-intelligence/case-files/${caseId}/analysis-jobs`, demo), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_version_ids: documents.map((document) => document.version_id),
          role: mode.apiRole,
          enable_external_research: true,
        }),
      })
      if (!response.ok) throw new Error(await responseError(response))
      const job = await response.json() as Job
      setActiveJob(job)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start the live pipeline.")
    } finally {
      setBusy(false)
    }
  }

  async function submitQuestion(event?: { preventDefault: () => void }) {
    event?.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || chatBusy) return
    if (!demo && !documents.length) {
      setError("Upload at least one document before asking the record a question.")
      return
    }

    const scope = resolveQuestionScope(trimmed, documents)
    if (scope.unmatchedMentions.length) {
      setError(`No uploaded document matched ${scope.unmatchedMentions.map((item) => `@${item}`).join(", ")}.`)
      return
    }

    const userTurn: ChatTurn = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      targetDocuments: scope.targetDocuments,
    }
    const nextTurns = [...chatTurns, userTurn]
    const apiTurns = nextTurns.slice(-12).map((turn) => ({
      role: turn.role,
      content: turn.id === userTurn.id ? scope.cleanedQuestion : turn.content,
    }))
    setChatTurns(nextTurns)
    setQuestion("")
    setChatBusy(true)
    setError("")

    try {
      const payload = demo
        ? demoChatResponse(role, scope.cleanedQuestion, workspace, scope.targetDocuments)
        : await (async () => {
            const response = await fetch(`/api/document-intelligence/case-files/${caseId}/chat`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                role: mode.apiRole,
                language: "en",
                document_version_ids: scope.targetDocuments.map((document) => document.version_id),
                messages: apiTurns,
              }),
            })
            if (!response.ok) throw new Error(await responseError(response))
            return await response.json() as CaseChatResponse
          })()

      setChatTurns((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: payload.answer,
          citations: payload.citations,
          caveats: payload.caveats,
          nextActions: payload.next_actions?.length ? payload.next_actions : roleNextActions[role],
          agentTrace: payload.agent_trace?.length
            ? payload.agent_trace
            : fallbackAgentTrace(role, payload.citations, payload.caveats),
          targetDocuments: scope.targetDocuments,
        },
      ])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not answer from the record.")
    } finally {
      setChatBusy(false)
    }
  }
  const finalText = report
    ? role === "citizen"
      ? claims[0]?.statement ?? "The final citizen answer is ready from the verified report."
      : claims.slice(0, 2).map((claim) => claim.statement).join(" ") || "The final role answer is ready from the verified report."
    : "Upload documents and run the pipeline to generate a source-grounded final answer here."
  const nextActions = roleNextActions[role]

  return (
    <section className={`${styles.pipeline} ${styles[role]}`} id="live-pipeline" aria-label={`${mode.title} live backend pipeline`}>
      <div className={styles.header}>
        <div>
          <p>{demo ? "Demo backend workspace" : "Connected backend workspace"}</p>
          <h2>{mode.title}</h2>
          <span>{mode.subtitle}</span>
        </div>
        <button type="button" onClick={() => void loadWorkspace()} disabled={loading}>
          {loading ? <Loader2 className={styles.spin} size={16} /> : <RefreshCw size={16} />}
          Refresh
        </button>
      </div>

      {error ? (
        <div className={styles.error} role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      ) : null}

      <div className={styles.controlGrid}>
        <div
          className={`${styles.dropzone} ${dragging ? styles.dragging : ""}`}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            void uploadFiles(Array.from(event.dataTransfer.files))
          }}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.xls,.eml,.png,.jpg,.jpeg,.tif,.tiff"
            onChange={(event) => void uploadFiles(Array.from(event.target.files ?? []))}
          />
          <UploadCloud size={28} />
          <div>
            <strong>Upload documents</strong>
            <span>PDF, DOCX, text, spreadsheet, email, or scan</span>
          </div>
          <button type="button" onClick={() => inputRef.current?.click()}>Choose files</button>
        </div>

        <div className={styles.runCard}>
          <div>
            <span>Case workspace</span>
            <strong>{caseId.slice(0, 8)}</strong>
            <p>{activeJob ? `Latest job: ${label(activeJob.status)}` : "No job has been started yet."}</p>
          </div>
          <button type="button" onClick={() => void runPipeline()} disabled={busy || hasRunningJob}>
            {busy || hasRunningJob ? <Loader2 className={styles.spin} size={16} /> : <Play size={16} />}
            {hasRunningJob ? "Pipeline running" : mode.run}
          </button>
        </div>
      </div>

      <div className={styles.stageGrid}>
        {pipeline.map((stage) => {
          const Icon = stage.icon
          const state = stageState(stage.key)
          return (
            <article className={styles[state]} key={stage.key}>
              <Icon size={20} />
              <span>{label(state)}</span>
              <strong>{stage.title}</strong>
              <p>{stage.detail}</p>
            </article>
          )
        })}
      </div>

      <div className={styles.liveGrid}>
        <article className={styles.panel}>
          <h3>Stored documents</h3>
          {[...uploads].reverse().map((row) => (
            <div className={styles.row} key={row.id}>
              <FileText size={16} />
              <div><strong>{row.file.name}</strong><span>{row.detail}</span></div>
              <small>{label(row.state)}</small>
            </div>
          ))}
          {documents.map((document) => (
            <div className={styles.row} key={document.version_id}>
              <FileText size={16} />
              <div><strong>{document.original_name}</strong><span>{fileSize(document.size_bytes)} - {document.parser_name} - SHA {document.sha256.slice(0, 8)}</span></div>
              <small>{label(document.status)}</small>
            </div>
          ))}
          {!uploads.length && !documents.length ? <p className={styles.empty}>No documents uploaded yet.</p> : null}
        </article>

        <article className={styles.panel}>
          <h3>Extracted result</h3>
          {(workspace?.evidence ?? []).slice(0, 4).map((item) => (
            <div className={styles.evidence} key={item.evidence_id}>
              <span>{label(item.kind)} - {Math.round(item.confidence * 100)}%</span>
              <strong>{item.label}</strong>
              <p>{item.value}</p>
            </div>
          ))}
          {!(workspace?.evidence.length) ? <p className={styles.empty}>Extractor output will appear after the job runs.</p> : null}
        </article>

        <article className={styles.panel}>
          <h3>{mode.final}</h3>
          <p className={styles.finalText}>{finalText}</p>
          {report?.caveats?.length ? (
            <div className={styles.caveats}>
              {report.caveats.slice(0, 2).map((caveat) => <span key={caveat.caveat_id}>{caveat.title}</span>)}
            </div>
          ) : null}
          {workspace?.integrity ? <small>{workspace.integrity.checked_claims} claims, {workspace.integrity.checked_evidence} evidence items, {workspace.integrity.checked_spans} spans checked.</small> : null}
        </article>
      </div>


      <section className={styles.chatPanel} aria-label={`${mode.final} question panel`}>
        <div className={styles.chatIntro}>
          <div>
            <p>Ask the record</p>
            <h3>Question panel</h3>
            <span>Answers return as a direct answer, source cards, caveats, and next actions.</span>
          </div>
          <MessageSquare size={22} />
        </div>

        <div className={styles.promptChips}>
          {suggestedQuestions[role].map((prompt) => (
            <button type="button" key={prompt} onClick={() => setQuestion(prompt)}>
              <Lightbulb size={14} />
              {prompt}
            </button>
          ))}
        </div>

        {documents.length ? (
          <div className={styles.documentMentions} aria-label="Document scope">
            <span>Document scope</span>
            <button type="button" onClick={() => setQuestion((current) => current.replace(/@"[^"]+"|(^|\s)@([^\s"@]+)/g, " ").replace(/\s+/g, " ").trimStart())}>
              All documents
            </button>
            {documents.slice(0, 8).map((document) => (
              <button type="button" key={document.version_id} onClick={() => insertDocumentMention(document)} title={document.original_name}>
                @{shortDocumentName(document.original_name)}
              </button>
            ))}
          </div>
        ) : null}

        <div className={styles.chatThread} ref={chatThreadRef} onWheel={handleChatWheel}>
          {!chatTurns.length ? (
            <div className={styles.chatEmpty}>
              <strong>Ask a question about the uploaded record.</strong>
              <span>{demo ? "Demo mode can answer immediately from a simulated record." : "Live mode uses the backend retrieval chat after documents are uploaded."}</span>
            </div>
          ) : null}

          {chatTurns.map((turn) => (
            turn.role === "user" ? (
              <div className={styles.userTurn} key={turn.id}>
                <span>{turn.targetDocuments?.length ? "You asked one document" : "You asked all documents"}</span>
                <p>{turn.content}</p>
                {turn.targetDocuments?.length ? (
                  <div className={styles.scopePills}>
                    {turn.targetDocuments.map((document) => <small key={document.version_id}>@{shortDocumentName(document.original_name)}</small>)}
                  </div>
                ) : null}
              </div>
            ) : (
              <article className={styles.answerTurn} key={turn.id}>
                <div className={styles.agentRunCard}>
                  <div className={styles.agentRunHead}>
                    <div>
                      <span><Workflow size={14} /> Agent run complete</span>
                      <strong>Query router to Extractor to Synthesis to Reviewer to {finalAgentName[role]}</strong>
                      <p>{turn.targetDocuments?.length ? `The answer below is scoped to ${turn.targetDocuments.length} selected document(s), then checked before it reaches this role panel.` : "The answer below searches the full uploaded record, then gets checked before it reaches this role panel."}</p>
                    </div>
                    <Sparkles size={24} />
                  </div>

                  <div className={styles.agentTraceGrid}>
                    {(turn.agentTrace?.length ? turn.agentTrace : fallbackAgentTrace(role, turn.citations, turn.caveats)).map((step, index) => (
                      <div className={styles.agentTraceStep} data-state={step.status} key={`${turn.id}-${step.agent}-${index}`}>
                        <div>
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          {step.status === "complete" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                        </div>
                        <strong>{step.agent}</strong>
                        <p>{step.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className={styles.agentAnswerLayout}>
                  <div className={styles.finalAnswerBlock}>
                    <span>{finalAgentName[role]} output</span>
                    <div className={styles.structuredAnswer}>
                      {answerLines(turn.content).map((line, index) => (
                        isAnswerHeading(line)
                          ? <h4 key={`${turn.id}-line-${index}`}>{line.replace(/:$/, "")}</h4>
                          : <p key={`${turn.id}-line-${index}`}>{line}</p>
                      ))}
                    </div>
                  </div>

                  <aside className={styles.reviewSummary}>
                    <div>
                      <GitBranch size={18} />
                      <span>Source coverage</span>
                      <strong>{turn.citations?.length ?? 0} card(s)</strong>
                    </div>
                    <div>
                      <ShieldCheck size={18} />
                      <span>Reviewer status</span>
                      <strong>{(turn.caveats?.length ?? 0) > 1 ? "Needs review" : "Checked"}</strong>
                    </div>
                    <div>
                      <ArrowRight size={18} />
                      <span>Output route</span>
                      <strong>{finalAgentName[role]}</strong>
                    </div>
                  </aside>
                </div>

                <div className={styles.resultCards}>
                  <article className={styles.sourceCardsPanel}>
                    <span>Source cards used by extractor</span>
                    {(turn.citations?.length ? turn.citations : []).slice(0, 3).map((citation) => (
                      <div className={styles.sourceCard} key={citation.citation_id}>
                        <div className={styles.sourceCardHead}>
                          <strong>{citation.display_label}</strong>
                          <small>{citationKind(citation)}</small>
                        </div>
                        <p>{citation.source_span?.exact_quote ?? citation.source_url ?? "Source linked to the retrieved record."}</p>
                        {citation.source_span ? <span className={styles.pageChip}>Page {citation.source_span.page_number}</span> : null}
                      </div>
                    ))}
                    {!turn.citations?.length ? <p>No source card returned.</p> : null}
                  </article>
                  <article>
                    <span>Reviewer caveats</span>
                    {(turn.caveats?.length ? turn.caveats : ["Review the answer before acting."]).slice(0, 3).map((caveat) => (
                      <div className={styles.caveatCard} key={caveat}>{caveat}</div>
                    ))}
                  </article>
                  <article>
                    <span>Next actions</span>
                    {(turn.nextActions?.length ? turn.nextActions : nextActions).map((action) => <div className={styles.actionCard} key={action}>{action}</div>)}
                  </article>
                </div>
              </article>
            )
          ))}
        </div>

        <form className={styles.chatComposer} onSubmit={submitQuestion}>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={role === "citizen" ? "Ask what this means or what to do next" : "Ask a question about the uploaded record"}
            rows={2}
          />
          <button type="submit" disabled={chatBusy || !question.trim()}>
            {chatBusy ? <Loader2 className={styles.spin} size={16} /> : <SendHorizontal size={16} />}
            Ask
          </button>
        </form>
      </section>      {events.length ? (
        <div className={styles.eventLog}>
          {events.slice(-5).map((event) => (
            <div key={event.sequence}>
              <Clock3 size={14} />
              <strong>{event.agent || label(event.event_type)}</strong>
              <span>{event.message}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}











