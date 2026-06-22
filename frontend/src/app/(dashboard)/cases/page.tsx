import { and, asc, desc, eq, ilike, or, count } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { cases, type LegalCase } from "@/db/schema"
import CasesTable from "@/components/dashboard/CasesTable"
import EmptyState from "@/components/dashboard/EmptyState"
import CaseListToolbar from "@/components/dashboard/CaseListToolbar"
import Link from "next/link"
import { Suspense } from "react"

export const dynamic = "force-dynamic"

function CasesSkeleton() {
  return (
    <div className="animate-pulse flex flex-col gap-4 mt-6">
      <div className="h-10 bg-gray-200 rounded w-full opacity-20"></div>
      <div className="h-16 bg-gray-200 rounded w-full opacity-20"></div>
      <div className="h-16 bg-gray-200 rounded w-full opacity-20"></div>
      <div className="h-16 bg-gray-200 rounded w-full opacity-20"></div>
      <div className="h-16 bg-gray-200 rounded w-full opacity-20"></div>
    </div>
  )
}

async function CaseList({
  userId,
  searchParams,
}: {
  userId: string
  searchParams: { q?: string; type?: string; status?: string; sort?: string; page?: string }
}) {
  const db = getDb()
  const q = searchParams.q || ""
  const typeFilter = searchParams.type || ""
  const statusFilter = searchParams.status || ""
  const sortOrder = searchParams.sort === "asc" ? asc : desc
  const page = Math.max(1, parseInt(searchParams.page || "1", 10))
  const limit = 20
  const offset = (page - 1) * limit

  const conditions = [eq(cases.userId, userId)]

  if (q) {
    conditions.push(
      or(
        ilike(cases.title, `%${q}%`),
        ilike(cases.rawInput, `%${q}%`)
      )!
    )
  }

  if (typeFilter) {
    conditions.push(eq(cases.caseType, typeFilter))
  }

  if (statusFilter) {
    conditions.push(eq(cases.status, statusFilter))
  }

  const queryCondition = and(...conditions)

  const [totalResult] = await db
    .select({ count: count() })
    .from(cases)
    .where(queryCondition)

  const total = totalResult.count

  const rows: LegalCase[] = await db
    .select()
    .from(cases)
    .where(queryCondition)
    .orderBy(sortOrder(cases.updatedAt))
    .limit(limit)
    .offset(offset)

  if (rows.length === 0 && (q || typeFilter || statusFilter)) {
    return (
      <div className="text-center py-12 text-[var(--muted)]">
        <p className="text-lg">No cases found matching your filters.</p>
        <p className="text-sm mt-2">Try adjusting your search query or removing filters.</p>
      </div>
    )
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <>
      <CasesTable cases={rows} />
      
      {totalPages > 1 && (
        <div className="flex justify-between items-center mt-6 border-t border-[var(--color-border-tertiary)] pt-4">
          <div className="text-sm text-[var(--muted)]">
            Showing {offset + 1} to {Math.min(offset + limit, total)} of {total} cases
          </div>
          <div className="flex gap-2">
            {page > 1 ? (
              <Link href={`?${new URLSearchParams({ ...searchParams, page: (page - 1).toString() }).toString()}`} className="btn">
                Previous
              </Link>
            ) : (
              <button className="btn opacity-50 cursor-not-allowed" disabled>Previous</button>
            )}
            
            {page < totalPages ? (
              <Link href={`?${new URLSearchParams({ ...searchParams, page: (page + 1).toString() }).toString()}`} className="btn">
                Next
              </Link>
            ) : (
              <button className="btn opacity-50 cursor-not-allowed" disabled>Next</button>
            )}
          </div>
        </div>
      )}
    </>
  )
}

export default async function CasesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; type?: string; status?: string; sort?: string; page?: string }>
}) {
  const session = await auth()
  const userId = session?.user ? (session.user as typeof session.user & { id?: string }).id : undefined
  
  if (!userId) {
    return null
  }

  const db = getDb()
  const [totalCountResult] = await db
    .select({ count: count() })
    .from(cases)
    .where(eq(cases.userId, userId))

  const totalUserCases = totalCountResult.count

  if (totalUserCases === 0) {
    return <EmptyState />
  }

  const params = await searchParams

  return (
    <div className="dash-card">
      <div className="ch border-b border-[var(--color-border-tertiary)] pb-4 mb-6">
        <div>
          <div className="ct">Case Library</div>
          <div className="cs">Search, filter, and manage all your dockets</div>
        </div>
      </div>
      
      <Suspense fallback={null}>
        <CaseListToolbar />
      </Suspense>

      <Suspense fallback={<CasesSkeleton />}>
        <CaseList userId={userId} searchParams={params} />
      </Suspense>
    </div>
  )
}
