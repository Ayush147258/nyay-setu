import Link from "next/link"
import { redirect } from "next/navigation"
import LiveDocumentPipeline from "@/components/live/LiveDocumentPipeline"
import { ensureLiveRoleCase } from "@/lib/live-role-case"
import { auth } from "@/lib/auth"
import { isDemoEmail } from "@/lib/demo-accounts"
import { ArrowLeft, Gavel, Landmark, Scale, UsersRound } from "lucide-react"

import styles from "./judge.module.css"

const queue = [
  { id: "156/CRPC", title: "FIR refusal", status: "Ready for upload" },
  { id: "DV-21", title: "Protection order", status: "Waiting" },
  { id: "CPA-04", title: "Consumer defect", status: "Waiting" },
]

export default async function JudgePage() {
  const session = await auth()
  const user = session?.user as { id?: string; tenantId?: string | null; email?: string | null } | undefined
  if (!user?.id) redirect("/login?callbackUrl=/judge")
  const demoAccount = isDemoEmail(user.email)
  const caseId = await ensureLiveRoleCase({ id: user.id, tenantId: user.tenantId }, "judge")

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}><span><Landmark size={17} /></span> NyaySetu Bench</Link>
        <nav className={styles.roleNav} aria-label="Role pages">
          <Link href="/lawyer"><Scale size={15} /> Lawyer</Link>
          <Link className={styles.active} href="/judge"><Gavel size={15} /> Judge</Link>
          <Link href="/citizen"><UsersRound size={15} /> Citizen</Link>
        </nav>
        <Link href="/demo" className={styles.backLink}><ArrowLeft size={16} /> Choose track</Link>
      </header>

      <section className={styles.headerPanel}>
        <div>
          <p className={styles.kicker}>Bench review queue</p>
          <h1>Review the record with chronology, caveats, and exact source spans.</h1>
          <p>
            Upload the bundle below and run the live analysis. The judge page keeps extracted facts,
            legal inference, caveats, and final observations separated.
          </p>
        </div>
        <div className={styles.sourceBadge}>
          <span>{demoAccount ? "Demo account" : "Live trace"}</span>
          <strong>Ready</strong>
          <small>Source-span counts update after the reviewer finishes.</small>
        </div>
      </section>

      <section className={styles.queueStrip} aria-label="Review queue">
        {queue.map((item, index) => (
          <article className={index === 0 ? styles.selectedQueue : ""} key={item.id}>
            <span>{item.id}</span>
            <strong>{item.title}</strong>
            <small>{item.status}</small>
          </article>
        ))}
      </section>

      <LiveDocumentPipeline role="judge" caseId={caseId} />
    </main>
  )
}


