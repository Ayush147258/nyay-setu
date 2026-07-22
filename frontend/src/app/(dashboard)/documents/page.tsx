import Link from "next/link"
import { desc, eq } from "drizzle-orm"
import { redirect } from "next/navigation"
import { IconArrowRight, IconFileDescription, IconFolderOpen } from "@tabler/icons-react"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { cases } from "@/db/schema"

export const dynamic = "force-dynamic"

export default async function DocumentsPage() {
  const session = await auth()
  const userId = session?.user
    ? (session.user as typeof session.user & { id?: string }).id
    : undefined
  if (!userId) redirect("/login")

  const db = getDb()
  const caseRows = await db
    .select()
    .from(cases)
    .where(eq(cases.userId, userId))
    .orderBy(desc(cases.updatedAt))
    .limit(100)

  return (
    <div>
      <div className="topbar">
        <div>
          <div className="docket-tag">Track C · document intelligence</div>
          <h1>Document workspaces</h1>
          <p className="sub">Open a case to ingest sources, inspect evidence, and review versioned reports.</p>
        </div>
        <Link href="/new-case" className="btn-primary">New case</Link>
      </div>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Case records</h2>
            <p className="panel-sub">Each workspace is isolated to its owner and preserved document versions.</p>
          </div>
          <span className="pill pill-processing">{caseRows.length} cases</span>
        </div>
        {caseRows.length ? (
          <div className="case-list">
            {caseRows.map((legalCase) => (
              <Link className="case-row" href={`/cases/${legalCase.id}/workspace`} key={legalCase.id}>
                <span className="case-avatar" style={{ background: "var(--indigo)" }}>
                  <IconFileDescription size={17} />
                </span>
                <div className="case-body">
                  <p className="name">{legalCase.title}</p>
                  <p className="meta">
                    <span className="file-no">{legalCase.id.slice(0, 8)}</span>
                    {" · "}{legalCase.caseType.replaceAll("_", " ")}
                    {legalCase.district ? ` · ${legalCase.district}` : ""}
                  </p>
                  <p className="time">Updated {legalCase.updatedAt?.toLocaleDateString("en-IN")}</p>
                </div>
                <div className="case-side">
                  <span className="pill pill-pending">{(legalCase.status ?? "intake").replaceAll("_", " ")}</span>
                  <IconArrowRight size={16} />
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <IconFolderOpen size={28} />
            <p>No case records are available yet.</p>
            <Link href="/new-case" className="btn-primary">Create the first case</Link>
          </div>
        )}
      </section>
    </div>
  )
}
