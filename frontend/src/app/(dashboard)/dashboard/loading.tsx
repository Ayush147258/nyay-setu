export default function DashboardLoading() {
  return (
    <div className="animate-pulse">
      <section className="stats-grid mb-6">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="stat-card border border-[var(--color-border-tertiary)] bg-white/50">
            <div className="stat-top">
              <div className="h-6 w-6 rounded-full bg-gray-200"></div>
              <div className="h-4 w-12 rounded bg-gray-200"></div>
            </div>
            <div className="mt-4 h-8 w-16 rounded bg-gray-200"></div>
            <div className="mt-2 h-4 w-32 rounded bg-gray-200"></div>
          </div>
        ))}
      </section>

      <section className="content-grid">
        <div className="panel bg-white/50 border border-[var(--color-border-tertiary)]">
          <div className="panel-head border-b border-[var(--color-border-tertiary)] pb-4">
            <div className="w-full">
              <div className="h-6 w-48 bg-gray-200 rounded mb-2"></div>
              <div className="h-4 w-64 bg-gray-200 rounded"></div>
            </div>
          </div>
          <div className="h-[250px] w-full bg-gray-100 rounded my-4"></div>
          <div className="h-4 w-40 bg-gray-200 rounded mt-4"></div>
        </div>

        <div className="panel bg-white/50 border border-[var(--color-border-tertiary)]">
          <div className="panel-head border-b border-[var(--color-border-tertiary)] pb-4">
            <div className="w-full">
              <div className="h-6 w-32 bg-gray-200 rounded mb-2"></div>
              <div className="h-4 w-48 bg-gray-200 rounded"></div>
            </div>
          </div>
          <div className="case-list mt-4 flex flex-col gap-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex gap-4 items-center pb-4 border-b border-gray-100 last:border-0">
                <div className="h-10 w-10 rounded-full bg-gray-200 shrink-0"></div>
                <div className="flex-1">
                  <div className="h-5 w-32 bg-gray-200 rounded mb-1.5"></div>
                  <div className="h-3 w-48 bg-gray-200 rounded"></div>
                </div>
                <div className="h-6 w-16 bg-gray-200 rounded-full shrink-0"></div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
