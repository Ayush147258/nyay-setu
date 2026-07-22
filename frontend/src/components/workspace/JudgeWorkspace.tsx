"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  IconAlertTriangle,
  IconBook2,
  IconCalendarEvent,
  IconCheck,
  IconClock,
  IconCloudUpload,
  IconDownload,
  IconExternalLink,
  IconFileDescription,
  IconFileTypePdf,
  IconHistory,
  IconLink,
  IconLoader2,
  IconNetwork,
  IconPlayerPlay,
  IconRefresh,
  IconScale,
  IconShieldCheck,
  IconSparkles,
  IconX,
  IconZoomScan,
} from "@tabler/icons-react"
import type { AppRole } from "@/lib/roles"
import { normalizeRole } from "@/lib/roles"
import RoleBriefing from "./RoleBriefing"
import styles from "./JudgeWorkspace.module.css"

type Block = {
  block_id: string
  page_number: number
  sequence: number
  kind: string
  text: string
  confidence: number
}

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
  pages: Array<{ page_number: number; blocks: Block[] }>
  created_at: string
}

type SourceSpan = {
  document_id: string
  version_id: string
  page_number: number
  block_id: string
  start_char: number
  end_char: number
  exact_quote: string
}

type Evidence = {
  evidence_id: string
  kind: string
  label: string
  value: string
  normalized_value: string
  confidence: number
  review_state: string
  source_spans: SourceSpan[]
}

type ReportClaim = {
  claim_id: string
  statement: string
  kind: string
  evidence_ids: string[]
  research_ids: string[]
  confidence: number
  caveat?: string | null
}

type Report = {
  report_id: string
  version: number
  title: string
  status: string
  sections: Array<{ section_id: string; title: string; claims: ReportClaim[] }>
  citations: Array<{
    citation_id: string
    evidence_id?: string | null
    research_id?: string | null
    source_span?: SourceSpan | null
    source_url?: string | null
    display_label: string
  }>
  relationships: Array<{
    relationship_id: string
    source_evidence_id: string
    target_evidence_id: string
    relationship_type: string
    description: string
    confidence: number
    review_state: string
  }>
  timeline: Array<{
    event_id: string
    date_text: string
    normalized_date?: string | null
    description: string
    evidence_ids: string[]
    confidence: number
  }>
  research_findings: Array<{
    research_id: string
    title: string
    excerpt: string
    source_url: string
    citation: string
    court: string
    year: string
    provider: string
  }>
  caveats: Array<{
    caveat_id: string
    severity: "info" | "warning" | "blocking"
    title: string
    detail: string
    evidence_ids: string[]
  }>
  workflow_version: string
  created_at: string
}

type Integrity = {
  valid: boolean
  issues: Array<{
    code: string
    severity: "warning" | "blocking"
    message: string
    entity_type: string
    entity_id: string
  }>
  checked_claims: number
  checked_evidence: number
  checked_spans: number
}

type ReviewItem = {
  review_id: string
  source_type: string
  source_id: string
  severity: "warning" | "blocking"
  reason: string
  status: "open" | "resolved" | "dismissed"
}

