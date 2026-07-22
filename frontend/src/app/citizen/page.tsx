import Link from "next/link"
import { redirect } from "next/navigation"
import LiveDocumentPipeline from "@/components/live/LiveDocumentPipeline"
import { ensureLiveRoleCase } from "@/lib/live-role-case"
import { auth } from "@/lib/auth"
import { isDemoEmail } from "@/lib/demo-accounts"
import { ArrowLeft, Gavel, HeartHandshake, Languages, MapPinned, Scale, Sparkles, UploadCloud, UsersRound } from "lucide-react"

import styles from "./citizen.module.css"

const steps = [
  { title: "Upload papers", text: "Complaint, police diary note, ID proof, or any photo of the document." },
  { title: "Watch agents read", text: "The live pipeline shows extraction, synthesis, reviewer checks, and the final answer." },
  { title: "Take action", text: "You get a safe next step and a checklist before visiting court or police station." },
]

const tasks = [
  "Keep one copy of every paper",
  "Ask for police diary refusal proof",
  "Carry ID and address proof",
  "Read the simple guide before going to court",
]

export default async function CitizenPage() {
  const session = await auth()
  const user = session?.user as { id?: string; tenantId?: string | null; email?: string | null } | undefined
  if (!user?.id) redirect("/login?callbackUrl=/citizen")
  const demoAccount = isDemoEmail(user.email)
  const caseId = await ensureLiveRoleCase({ id: user.id, tenantId: user.tenantId }, "citizen")

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}><span><HeartHandshake size={18} /></span> NyaySetu Guide</Link>
        <nav className={styles.roleNav} aria-label="Role pages">
          <Link href="/lawyer"><Scale size={15} /> Lawyer</Link>
          <Link href="/judge"><Gavel size={15} /> Judge</Link>
          <Link className={styles.active} href="/citizen"><UsersRound size={15} /> Citizen</Link>
        </nav>
        <Link href="/demo" className={styles.backLink}><ArrowLeft size={16} /> Choose track</Link>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroText}>
          <p className={styles.kicker}>Citizen help room</p>
          <h1>Your legal papers, explained like a clear next step.</h1>
          <p>
            Upload the documents you have. NyaySetu runs the backend document pipeline and turns the verified record into simple guidance.
          </p>
          <div className={styles.heroActions}>
            <a href="#live-pipeline"><UploadCloud size={17} /> Upload papers</a>
            <button type="button" className={styles.softButton}><Languages size={17} /> Change language</button>
          </div>
        </div>
        <div className={styles.nextCard}>
          <Sparkles size={28} />
          <span>{demoAccount ? "Demo account" : "Live mode"}</span>
          <strong>Upload, run, then read your source-grounded answer.</strong>
          <p>{demoAccount ? "Signed in with the temporary demo account. Uploaded papers are stored and analyzed through the live backend." : "This page uses your signed-in backend workspace so uploaded papers can be stored and analyzed."}</p>
        </div>
      </section>

      <section className={styles.stepPath}>
        {steps.map((step, index) => (
          <article key={step.title}>
            <span>{index + 1}</span>
            <h2>{step.title}</h2>
            <p>{step.text}</p>
          </article>
        ))}
      </section>

      <LiveDocumentPipeline role="citizen" caseId={caseId} />

      <section className={styles.actionGrid}>
        <article className={styles.checkPanel}>
          <p className={styles.kicker}>Action list</p>
          <h2>Before you go</h2>
          <div className={styles.checklist}>
            {tasks.map((task) => (
              <label key={task}>
                <input type="checkbox" />
                <span>{task}</span>
              </label>
            ))}
          </div>
        </article>

        <article className={styles.mapPanel}>
          <MapPinned size={24} />
          <p className={styles.kicker}>Where this goes</p>
          <h2>Magistrate court counter</h2>
          <p>Carry your filing draft, refusal proof, ID proof, and copies. Ask for help submitting the Section 156(3) application.</p>
        </article>
      </section>
    </main>
  )
}


