import Link from "next/link"
import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  BrainCircuit,
  FileText,
  Gavel,
  Layers3,
  LockKeyhole,
  MessageSquareText,
  Scale,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UsersRound,
} from "lucide-react"

import styles from "./page.module.css"

const pipeline = [
  {
    icon: UploadCloud,
    label: "01",
    title: "Upload record",
    text: "PDFs, scans, pleadings, emails, and handwritten notes enter one secure case workspace.",
    accent: "teal",
  },
  {
    icon: BrainCircuit,
    label: "02",
    title: "Extractor agent",
    text: "The backend extracts facts, dates, parties, citations, contradictions, and missing proof.",
    accent: "gold",
  },
  {
    icon: Layers3,
    label: "03",
    title: "Synthesis agent",
    text: "Evidence atoms become a structured legal brief with source cards and integrity checks.",
    accent: "ruby",
  },
  {
    icon: ShieldCheck,
    label: "04",
    title: "Reviewer agent",
    text: "Unsupported claims are flagged before the final answer reaches any role-specific panel.",
    accent: "blue",
  },
]

const rolePreviews = [
  {
    icon: Scale,
    title: "Lawyer lens",
    eyebrow: "Argument builder",
    text: "Strongest claim, weak-point attack map, missing proof, and counsel-ready final answer.",
  },
  {
    icon: Gavel,
    title: "Judge lens",
    eyebrow: "Neutral bench view",
    text: "Chronology, issue framing, source spans, conflicts, caveats, and record integrity status.",
  },
  {
    icon: UsersRound,
    title: "Citizen lens",
    eyebrow: "Plain-language guide",
    text: "Simple explanation, next actions, document checklist, and questions to ask before filing.",
  },
]

const proofPoints = [
  "Citation-grounded chat",
  "Document upload and storage",
  "Live pipeline visibility",
  "Role-specific final answers",
]

