"use client"

import { Suspense, useState } from "react"
import { useSearchParams } from "next/navigation"
import JudgeWorkspace, { type Workspace } from "@/components/workspace/JudgeWorkspace"
import type { AppRole } from "@/lib/roles"
import { normalizeRole, roleMeta } from "@/lib/roles"
import styles from "./demo.module.css"

const caseId = "11111111-1111-4111-8111-111111111111"
const versionId = "22222222-2222-4222-8222-222222222222"
const documentId = "33333333-3333-4333-8333-333333333333"
const createdAt = "2026-07-17T08:30:00.000Z"

const span = (blockId: string, quote: string, start = 0) => ({
  document_id: documentId,
  version_id: versionId,
  page_number: 1,
  block_id: blockId,
  start_char: start,
  end_char: start + quote.length,
  exact_quote: quote,
})

const evidence = [
  {
    evidence_id: "ev-petitioner",
    kind: "person",
    label: "Petitioner",
    value: "Ramesh Kumar",
    normalized_value: "ramesh kumar",
    confidence: 0.98,
    review_state: "verified",
    source_spans: [span("block-party", "Ramesh Kumar")],
  },
  {
    evidence_id: "ev-case",
    kind: "case_number",
    label: "FIR number",
    value: "FIR No. 123 of 2024",
    normalized_value: "123/2024",
    confidence: 0.96,
    review_state: "verified",
    source_spans: [span("block-fir", "FIR No. 123 of 2024")],
  },
  {
    evidence_id: "ev-date",
    kind: "date",
    label: "Complaint date",
    value: "12 March 2024",
    normalized_value: "2024-03-12",
    confidence: 0.92,
    review_state: "verified",
    source_spans: [span("block-date", "12/03/2024")],
  },
  {
    evidence_id: "ev-money",
    kind: "money",
    label: "Disputed amount",
    value: "Rs. 10,000",
    normalized_value: "INR 10000",
    confidence: 0.73,
    review_state: "needs_review",
    source_spans: [span("block-money", "Rs. 10,000")],
  },
]

const report = {
  report_id: "report-demo-v2",
  version: 2,
  title: "Judicial Record Analysis: FIR Registration Dispute",
  status: "needs_review",
  sections: [
    {
      section_id: "material-facts",
      title: "Material facts",
      claims: [
        {
          claim_id: "claim-1",
          statement: "The petitioner states that FIR No. 123 of 2024 was presented on 12 March 2024.",
          kind: "fact",
          evidence_ids: ["ev-petitioner", "ev-case", "ev-date"],
          research_ids: [],
          confidence: 0.95,
        },
        {
          claim_id: "claim-2",
          statement: "The disputed amount recorded in the complaint is Rs. 10,000.",
          kind: "fact",
          evidence_ids: ["ev-money"],
          research_ids: [],
          confidence: 0.73,
          caveat: "Amount requires comparison with the missing payment annexure.",
        },
      ],
    },
    {
      section_id: "legal-analysis",
      title: "Legal analysis",
      claims: [
        {
          claim_id: "claim-3",
          statement: "The record raises a question concerning the duty to register information disclosing a cognizable offence.",
          kind: "law",
          evidence_ids: ["ev-case"],
          research_ids: ["research-lalita"],
          confidence: 0.88,
        },
      ],
    },
  ],
  citations: [],
  relationships: [
    {
      relationship_id: "rel-1",
      source_evidence_id: "ev-petitioner",
      target_evidence_id: "ev-case",
      relationship_type: "party_to",
      description: "Ramesh Kumar is identified as the complainant connected to FIR No. 123 of 2024.",
      confidence: 0.94,
      review_state: "verified",
    },
  ],
  timeline: [
    {
      event_id: "timeline-1",
      date_text: "12/03/2024",
      normalized_date: "2024-03-12",
      description: "Complaint presented for FIR registration.",
      evidence_ids: ["ev-date", "ev-case"],
      confidence: 0.92,
    },
    {
      event_id: "timeline-2",
      date_text: "18/03/2024",
      normalized_date: "2024-03-18",
      description: "Written representation submitted to the Superintendent of Police.",
      evidence_ids: ["ev-case"],
      confidence: 0.81,
    },
  ],
  research_findings: [
    {
      research_id: "research-lalita",
      title: "Lalita Kumari v. Government of Uttar Pradesh",
      excerpt: "Authority concerning mandatory registration where information discloses a cognizable offence.",
      source_url: "https://indiankanoon.org/doc/10239019/",
      citation: "(2014) 2 SCC 1",
      court: "Supreme Court of India",
      year: "2013",
      provider: "Indian Kanoon",
    },
  ],
  caveats: [
    {
      caveat_id: "caveat-annexure",
      severity: "blocking" as const,
      title: "Payment annexure missing",
      detail: "The document referenced as Annexure B was not included in the uploaded record.",
      evidence_ids: ["ev-money"],
    },
  ],
  workflow_version: "document-intelligence-v1",
  created_at: createdAt,
}