type Job = {
  job_id: string
  status: string
  attempts: number
  max_attempts: number
  run_id?: string | null
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

export type Workspace = {
  documents: DocumentVersion[]
  jobs: Job[]
  reports: Report[]
  latest_report: Report | null
  evidence: Evidence[]
  integrity: Integrity | null
  review_items: ReviewItem[]
  review_decisions: Array<{ review_id: string; status: ReviewItem["status"]; note: string }>
  research: {
    status: string
    query: string
    findings: Report["research_findings"]
    warnings: string[]
  } | null
}

type UploadRow = {
  id: string
  file: File
  state: "queued" | "uploading" | "ready" | "partial" | "failed"
  detail: string
}

type Tab = "evidence" | "report" | "research" | "relationships" | "chronology" | "integrity"

const terminalStatuses = new Set(["completed", "needs_review", "failed", "cancelled"])
const eventNames = [
  "queued",
  "claimed",
  "stage",
  "completed",
  "cancel_requested",
  "cancelled",
  "manual_retry",
  "retry_scheduled",
  "failed",
  "lease_expired",
  "lease_recovered",
]

const modeCopy: Record<AppRole, {
  eyebrow: string
  runLabel: string
  runningLabel: string
  progressTitle: string
  tabLabels: Record<Tab, string>
}> = {
  lawyer: {
    eyebrow: "Counsel preparation room",
    runLabel: "Prepare hearing",
    runningLabel: "Preparation running",
    progressTitle: "Preparation agent run",
    tabLabels: {
      evidence: "Case proof",
      report: "Hearing brief",
      research: "Authorities",
      relationships: "Case links",
      chronology: "Timeline",
      integrity: "Weak points",
    },
  },
  judge: {
    eyebrow: "Judge workspace",
    runLabel: "Run analysis",
    runningLabel: "Analysis running",
    progressTitle: "Durable agent run",
    tabLabels: {
      evidence: "Evidence",
      report: "Report",
      research: "Research",
      relationships: "Relationships",
      chronology: "Chronology",
      integrity: "Integrity",
    },
  },
  citizen: {
    eyebrow: "My case workspace",
    runLabel: "Check my case",
    runningLabel: "Case check running",
    progressTitle: "Case check in progress",
    tabLabels: {
      evidence: "My record",
      report: "Case summary",
      research: "Legal references",
      relationships: "People and links",
      chronology: "Case timeline",
      integrity: "Delays and questions",
    },
  },
}
function formatDate(value?: string | null) {
  if (!value) return "Not recorded"
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

function fileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function responseError(response: Response) {
  const payload = await response.json().catch(() => ({})) as { detail?: string; error?: string }
  return payload.detail || payload.error || `Request failed with status ${response.status}`
}

function statusLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export default function JudgeWorkspace({
  caseId,
  caseTitle,
  caseType,
  district,
  audience = "judge",
  caseStatus,
  initialWorkspace,
  previewMode = false,
}: {
  caseId: string
  caseTitle: string
  caseType: string
  district?: string
  audience?: AppRole
  caseStatus?: string
  initialWorkspace?: Workspace
  previewMode?: boolean
}) {
  const currentRole = normalizeRole(audience)
  const mode = modeCopy[currentRole]
  const [workspace, setWorkspace] = useState<Workspace | null>(initialWorkspace ?? null)
  const [loading, setLoading] = useState(!initialWorkspace)
  const [loadError, setLoadError] = useState("")
  const [tab, setTab] = useState<Tab>("evidence")
  const [uploads, setUploads] = useState<UploadRow[]>([])
  const [uploadError, setUploadError] = useState("")
  const [analysisError, setAnalysisError] = useState("")
  const [starting, setStarting] = useState(false)
  const [researchEnabled, setResearchEnabled] = useState(true)
  const [activeJob, setActiveJob] = useState<Job | null>(initialWorkspace?.jobs[0] ?? null)
  const [events, setEvents] = useState<JobEvent[]>([])
  const [streamError, setStreamError] = useState("")
  const [reconnectKey, setReconnectKey] = useState(0)
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(initialWorkspace?.evidence[0]?.evidence_id ?? null)
  const [selectedReportId, setSelectedReportId] = useState<string | null>(initialWorkspace?.latest_report?.report_id ?? null)
  const [reviewBusy, setReviewBusy] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const loadWorkspace = useCallback(async (quiet = false) => {
    if (previewMode) return
    if (!quiet) setLoading(true)
    setLoadError("")
    try {
      const response = await fetch(
        `/api/document-intelligence/case-files/${caseId}/workspace`,
        { cache: "no-store" },
      )
      if (!response.ok) throw new Error(await responseError(response))
      const payload = await response.json() as Workspace
      setWorkspace(payload)
      setActiveJob(payload.jobs[0] ?? null)
      setSelectedReportId((current) =>
        current && payload.reports.some((report) => report.report_id === current)
          ? current
          : payload.latest_report?.report_id ?? null,
      )
      setSelectedEvidenceId((current) =>
        current && payload.evidence.some((item) => item.evidence_id === current)
          ? current
          : payload.evidence[0]?.evidence_id ?? null,
      )
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not load the case workspace.")
    } finally {
      setLoading(false)
    }
  }, [caseId, previewMode])

  useEffect(() => {
    if (!previewMode) void loadWorkspace()
  }, [loadWorkspace, previewMode])

  const jobId = activeJob?.job_id
  useEffect(() => {
    if (!jobId || terminalStatuses.has(activeJob?.status ?? "")) return
    setStreamError("")
    const source = new EventSource(`/api/document-intelligence/analysis-jobs/${jobId}/events`)

    const receive = (event: MessageEvent) => {
      try {
        const item = JSON.parse(event.data) as JobEvent
        setEvents((current) => {
          if (current.some((known) => known.sequence === item.sequence)) return current
          return [...current, item].sort((a, b) => a.sequence - b.sequence)
        })
        setActiveJob((current) => current ? { ...current, status: item.status } : current)
        if (terminalStatuses.has(item.status)) {
          source.close()
          window.setTimeout(() => void loadWorkspace(true), 250)
        }
      } catch {
        setStreamError("An analysis progress event could not be read.")
      }
    }

    eventNames.forEach((name) => source.addEventListener(name, receive as EventListener))
    source.onerror = () => {
      source.close()
      setStreamError("Live progress disconnected. The durable job is still safe; reconnect to continue watching it.")
    }
    return () => source.close()
  }, [jobId, reconnectKey, loadWorkspace])

  const selectedEvidence = workspace?.evidence.find((item) => item.evidence_id === selectedEvidenceId) ?? null
  const selectedReport = workspace?.reports.find((item) => item.report_id === selectedReportId)
    ?? workspace?.latest_report
    ?? null
  const decisionMap = useMemo(
    () => new Map((workspace?.review_decisions ?? []).map((item) => [item.review_id, item])),
    [workspace?.review_decisions],
  )
  const latestDocuments = useMemo(() => {
    const map = new Map<string, DocumentVersion>()
    for (const document of workspace?.documents ?? []) map.set(document.document_id, document)
    return [...map.values()]
  }, [workspace?.documents])
  const integrityScore = useMemo(() => {
    if (!workspace?.integrity) return null
    const blocking = workspace.integrity.issues.filter((item) => item.severity === "blocking").length
    const warnings = workspace.integrity.issues.length - blocking
    return Math.max(0, 100 - blocking * 25 - warnings * 8)
  }, [workspace?.integrity])

  function updateUpload(id: string, update: Partial<UploadRow>) {
    setUploads((current) => current.map((row) => row.id === id ? { ...row, ...update } : row))
  }

  async function uploadFiles(files: File[]) {
    if (!files.length) return
    setUploadError("")
    const rows = files.map((file) => ({
      id: crypto.randomUUID(),
      file,
      state: "queued" as const,
      detail: "Waiting",
    }))
    setUploads((current) => [...current, ...rows])

    for (const row of rows) {
      updateUpload(row.id, { state: "uploading", detail: "Uploading and parsing" })
      const form = new FormData()
      form.append("file", row.file)
      form.append("case_id", caseId)
      try {
        const response = await fetch("/api/document-intelligence/documents/upload", {
          method: "POST",
          body: form,
        })
        if (!response.ok) throw new Error(await responseError(response))
        const payload = await response.json() as { document: DocumentVersion; duplicate: boolean }
        const partial = payload.document.status !== "ready"
        updateUpload(row.id, {
          state: partial ? "partial" : "ready",
          detail: payload.duplicate
            ? "Identical source already preserved"
            : `${statusLabel(payload.document.status)} via ${payload.document.parser_name}`,
        })
      } catch (error) {
        const message = error instanceof Error ? error.message : "Upload failed"
        updateUpload(row.id, { state: "failed", detail: message })
        setUploadError("One or more files could not be ingested. Review the per-file status and retry.")
      }
    }
    await loadWorkspace(true)
  }

  async function startAnalysis() {
    if (!latestDocuments.length) {
      setAnalysisError("Upload at least one document before starting analysis.")
      return
    }
    setStarting(true)
    setAnalysisError("")
    setEvents([])
    try {
      const response = await fetch(
        `/api/document-intelligence/case-files/${caseId}/analysis-jobs`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            document_version_ids: latestDocuments.map((item) => item.version_id),
            role: currentRole,
            enable_external_research: researchEnabled,
          }),
        },
      )
      if (!response.ok) throw new Error(await responseError(response))
      const job = await response.json() as Job
      setActiveJob(job)
      setReconnectKey((value) => value + 1)
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "Could not start analysis.")
    } finally {
      setStarting(false)
    }
  }

  async function retryJob() {
    if (!activeJob) return
    setAnalysisError("")
    try {
      const response = await fetch(
        `/api/document-intelligence/analysis-jobs/${activeJob.job_id}/retry`,
        { method: "POST" },
      )
      if (!response.ok) throw new Error(await responseError(response))
      const job = await response.json() as Job
      setEvents([])
      setActiveJob(job)
      setReconnectKey((value) => value + 1)
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "Could not retry analysis.")
    }
  }

  async function decideReview(reviewId: string, status: "resolved" | "dismissed") {
    setReviewBusy(reviewId)
    try {
      const response = await fetch(
        `/api/document-intelligence/case-files/${caseId}/reviews/${reviewId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        },
      )
      if (!response.ok) throw new Error(await responseError(response))
      await loadWorkspace(true)
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "Could not update review state.")
    } finally {
      setReviewBusy(null)
    }
  }

  const tabs: Array<{ id: Tab; label: string; icon: typeof IconScale; count?: number }> = [
    { id: "evidence", label: mode.tabLabels.evidence, icon: IconZoomScan, count: workspace?.evidence.length },
    { id: "report", label: mode.tabLabels.report, icon: IconFileDescription, count: workspace?.reports.length },
    { id: "research", label: mode.tabLabels.research, icon: IconBook2, count: selectedReport?.research_findings.length },
    { id: "relationships", label: mode.tabLabels.relationships, icon: IconNetwork, count: selectedReport?.relationships.length },
    { id: "chronology", label: mode.tabLabels.chronology, icon: IconCalendarEvent, count: selectedReport?.timeline.length },
    { id: "integrity", label: mode.tabLabels.integrity, icon: IconShieldCheck, count: workspace?.review_items.length },
  ]

  if (loading && !workspace) {
    return (
      <div className={styles.centerState}>
        <IconLoader2 className={styles.spin} size={28} />
        <strong>Opening the case record</strong>
        <span>Loading preserved documents, jobs, and report versions.</span>
      </div>
    )
  }

  if (loadError && !workspace) {
    return (
      <div className={styles.centerState}>
        <IconAlertTriangle size={30} />
        <strong>Workspace unavailable</strong>
        <span>{loadError}</span>
        <button className={styles.primaryButton} onClick={() => void loadWorkspace()}>
          <IconRefresh size={17} /> Retry
        </button>
      </div>
    )
  }

  return (
    <div className={styles.workspace}>
      <header className={styles.caseHeader}>
        <div>
          <div className={styles.eyebrow}>{mode.eyebrow} · {caseId.slice(0, 8)}</div>
          <h1>{caseTitle}</h1>
          <p>{statusLabel(caseType)}{district ? ` · ${district}` : ""}</p>
        </div>
        <div className={styles.headerActions}>
          {selectedReport ? (
            <>
              <a
                className={styles.secondaryButton}
                href={`/api/document-intelligence/case-files/${caseId}/reports/${selectedReport.report_id}/export?format=json`}
              >
                <IconDownload size={17} /> JSON
              </a>
              <a
                className={styles.secondaryButton}
                href={`/api/document-intelligence/case-files/${caseId}/reports/${selectedReport.report_id}/export?format=pdf`}
              >
                <IconFileTypePdf size={17} /> PDF
              </a>
            </>
          ) : null}
          <button className={styles.primaryButton} onClick={() => void startAnalysis()} disabled={starting || previewMode}>
            {starting ? <IconLoader2 className={styles.spin} size={17} /> : <IconPlayerPlay size={17} />}
            {activeJob && !terminalStatuses.has(activeJob.status) ? mode.runningLabel : mode.runLabel}
          </button>
        </div>
      </header>

      <RoleBriefing
        role={currentRole}
        workspace={workspace}
        report={selectedReport ?? null}
        caseStatus={caseStatus}
        integrityScore={integrityScore}
        onOpenTab={setTab}
      />

      <section className={styles.intakeBand}>
        <div
          className={`${styles.dropZone} ${dragging ? styles.dragging : ""}`}
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
          <IconCloudUpload size={24} />
          <div>
            <strong>Add source documents</strong>
            <span>PDF, DOCX, text, spreadsheet, email, or scanned image</span>
          </div>
          <button className={styles.secondaryButton} onClick={() => inputRef.current?.click()}>Choose files</button>
        </div>

        <div className={styles.analysisControl}>
          <div>
            <strong>External legal research</strong>
            <span>Keep authorities separate from case evidence.</span>
          </div>
          <button
            className={`${styles.toggle} ${researchEnabled ? styles.toggleOn : ""}`}
            onClick={() => setResearchEnabled((value) => !value)}
            role="switch"
            aria-checked={researchEnabled}
            aria-label="External legal research"
          ><span /></button>
        </div>
      </section>

      {uploadError || analysisError || streamError ? (
        <div className={styles.errorBanner} role="alert">
          <IconAlertTriangle size={18} />
          <span>{uploadError || analysisError || streamError}</span>
          {streamError && activeJob ? (
            <button onClick={() => { setStreamError(""); setReconnectKey((value) => value + 1) }}>
              <IconRefresh size={16} /> Reconnect
            </button>
          ) : null}
          {(activeJob?.status === "failed" || activeJob?.status === "cancelled") ? (
            <button onClick={() => void retryJob()}><IconRefresh size={16} /> Retry job</button>
          ) : null}
        </div>
      ) : null}

      {(uploads.length > 0 || latestDocuments.length > 0) ? (
        <section className={styles.sourceStrip} aria-label="Source document status">
          {[...uploads].reverse().map((row) => (
            <div className={styles.sourceRow} key={row.id}>
              <IconFileDescription size={18} />
              <div><strong>{row.file.name}</strong><span>{row.detail}</span></div>
              <span className={`${styles.statusPill} ${styles[row.state]}`}>{statusLabel(row.state)}</span>
              {row.state !== "uploading" ? (
                <button aria-label={`Remove ${row.file.name}`} onClick={() => setUploads((items) => items.filter((item) => item.id !== row.id))}><IconX size={15} /></button>
              ) : <IconLoader2 className={styles.spin} size={16} />}
            </div>
          ))}
          {latestDocuments.map((document) => (
            <div className={styles.sourceRow} key={document.version_id}>
              <IconFileDescription size={18} />
              <div>
                <strong>{document.original_name}</strong>
                <span>{fileSize(document.size_bytes)} · {document.parser_name} · SHA {document.sha256.slice(0, 10)}</span>
              </div>
              <span className={`${styles.statusPill} ${document.status === "ready" ? styles.ready : styles.partial}`}>{statusLabel(document.status)}</span>
            </div>
          ))}
        </section>
      ) : null}

      <section className={styles.progressBand}>
        <div className={styles.progressHeading}>
          <div>
            <IconSparkles size={18} />
            <strong>{mode.progressTitle}</strong>
            <span>{activeJob ? `Attempt ${activeJob.attempts} of ${activeJob.max_attempts}` : "No analysis has been queued"}</span>
          </div>
          <span className={`${styles.liveStatus} ${activeJob && !terminalStatuses.has(activeJob.status) ? styles.live : ""}`}>
            {activeJob ? statusLabel(activeJob.status) : "Idle"}
          </span>
        </div>
        <div className={styles.progressSteps}>
          {["queued", "extracting", "researching", "synthesizing", "verifying", "completed"].map((stage, index) => {
            const order = ["queued", "extracting", "researching", "synthesizing", "verifying", "completed"]
            const current = activeJob?.status === "needs_review" ? "completed" : activeJob?.status ?? "queued"
            const complete = activeJob ? order.indexOf(current) >= index : false
            return <div key={stage} className={complete ? styles.stepComplete : ""}><span>{complete ? <IconCheck size={13} /> : index + 1}</span><small>{statusLabel(stage)}</small></div>
          })}
        </div>
        {events.length ? (
          <div className={styles.eventLog}>
            {events.slice(-4).map((event) => (
              <div key={event.sequence}><IconClock size={14} /><strong>{event.agent || statusLabel(event.event_type)}</strong><span>{event.message}</span><time>{formatDate(event.created_at)}</time></div>
            ))}
          </div>
        ) : null}
      </section>

      <nav className={styles.tabs} aria-label="Case analysis views">
        {tabs.map((item) => {
          const Icon = item.icon
          return (
            <button key={item.id} className={tab === item.id ? styles.activeTab : ""} onClick={() => setTab(item.id)}>
              <Icon size={17} /> {item.label}
              {typeof item.count === "number" ? <span>{item.count}</span> : null}
            </button>
          )
        })}
      </nav>

      <main className={styles.content}>
        {tab === "evidence" ? (
          workspace?.evidence.length ? (
            <div className={styles.evidenceLayout}>
              <section className={styles.evidenceList}>
                <div className={styles.sectionHeading}><div><h2>Extracted evidence</h2><p>Facts remain tied to immutable source spans.</p></div></div>
                {workspace.evidence.map((item) => (
                  <button
                    key={item.evidence_id}
                    className={selectedEvidenceId === item.evidence_id ? styles.selectedEvidence : ""}
                    onClick={() => setSelectedEvidenceId(item.evidence_id)}
                  >
                    <span className={styles.evidenceKind}>{statusLabel(item.kind)}</span>
                    <strong>{item.label}</strong>
                    <p>{item.value}</p>
                    <small>{Math.round(item.confidence * 100)}% confidence · {statusLabel(item.review_state)}</small>
                  </button>
                ))}
              </section>
              <aside className={styles.sourceInspector}>
                <div className={styles.sectionHeading}><div><h2>Source inspector</h2><p>Click any evidence item to verify its exact origin.</p></div></div>
                {selectedEvidence ? selectedEvidence.source_spans.map((span) => {
                  const document = workspace.documents.find((item) => item.version_id === span.version_id)
                  return (
                    <div className={styles.sourceExcerpt} key={`${span.block_id}-${span.start_char}`}>
                      <div><IconLink size={15} /><strong>{document?.original_name ?? "Preserved source"}</strong><span>Page {span.page_number} · chars {span.start_char}–{span.end_char}</span></div>
                      <blockquote>{span.exact_quote}</blockquote>
                      <code>{span.block_id}</code>
                    </div>
                  )
                }) : <div className={styles.empty}>Select evidence to inspect its source.</div>}
              </aside>
            </div>
          ) : <Empty title="No evidence yet" detail="Upload documents and run analysis to populate verified evidence atoms." />
        ) : null}

        {tab === "report" ? (
          selectedReport ? (
            <div className={styles.reportLayout}>
              <article className={styles.reportDocument}>
                <div className={styles.reportMasthead}><IconScale size={24} /><div><span>NyaySetu structured analysis</span><h2>{selectedReport.title}</h2><p>Version {selectedReport.version} · {formatDate(selectedReport.created_at)}</p></div></div>
                {selectedReport.sections.map((section) => (
                  <section key={section.section_id}>
                    <h3>{section.title}</h3>
                    {section.claims.map((claim) => (
                      <div className={styles.claim} key={claim.claim_id}>
                        <span>{statusLabel(claim.kind)}</span><p>{claim.statement}</p><small>{Math.round(claim.confidence * 100)}% · {claim.evidence_ids.length} evidence citation(s)</small>
                        {claim.caveat ? <em>{claim.caveat}</em> : null}
                      </div>
                    ))}
                  </section>
                ))}
              </article>
              <aside className={styles.versionRail}>
                <div className={styles.sectionHeading}><div><h2>Version history</h2><p>Every report remains available.</p></div></div>
                {workspace?.reports.map((report) => (
                  <button key={report.report_id} className={selectedReport.report_id === report.report_id ? styles.selectedVersion : ""} onClick={() => setSelectedReportId(report.report_id)}>
                    <IconHistory size={17} /><div><strong>Version {report.version}</strong><span>{formatDate(report.created_at)}</span></div><small>{statusLabel(report.status)}</small>
                  </button>
                ))}
              </aside>
            </div>
          ) : <Empty title="No report yet" detail="The structured report appears after the verifier completes the durable run." />
        ) : null}

        {tab === "research" ? (
          selectedReport?.research_findings.length ? (
            <section className={styles.singleSection}>
              <div className={styles.sectionHeading}><div><h2>External legal research</h2><p>Authorities are deliberately separated from record evidence.</p></div></div>
              <div className={styles.researchList}>{selectedReport.research_findings.map((finding) => (
                <article key={finding.research_id}>
                  <div><span>{finding.provider}</span>{finding.court ? <span>{finding.court}</span> : null}{finding.year ? <span>{finding.year}</span> : null}</div>
                  <h3>{finding.title}</h3><p>{finding.excerpt}</p>
                  <a href={finding.source_url} target="_blank" rel="noreferrer">Open authority <IconExternalLink size={15} /></a>
                </article>
              ))}</div>
            </section>
          ) : <Empty title="No external research" detail={workspace?.research?.warnings?.[0] || "Enable legal research on the next run to retrieve allow-listed authorities."} />
        ) : null}

        {tab === "relationships" ? (
          selectedReport?.relationships.length ? (
            <section className={styles.singleSection}>
              <div className={styles.sectionHeading}><div><h2>Evidence relationships</h2><p>Connections derived from the record, with confidence and review state.</p></div></div>
              <div className={styles.relationshipList}>{selectedReport.relationships.map((edge) => (
                <article key={edge.relationship_id}><IconNetwork size={19} /><div><span>{statusLabel(edge.relationship_type)}</span><h3>{edge.description}</h3><p>{edge.source_evidence_id.slice(0, 12)} → {edge.target_evidence_id.slice(0, 12)}</p></div><strong>{Math.round(edge.confidence * 100)}%</strong></article>
              ))}</div>
            </section>
          ) : <Empty title="No relationships found" detail="The relationship agent did not find supported links in the current evidence set." />
        ) : null}

        {tab === "chronology" ? (
          selectedReport?.timeline.length ? (
            <section className={styles.singleSection}>
              <div className={styles.sectionHeading}><div><h2>Case chronology</h2><p>Dated events remain linked to their supporting evidence.</p></div></div>
              <div className={styles.timeline}>{selectedReport.timeline.map((event) => (
                <article key={event.event_id}><span /><time>{event.normalized_date || event.date_text}</time><div><h3>{event.description}</h3><p>{event.evidence_ids.length} source link(s) · {Math.round(event.confidence * 100)}% confidence</p></div></article>
              ))}</div>
            </section>
          ) : <Empty title="No chronology yet" detail="No dated evidence was extracted from the current documents." />
        ) : null}

        {tab === "integrity" ? (
          workspace?.integrity ? (
            <div className={styles.integrityLayout}>
              <section className={styles.scorePanel}>
                <div className={styles.scoreRing}><strong>{integrityScore}</strong><span>/ 100</span></div>
                <h2>{workspace.integrity.valid ? "Integrity checks passed" : currentRole === "lawyer" ? "Preparation gaps remain" : currentRole === "citizen" ? "Questions need attention" : "Judicial review required"}</h2>
                <p>{workspace.integrity.checked_spans} exact source spans, {workspace.integrity.checked_evidence} evidence atoms, and {workspace.integrity.checked_claims} claims checked.</p>
              </section>
              <section className={styles.reviewQueue}>
                <div className={styles.sectionHeading}><div><h2>{currentRole === "lawyer" ? "Weak points to resolve" : currentRole === "citizen" ? "Items to ask your lawyer about" : "Unresolved caveats"}</h2><p>Nothing low-confidence or unsupported is hidden.</p></div></div>
                {workspace.review_items.length ? workspace.review_items.map((item) => {
                  const decision = decisionMap.get(item.review_id)
                  return (
                    <article key={item.review_id}>
                      <span className={`${styles.severity} ${item.severity === "blocking" ? styles.blocking : ""}`}>{statusLabel(item.severity)}</span>
                      <div><h3>{item.reason}</h3><p>{statusLabel(item.source_type)} · {item.source_id}</p></div>
                      {decision ? <strong className={styles.decided}><IconCheck size={15} /> {statusLabel(decision.status)}</strong> : currentRole === "citizen" ? (
                        <strong className={styles.askCounsel}>Ask counsel</strong>
                      ) : (
                        <div className={styles.reviewActions}>
                          <button disabled={reviewBusy === item.review_id} onClick={() => void decideReview(item.review_id, "resolved")}><IconCheck size={15} /> Resolve</button>
                          <button disabled={reviewBusy === item.review_id} onClick={() => void decideReview(item.review_id, "dismissed")}><IconX size={15} /> Dismiss</button>
                        </div>
                      )}
                    </article>
                  )
                }) : <div className={styles.empty}>No unresolved caveats remain.</div>}
              </section>
            </div>
          ) : <Empty title="Integrity results pending" detail="Run analysis to validate source spans, evidence, and report claims." />
        ) : null}
      </main>
    </div>
  )
}

function Empty({ title, detail }: { title: string; detail: string }) {
  return <div className={styles.emptyLarge}><IconFileDescription size={26} /><strong>{title}</strong><span>{detail}</span></div>
}


