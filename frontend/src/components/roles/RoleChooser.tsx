"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import {
  IconBriefcase2,
  IconCheck,
  IconGavel,
  IconLoader2,
  IconUser,
} from "@tabler/icons-react"
import type { AppRole } from "@/lib/roles"
import styles from "./RoleChooser.module.css"

const choices: Array<{
  role: AppRole
  title: string
  kicker: string
  description: string
  outcomes: string[]
  icon: typeof IconGavel
}> = [
  {
    role: "lawyer",
    title: "I represent a party",
    kicker: "Counsel preparation",
    description: "Pressure-test the record before the hearing and prepare grounded answers.",
    outcomes: ["Opponent challenge map", "Likely bench questions", "Evidence-backed response plan"],
    icon: IconBriefcase2,
  },
  {
    role: "judge",
    title: "I review matters neutrally",
    kicker: "Bench review",
    description: "Inspect evidence, chronology, authorities, integrity, and unresolved caveats.",
    outcomes: ["Neutral record analysis", "Exact source spans", "Integrity and review controls"],
    icon: IconGavel,
  },
  {
    role: "citizen",
    title: "I am tracking my case",
    kicker: "Case understanding",
    description: "Understand progress, possible delay causes, and what to ask your lawyer next.",
    outcomes: ["Plain-language status", "Delay explanation", "Questions for your lawyer"],
    icon: IconUser,
  },
]

export default function RoleChooser({ currentRole }: { currentRole?: AppRole }) {
  const router = useRouter()
  const [selected, setSelected] = useState<AppRole | null>(null)
  const [error, setError] = useState("")

  async function choose(role: AppRole) {
    setSelected(role)
    setError("")
    try {
      const response = await fetch("/api/profile/role", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      })
      const payload = await response.json().catch(() => ({})) as { error?: string }
      if (!response.ok) throw new Error(payload.error || "Could not update your role")
      router.push("/dashboard")
      router.refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update your role")
      setSelected(null)
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}><IconGavel size={21} /> NyaySetu</div>
        <span>Role can be changed later</span>
      </header>

      <section className={styles.intro}>
        <span className={styles.eyebrow}>Choose your working view</span>
        <h1>How are you approaching this case?</h1>
        <p>The underlying evidence stays the same. NyaySetu changes the questions, controls, and preparation view around your work.</p>
      </section>

      <section className={styles.roleGrid} aria-label="NyaySetu roles">
        {choices.map((choice) => {
          const Icon = choice.icon
          const busy = selected === choice.role
          const active = currentRole === choice.role
          return (
            <article key={choice.role} className={active ? styles.current : undefined}>
              <div className={styles.roleTop}>
                <span className={styles.icon}><Icon size={24} /></span>
                {active ? <span className={styles.activeLabel}><IconCheck size={13} /> Current</span> : null}
              </div>
              <span className={styles.kicker}>{choice.kicker}</span>
              <h2>{choice.title}</h2>
              <p>{choice.description}</p>
              <ul>
                {choice.outcomes.map((outcome) => <li key={outcome}><IconCheck size={14} /> {outcome}</li>)}
              </ul>
              <button onClick={() => void choose(choice.role)} disabled={selected !== null}>
                {busy ? <IconLoader2 className={styles.spin} size={17} /> : <Icon size={17} />}
                {busy ? "Opening workspace" : `Continue as ${choice.kicker.split(" ")[0]}`}
              </button>
            </article>
          )
        })}
      </section>

      {error ? <div className={styles.error} role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div> : null}
      <p className={styles.note}>Role selection personalizes presentation only. Access to cases and documents remains governed by account ownership.</p>
    </main>
  )
}