export default function LandingPage() {
  return (
    <main className={styles.page}>
      <header className={styles.navbar}>
        <Link href="/" className={styles.brand} aria-label="NyaySetu home">
          <span className={styles.brandMark}>NS</span>
          <span>
            <strong>NyaySetu</strong>
            <small>Document Intelligence</small>
          </span>
        </Link>

        <nav className={styles.navLinks} aria-label="Landing page sections">
          <a href="#pipeline">Pipeline</a>
          <a href="#roles">Roles</a>
          <a href="#integrity">Integrity</a>
        </nav>

        <div className={styles.navActions}>
          <Link href="/login" className={styles.loginLink}>Sign in</Link>
          <Link href="/demo" className={styles.navButton}>
            Try demo <ArrowRight size={16} />
          </Link>
        </div>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroGrid}>
          <div className={styles.heroCopy}>
            <p className={styles.kicker}><Sparkles size={15} /> Legal AI workspace for real records</p>
            <h1>Turn complex legal documents into clear answers for every side.</h1>
            <p className={styles.lede}>
              NyaySetu uploads the source record, extracts facts through backend agents, verifies integrity, and generates separate lawyer, judge, and citizen answers from the same evidence.
            </p>

            <div className={styles.heroActions}>
              <Link href="/demo" className={styles.primaryButton}>
                Try demo <ArrowRight size={18} />
              </Link>
              <a href="#pipeline" className={styles.secondaryButton}>
                See live pipeline
              </a>
            </div>

            <div className={styles.proofStrip} aria-label="Product capabilities">
              {proofPoints.map((point) => (
                <span key={point}><BadgeCheck size={15} /> {point}</span>
              ))}
            </div>
          </div>

          <div className={styles.sceneWrap} aria-label="Animated preview of the NyaySetu document pipeline">
            <div className={styles.sceneStage}>
              <div className={styles.gridPlane} />
              <div className={styles.documentStack}>
                <div className={`${styles.sheet} ${styles.sheetBack}`} />
                <div className={`${styles.sheet} ${styles.sheetMid}`} />
                <div className={`${styles.sheet} ${styles.sheetFront}`}>
                  <div className={styles.sheetHeader}>
                    <span>Case bundle</span>
                    <FileText size={16} />
                  </div>
                  <div className={styles.redactedLine} />
                  <div className={styles.redactedLineShort} />
                  <div className={styles.highlightLine} />
                  <div className={styles.redactedLineWide} />
                  <div className={styles.scanBeam} />
                </div>
              </div>

              <div className={`${styles.agentNode} ${styles.nodeOne}`}>
                <BrainCircuit size={18} />
                <span>Extract</span>
              </div>
              <div className={`${styles.agentNode} ${styles.nodeTwo}`}>
                <BookOpenCheck size={18} />
                <span>Synth</span>
              </div>
              <div className={`${styles.agentNode} ${styles.nodeThree}`}>
                <ShieldCheck size={18} />
                <span>Review</span>
              </div>

              <div className={styles.resultConsole}>
                <div className={styles.consoleHeader}>
                  <span>Answer router</span>
                  <span className={styles.liveDot}>Live</span>
                </div>
                <div className={styles.consoleRows}>
                  <span>Lawyer: proof gap</span>
                  <span>Judge: neutral chronology</span>
                  <span>Citizen: next action</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.metricsBand} aria-label="NyaySetu scalability signals">
        <div>
          <strong>Multi-format</strong>
          <span>PDF, DOCX, text, scans</span>
        </div>
        <div>
          <strong>Multi-agent</strong>
          <span>Extractor, synthesis, reviewer</span>
        </div>
        <div>
          <strong>Role-aware</strong>
          <span>Lawyer, judge, citizen</span>
        </div>
        <div>
          <strong>Evidence-first</strong>
          <span>Answers cite uploaded records</span>
        </div>
      </section>

      <section id="pipeline" className={styles.pipelineSection}>
        <div className={styles.sectionHead}>
          <p className={styles.kicker}><Layers3 size={15} /> Live backend pipeline</p>
          <h2>Show the agent system working, not just a static chatbot.</h2>
          <p>
            The landing page now explains the real product promise: upload documents, preserve them, extract evidence, synthesize a report, review integrity, then answer through the selected role panel.
          </p>
        </div>

        <div className={styles.pipelineGrid}>
          {pipeline.map((step) => {
            const Icon = step.icon
            return (
              <article className={styles.pipelineStep} data-accent={step.accent} key={step.title}>
                <div className={styles.stepTop}>
                  <span>{step.label}</span>
                  <Icon size={22} />
                </div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </article>
            )
          })}
        </div>
      </section>

      <section id="roles" className={styles.roleSection}>
        <div className={styles.sectionHeadCompact}>
          <p className={styles.kicker}><MessageSquareText size={15} /> Three panels after demo</p>
          <h2>One record. Three different reading experiences.</h2>
        </div>

        <div className={styles.roleGrid}>
          {rolePreviews.map((role) => {
            const Icon = role.icon
            return (
              <article className={styles.roleCard} key={role.title}>
                <div className={styles.roleIcon}><Icon size={23} /></div>
                <p>{role.eyebrow}</p>
                <h3>{role.title}</h3>
                <span>{role.text}</span>
              </article>
            )
          })}
        </div>

        <div className={styles.roleCta}>
          <div>
            <strong>Demo flow stays correct.</strong>
            <span>Click Try demo first, then choose Lawyer, Judge, or Citizen in the track chooser.</span>
          </div>
          <Link href="/demo" className={styles.primaryButton}>
            Open track chooser <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      <section id="integrity" className={styles.integritySection}>
        <div className={styles.integrityCopy}>
          <p className={styles.kicker}><LockKeyhole size={15} /> Data integrity layer</p>
          <h2>Built for Track C: extraction, synthesis, and consistency at scale.</h2>
          <p>
            NyaySetu is positioned as an intelligent document synthesis agent: the extractor pulls raw facts from unstructured records, synthesis compiles them into business/legal reports, and reviewer checks preserve source integrity before role answers are generated.
          </p>
        </div>

        <div className={styles.integrityRail}>
          <div><span>01</span> Raw source preserved</div>
          <div><span>02</span> Evidence atoms created</div>
          <div><span>03</span> Citations attached</div>
          <div><span>04</span> Reviewer flags gaps</div>
          <div><span>05</span> Final answer routed</div>
        </div>
      </section>
    </main>
  )
}
