export default function ArenaLoading() {
  return (
    <div className="arena-grid animate-pulse">
      {/* Left panel skeleton */}
      <aside className="arena-side flex flex-col gap-6">
        <div className="border border-[var(--color-border-tertiary)] bg-white/50 rounded-lg p-5">
          <div className="h-4 w-24 bg-gray-200 rounded mb-4"></div>
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex gap-3 items-center">
                <div className="h-8 w-8 rounded-full bg-gray-200"></div>
                <div className="h-3 w-20 bg-gray-200 rounded"></div>
              </div>
            ))}
          </div>
        </div>
        <div className="border border-[var(--color-border-tertiary)] bg-white/50 rounded-lg p-5">
          <div className="h-4 w-32 bg-gray-200 rounded mb-4"></div>
          <div className="space-y-3">
            <div className="h-3 w-full bg-gray-200 rounded"></div>
            <div className="h-3 w-2/3 bg-gray-200 rounded"></div>
            <div className="h-3 w-5/6 bg-gray-200 rounded"></div>
          </div>
        </div>
      </aside>

      {/* Center chat skeleton */}
      <section className="dash-card arena-chat flex flex-col">
        <div className="ch border-b border-[var(--color-border-tertiary)] flex justify-between items-center pb-4">
          <div>
            <div className="h-6 w-32 bg-gray-200 rounded mb-2"></div>
            <div className="h-4 w-48 bg-gray-200 rounded"></div>
          </div>
          <div className="h-6 w-24 bg-gray-200 rounded-full"></div>
        </div>
        <div className="arena-feed flex-1 p-6 flex flex-col gap-6">
          <div className="mx-auto h-4 w-48 bg-gray-200 rounded"></div>
          {[...Array(3)].map((_, i) => (
            <div key={i} className="flex gap-4">
              <div className="h-10 w-10 rounded-full bg-gray-200 shrink-0"></div>
              <div className="flex-1 border border-gray-100 rounded-lg p-4 bg-white/30">
                <div className="h-4 w-24 bg-gray-200 rounded mb-3"></div>
                <div className="space-y-2">
                  <div className="h-3 w-full bg-gray-200 rounded"></div>
                  <div className="h-3 w-5/6 bg-gray-200 rounded"></div>
                  <div className="h-3 w-4/6 bg-gray-200 rounded"></div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Right document skeleton */}
      <aside className="border-l border-[var(--color-border-tertiary)] bg-[var(--cream)]/30 flex flex-col h-full overflow-hidden">
        <div className="p-4 border-b border-[var(--color-border-tertiary)] bg-white/50">
          <div className="h-5 w-40 bg-gray-200 rounded mb-2"></div>
          <div className="h-3 w-24 bg-gray-200 rounded"></div>
        </div>
        <div className="flex-1 p-8">
          <div className="bg-white shadow-sm border border-gray-200 rounded w-full h-full p-8 flex flex-col gap-4">
            <div className="h-6 w-1/2 bg-gray-200 rounded mx-auto mb-8"></div>
            <div className="h-4 w-1/3 bg-gray-200 rounded"></div>
            <div className="h-4 w-1/4 bg-gray-200 rounded mb-6"></div>
            
            <div className="space-y-3 mt-4">
              {[...Array(12)].map((_, i) => (
                <div key={i} className={`h-3 bg-gray-200 rounded ${i % 4 === 0 ? 'w-full' : i % 3 === 0 ? 'w-5/6' : 'w-11/12'}`}></div>
              ))}
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}