const preview: Workspace = {
  documents: [
    {
      document_id: documentId,
      version_id: versionId,
      original_name: "fir-registration-petition.pdf",
      media_type: "application/pdf",
      document_format: "pdf",
      sha256: "a".repeat(64),
      size_bytes: 842331,
      status: "ready",
      parser_name: "pymupdf",
      warnings: [],
      pages: [
        {
          page_number: 1,
          blocks: evidence.map((item, index) => ({
            block_id: item.source_spans[0].block_id,
            page_number: 1,
            sequence: index,
            kind: "paragraph",
            text: item.source_spans[0].exact_quote,
            confidence: item.confidence,
          })),
        },
      ],
      created_at: createdAt,
    },
  ],
  jobs: [
    {
      job_id: "44444444-4444-4444-8444-444444444444",
      status: "needs_review",
      attempts: 1,
      max_attempts: 3,
      run_id: "run-demo",
      report_id: report.report_id,
      updated_at: createdAt,
    },
  ],
  reports: [report, { ...report, report_id: "report-demo-v1", version: 1, status: "completed", created_at: "2026-07-16T11:00:00.000Z" }],
  latest_report: report,
  evidence,
  integrity: {
    valid: false,
    issues: [
      {
        code: "missing_document",
        severity: "blocking",
        message: "Annexure B is referenced but absent from the preserved record.",
        entity_type: "report_caveat",
        entity_id: "caveat-annexure",
      },
    ],
    checked_claims: 3,
    checked_evidence: 4,
    checked_spans: 4,
  },
  review_items: [
    {
      review_id: "review-annexure",
      source_type: "report_caveat",
      source_id: "caveat-annexure",
      severity: "blocking",
      reason: "Payment annexure missing: Annexure B was not included in the uploaded record.",
      status: "open",
    },
  ],
  review_decisions: [],
  research: {
    status: "completed",
    query: "mandatory FIR registration Section 154",
    findings: report.research_findings,
    warnings: [],
  },
}

function JudgeWorkspaceDemoContent() {
  const searchParams = useSearchParams()
  const initialRole = normalizeRole(searchParams.get("role"))
  const [role, setRole] = useState<AppRole>(initialRole)

  return (
    <div className={["nyaysetu-dashboard-theme", styles.page].join(" ")}>
      <div className={styles.roleBar}>
        <div><strong>Role preview</strong><span>The record remains identical across all three views.</span></div>
        <div className={styles.segments}>
          {(["lawyer", "judge", "citizen"] as AppRole[]).map((option) => (
            <button key={option} className={role === option ? styles.active : ""} onClick={() => setRole(option)}>
              {roleMeta[option].label}
            </button>
          ))}
        </div>
      </div>
      <JudgeWorkspace
        caseId={caseId}
        caseTitle="Ramesh Kumar v. State of Bihar"
        caseType="fir"
        district="Patna"
        caseStatus="under_attack"
        audience={role}
        initialWorkspace={preview}
        previewMode
      />
    </div>
  )
}
export default function JudgeWorkspaceDemo() {
  return (
    <Suspense fallback={<div className={["nyaysetu-dashboard-theme", styles.page].join(" ")}>Loading demo workspace...</div>}>
      <JudgeWorkspaceDemoContent />
    </Suspense>
  )
}
