import Link from "next/link"
import { ArrowRight, BriefcaseBusiness, Gavel, ShieldCheck, UserRound } from "lucide-react"
import type { AppRole } from "@/lib/roles"
import { demoAccountForRole } from "@/lib/demo-accounts"
import styles from "./demo.module.css"

const roleOptions: Array<{
  role: AppRole
  title: string
  label: string
  description: string
  details: string[]
  icon: typeof Gavel
}> = [
  {
    role: "lawyer",
    title: "Lawyer Track",
    label: "Counsel preparation",
    description: "Open the advocate view for weak-point mapping, evidence-backed arguments, and likely bench questions.",
    details: ["Opponent challenge map", "Case preparation checklist", "Evidence-backed response plan"],
    icon: BriefcaseBusiness,
  },
  {
    role: "judge",
    title: "Judge Track",
    label: "Neutral bench review",
    description: "Open the judicial review view for chronology, source spans, integrity findings, and unresolved caveats.",
    details: ["Neutral record analysis", "Exact source citations", "Integrity and review controls"],
    icon: Gavel,
  },
  {
    role: "citizen",
    title: "Citizen Track",
    label: "Plain-language case status",
    description: "Open the citizen view for clear progress, delay reasons, and questions to ask before the next lawyer meeting.",
    details: ["Simple case status", "Delay explanation", "Questions for your lawyer"],
    icon: UserRound,
  },
]

export default function DemoRolePage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="NyaySetu landing page">
          <span className={styles.brandMark}><Gavel size={18} /></span>
          <span>NyaySetu</span>
        </Link>
        <Link href="/" className={styles.backLink}>Back to landing</Link>
      </header>

      <section className={styles.hero}>
        <span className={styles.eyebrow}><ShieldCheck size={15} /> Public demo</span>
        <h1>Choose your Track C workspace</h1>
        <p>Select how you want to inspect the same legal record. The underlying evidence stays identical; NyaySetu changes the workflow around the role.</p>
      </section>

      <section className={styles.roleGrid} aria-label="Choose a NyaySetu demo track">
        {roleOptions.map((option) => {
          const Icon = option.icon
          return (
            <Link key={option.role} href={`/login?callbackUrl=${demoAccountForRole(option.role).route}&demoRole=${option.role}`} className={styles.rolePanel}>
              <div className={styles.roleTop}>
                <span className={styles.icon}><Icon size={25} /></span>
                <span className={styles.track}>{option.label}</span>
              </div>
              <h2>{option.title}</h2>
              <p>{option.description}</p>
              <ul>
                {option.details.map((detail) => <li key={detail}>{detail}</li>)}
              </ul>
              <span className={styles.openTrack}>Open track <ArrowRight size={16} /></span>
            </Link>
          )
        })}
      </section>
    </main>
  )
}


