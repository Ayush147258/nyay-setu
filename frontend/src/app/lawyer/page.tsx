import Link from "next/link"
import { redirect } from "next/navigation"
import LiveDocumentPipeline from "@/components/live/LiveDocumentPipeline"
import { ensureLiveRoleCase } from "@/lib/live-role-case"
import { auth } from "@/lib/auth"
import { isDemoEmail } from "@/lib/demo-accounts"
import { ArrowLeft, Gavel, Scale, UsersRound } from "lucide-react"

import styles from "./lawyer.module.css"

const risks = [
  { level: "High", title: "Date dispute", text: "Diary timestamp may be used to challenge the occurrence date. Lead with reporting delay and station refusal." },
  { level: "Medium", title: "Jurisdiction", text: "Bhagalpur boundary record supports filing, but keep a short location note ready." },
  { level: "Low", title: "Identity", text: "One witness statement is filed. The second witness affidavit should be collected before hearing." },
]

const tasks = [
  "Attach certified diary refusal copy",
  "Collect second witness affidavit",
  "Review jurisdiction paragraph",
  "Export final brief for senior counsel",
]

export default async function LawyerPage() {
  const session = await auth()
  const user = session?.user as { id?: string; tenantId?: string | null; email?: string | null } | undefined
  if (!user?.id) redirect("/login?callbackUrl=/lawyer")
  const demoAccount = isDemoEmail(user.email)
  const caseId = await ensureLiveRoleCase({ id: user.id, tenantId: user.tenantId }, "lawyer")

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}>
          <span>NS</span>
          NyaySetu Counsel
        </Link>
        <nav className={styles.roleNav} aria-label="Role pages">
          <Link className={styles.active} href="/lawyer"><Scale size={15} /> Lawyer</Link>
          <Link href="/judge"><Gavel size={15} /> Judge</Link>
          <Link href="/citizen"><UsersRound size={15} /> Citizen</Link>
        </nav>
        <Link href="/demo" className={styles.backLink}><ArrowLeft size={16} /> Choose track</Link>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.kicker}>Counsel brief builder</p>
          <h1>Build the argument from the record, not from guesswork.</h1>
          <p>
            Upload a case bundle, run the extractor and synthesis agents, watch the reviewer check integrity,
            and turn the result into a lawyer-ready final answer.
          </p>
        </div>
        <div className={styles.heroCard}>
          <span>{demoAccount ? "Demo account" : "Live mode"}</span>
          <strong>ON</strong>
          <p>{demoAccount ? "Signed in with the temporary demo account. PDF upload, RAG, and chat use the live backend." : "The pipeline below uses your signed-in document-intelligence workspace."}</p>
        </div>
      </section>

      <LiveDocumentPipeline role="lawyer" caseId={caseId} />

      <section className={styles.lowerGrid}>
        <article className={styles.riskBoard}>
          <p className={styles.kicker}>Counsel lens</p>
          <h2>What the lawyer page emphasizes</h2>
          {risks.map((risk) => (
            <div className={styles.riskItem} key={risk.title} data-level={risk.level.toLowerCase()}>
              <span>{risk.level}</span>
              <div>
                <h3>{risk.title}</h3>
                <p>{risk.text}</p>
              </div>
            </div>
          ))}
        </article>

        <article className={styles.checklistPanel}>
          <p className={styles.kicker}>Action list</p>
          <h2>Before export</h2>
          <div className={styles.checklist}>
            {tasks.map((task) => (
              <label key={task}>
                <input type="checkbox" />
                <span>{task}</span>
              </label>
            ))}
          </div>
        </article>
      </section>
    </main>
  )
}


