"use client"

import {
  IconAlertTriangle,
  IconArrowRight,
  IconCheck,
  IconClockQuestion,
  IconMessageQuestion,
  IconScale,
  IconShieldCheck,
} from "@tabler/icons-react"
import type { AppRole } from "@/lib/roles"
import type { Workspace } from "./JudgeWorkspace"
import styles from "./RoleBriefing.module.css"

type WorkspaceTab = "evidence" | "report" | "research" | "relationships" | "chronology" | "integrity"

type BriefingProps = {
  role: AppRole
  workspace: Workspace | null
  report: Workspace["latest_report"]
  caseStatus?: string
  integrityScore: number | null
  onOpenTab: (tab: WorkspaceTab) => void
}

const terminalJobs = new Set(["completed", "needs_review", "failed", "cancelled"])

function label(value?: string | null) {
  return (value || "not recorded").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export default function RoleBriefing({
  role,
  workspace,
  report,
  caseStatus,
  integrityScore,
  onOpenTab,
}: BriefingProps) {
  if (role === "judge") return null

  if (role === "lawyer") {
    const attacks = [
      ...(report?.caveats.map((item) => ({
        id: item.caveat_id,
        severity: item.severity,
        title: item.title,
        detail: item.detail,
      })) ?? []),
      ...(workspace?.evidence
        .filter((item) => item.confidence < 0.75 || item.review_state === "needs_review")
        .map((item) => ({
          id: `evidence-${item.evidence_id}`,
          severity: "warning" as const,
          title: `${item.label} may be challenged`,
          detail: `The current extraction is ${Math.round(item.confidence * 100)}% confident. Verify the original page before relying on it.`,
        })) ?? []),
    ].filter((item, index, items) => items.findIndex((candidate) => candidate.title === item.title) === index).slice(0, 4)

    const primaryCaveat = attacks[0]
    const questions = [
      primaryCaveat
        ? `How do you answer the unresolved issue: ${primaryCaveat.title}?`
        : "Which exact page proves each essential fact in your submission?",
      "What precise relief are you asking for, and what provision gives this court jurisdiction?",
      report?.research_findings.length
        ? "Have you read the full judgments behind every cited excerpt, including later treatment?"
        : "Which binding authority supports the proposition you want the court to accept?",
      "What is the strongest version of opposing counsel's case, and where does the record answer it?",
    ]

    return (
      <section className={styles.briefing} aria-label="Counsel hearing preparation">
        <div className={styles.briefHeader}>
          <div><span>Counsel preparation</span><h2>Hearing pressure test</h2><p>Record-derived challenges to resolve before you stand up in court.</p></div>
          <div className={styles.readiness}><strong>{integrityScore ?? "-"}</strong><span>readiness</span></div>
        </div>
        <div className={styles.lawyerGrid}>
          <article className={styles.challengePanel}>
            <div className={styles.panelTitle}><IconAlertTriangle size={18} /><div><h3>Opponent challenge map</h3><p>Likely attacks based on gaps and low-confidence material.</p></div></div>
            {attacks.length ? attacks.map((attack) => (
              <div className={styles.challenge} key={attack.id}>
                <span className={attack.severity === "blocking" ? styles.blocking : undefined}>{label(attack.severity)}</span>
                <div><strong>{attack.title}</strong><p>{attack.detail}</p><small>Prepare a cited answer or concede the limit clearly.</small></div>
              </div>
            )) : <div className={styles.clear}><IconCheck size={17} /> No record-derived challenge is currently open.</div>}
            <button onClick={() => onOpenTab("integrity")}>Review all weak points <IconArrowRight size={15} /></button>
          </article>

          <article className={styles.questionPanel}>
            <div className={styles.panelTitle}><IconScale size={18} /><div><h3>Likely bench questions</h3><p>Questions counsel should answer with a page citation.</p></div></div>
            <ol>{questions.map((question) => <li key={question}>{question}</li>)}</ol>
            <button onClick={() => onOpenTab("evidence")}>Open case proof <IconArrowRight size={15} /></button>
          </article>

          <article className={styles.responsePanel}>
            <div className={styles.panelTitle}><IconShieldCheck size={18} /><div><h3>Response discipline</h3><p>Use only what survives source verification.</p></div></div>
            <ul>
              <li><IconCheck size={14} /> Lead with the exact proposition and relief.</li>
              <li><IconCheck size={14} /> Keep the supporting page open for each factual claim.</li>
              <li><IconCheck size={14} /> State adverse facts before the opponent does.</li>
              <li><IconCheck size={14} /> Never fill a record gap with an assumption.</li>
            </ul>
            <button onClick={() => onOpenTab("report")}>Open hearing brief <IconArrowRight size={15} /></button>
          </article>
        </div>
        <p className={styles.safety}>Preparation aid only. It must not be used to coach false testimony, conceal adverse material, or misstate the record.</p>
      </section>
    )
  }

  const activeJob = workspace?.jobs[0]
  const delayReasons: string[] = []
  if (activeJob && !terminalJobs.has(activeJob.status)) delayReasons.push(`Document analysis is still ${label(activeJob.status).toLowerCase()}.`)
  const incompleteDocuments = workspace?.documents.filter((document) => document.status !== "ready") ?? []
  if (incompleteDocuments.length) delayReasons.push(`${incompleteDocuments.length} document(s) still need parsing, OCR, or human review.`)
  const openReviews = workspace?.review_items.filter((item) => item.status === "open") ?? []
  if (openReviews.length) delayReasons.push(`${openReviews.length} unresolved record issue(s) may be holding up the next step.`)
  if (workspace && !workspace.latest_report) delayReasons.push("No completed case analysis is available yet.")
  if (!delayReasons.length) delayReasons.push("NyaySetu does not currently see a document-processing blocker. Ask counsel about court scheduling or procedural delay.")

  const lawyerQuestions = [
    "What happened at the last hearing, and what did the court direct us to do next?",
    "What is the next court date, and what must be filed or prepared before then?",
    openReviews.length
      ? `How will we resolve the ${openReviews.length} open document or evidence issue(s)?`
      : "Is any document, affidavit, fee, or certified copy still missing?",
    "What is the strongest point against our case, and how will you answer it from the record?",
    "Please show me the filing receipt, order sheet, or source document supporting the current status.",
  ]

  return (
    <section className={styles.briefing} aria-label="Citizen case readiness">
      <div className={styles.briefHeader}>
        <div><span>Case understanding</span><h2>Your next lawyer meeting</h2><p>Current record status, possible delays, and questions worth getting answered.</p></div>
        <div className={styles.caseStatus}><strong>{label(caseStatus)}</strong><span>case status</span></div>
      </div>
      <div className={styles.citizenGrid}>
        <article>
          <div className={styles.panelTitle}><IconClockQuestion size={18} /><div><h3>What may be causing delay</h3><p>Based on the documents visible to NyaySetu.</p></div></div>
          <ul className={styles.delayList}>{delayReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          <button onClick={() => onOpenTab("integrity")}>See unresolved items <IconArrowRight size={15} /></button>
        </article>
        <article>
          <div className={styles.panelTitle}><IconMessageQuestion size={18} /><div><h3>Questions to ask your lawyer</h3><p>Take these into your next call or meeting.</p></div></div>
          <ol className={styles.citizenQuestions}>{lawyerQuestions.map((question) => <li key={question}>{question}</li>)}</ol>
          <button onClick={() => onOpenTab("chronology")}>Open case timeline <IconArrowRight size={15} /></button>
        </article>
      </div>
      <p className={styles.safety}>A missing update in NyaySetu does not prove that your lawyer or the court caused the delay. Confirm status from the latest order sheet and filing receipt.</p>
    </section>
  )
}
