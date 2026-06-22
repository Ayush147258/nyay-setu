import { IconScale } from "@tabler/icons-react"

export default function AuthSkeleton() {
  return (
    <div className="auth-full-card animate-pulse">
      <div className="auth-logo opacity-50" aria-hidden="true">
        <span className="auth-logo-icon bg-gray-200 text-transparent"><IconScale size={18} /></span>
        <div className="flex flex-col gap-1.5 ml-2">
          <div className="h-4 w-20 bg-gray-200 rounded"></div>
          <div className="h-3 w-48 bg-gray-200 rounded"></div>
        </div>
      </div>

      <div className="mt-8 mb-2 h-7 w-40 bg-gray-200 rounded"></div>
      <div className="mb-6 h-4 w-64 bg-gray-200 rounded"></div>

      <div className="w-full h-[46px] bg-gray-200 rounded border border-gray-300"></div>

      <div className="mt-6 flex justify-center">
        <div className="h-4 w-48 bg-gray-200 rounded"></div>
      </div>
      
      <div className="mt-8 flex justify-center">
        <div className="h-3 w-56 bg-gray-200 rounded opacity-50"></div>
      </div>
    </div>
  )
}
