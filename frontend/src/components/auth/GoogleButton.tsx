"use client"

import { signIn } from "next-auth/react"
import { useSearchParams } from "next/navigation"
import { useState } from "react"

interface GoogleButtonProps {
  label: string
}

export default function GoogleButton({ label }: GoogleButtonProps) {
  const searchParams = useSearchParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const callbackUrl = searchParams.get("callbackUrl") || "/dashboard"

  async function continueWithGoogle() {
    setLoading(true)
    setError("")
    try {
      const result = await signIn("google", { callbackUrl, redirect: false })
      if (result?.error) {
        setLoading(false)
        setError("Google sign-in did not complete. Please try again.")
        return
      }
      window.location.href = result?.url || callbackUrl
    } catch {
      setLoading(false)
      setError("Google sign-in was cancelled or failed. You can retry now.")
    }
  }

  return (
    <div className="grid gap-3">
      <button type="button" className="auth-google" onClick={continueWithGoogle} disabled={loading}>
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 48 48">
          <path fill="#FFC107" d="M43.61 20.08H42V20H24v8h11.3C33.65 32.66 29.22 36 24 36c-6.63 0-12-5.37-12-12s5.37-12 12-12c3.06 0 5.84 1.15 7.96 3.04l5.66-5.66C34.05 6.05 29.27 4 24 4 12.95 4 4 12.95 4 24s8.95 20 20 20 20-8.95 20-20c0-1.34-.14-2.65-.39-3.92Z" />
          <path fill="#FF3D00" d="m6.31 14.69 6.57 4.82C14.66 15.11 18.96 12 24 12c3.06 0 5.84 1.15 7.96 3.04l5.66-5.66C34.05 6.05 29.27 4 24 4 16.32 4 9.66 8.34 6.31 14.69Z" />
          <path fill="#4CAF50" d="M24 44c5.16 0 9.86-1.98 13.41-5.21l-6.19-5.24C29.14 35.12 26.63 36 24 36c-5.2 0-9.62-3.31-11.28-7.93l-6.52 5.02C9.51 39.56 16.23 44 24 44Z" />
          <path fill="#1976D2" d="M43.61 20.08H42V20H24v8h11.3a12.04 12.04 0 0 1-4.09 5.55l.01-.01 6.19 5.24C36.97 39.18 44 34 44 24c0-1.34-.14-2.65-.39-3.92Z" />
        </svg>
        {loading ? "Redirecting to Google..." : label}
      </button>
      {error ? (
        <div className="rounded-[10px] border border-[#f2b8b5] bg-[#fff1f0] p-3 text-sm text-[#a32d2d]">
          {error} <button className="font-semibold underline" type="button" onClick={continueWithGoogle}>Retry</button>
        </div>
      ) : null}
    </div>
  )
}
