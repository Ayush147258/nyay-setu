"use client"

import { useMemo, useState } from "react"
import { signIn } from "next-auth/react"
import { useSearchParams } from "next/navigation"
import { ArrowRight, Gavel, Scale, Shield, UsersRound } from "lucide-react"
import { DEMO_ACCOUNTS, DEMO_ACCOUNT_PASSWORD, type DemoRole } from "@/lib/demo-accounts"

const icons: Record<DemoRole, typeof Scale> = {
  lawyer: Scale,
  judge: Gavel,
  citizen: UsersRound,
}

function safeCallbackUrl(value: string | null, roleRoute: string) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return roleRoute
  if (["/lawyer", "/judge", "/citizen"].some((route) => value === route || value.startsWith(`${route}/`))) {
    return value === roleRoute || value.startsWith(`${roleRoute}/`) ? value : roleRoute
  }
  return value
}

export default function DemoAccountButtons() {
  const searchParams = useSearchParams()
  const [loadingRole, setLoadingRole] = useState<DemoRole | null>(null)
  const [error, setError] = useState("")
  const callbackUrl = searchParams.get("callbackUrl")
  const preferredRole = searchParams.get("demoRole")
  const accounts = useMemo(() => {
    if (!preferredRole) return DEMO_ACCOUNTS
    const selected = DEMO_ACCOUNTS.find((account) => account.role === preferredRole)
    return selected ? [selected, ...DEMO_ACCOUNTS.filter((account) => account.role !== selected.role)] : DEMO_ACCOUNTS
  }, [preferredRole])

  async function useDemo(role: DemoRole, email: string, route: string) {
    setLoadingRole(role)
    setError("")
    const nextUrl = safeCallbackUrl(callbackUrl, route)
    try {
      const result = await signIn("credentials", {
        email,
        password: DEMO_ACCOUNT_PASSWORD,
        callbackUrl: nextUrl,
        redirect: false,
      })
      if (result?.error) {
        setLoadingRole(null)
        setError("Demo sign-in failed. Check that the database schema is available, then try again.")
        return
      }
      window.location.href = result?.url || nextUrl
    } catch {
      setLoadingRole(null)
      setError("Demo sign-in could not reach the auth service.")
    }
  }

  return (
    <section className="auth-demo-block" aria-label="Hackathon demo accounts">
      <div className="auth-demo-heading">Hackathon demo accounts</div>
      <div className="auth-demo-list">
        {accounts.map((account) => {
          const Icon = icons[account.role]
          return (
            <button
              type="button"
              className={`auth-demo-card auth-demo-${account.role}`}
              key={account.role}
              onClick={() => void useDemo(account.role, account.email, account.route)}
              disabled={Boolean(loadingRole)}
            >
              <span className="auth-demo-icon" aria-hidden="true"><Icon size={18} /></span>
              <span className="auth-demo-copy">
                <strong>{account.title}</strong>
                <small>{account.email}</small>
              </span>
              <span className="auth-demo-arrow">{loadingRole === account.role ? "Signing in" : <ArrowRight size={16} />}</span>
            </button>
          )
        })}
      </div>
      <p className="auth-demo-pass"><Shield size={13} /> Temporary password: {DEMO_ACCOUNT_PASSWORD}</p>
      {error ? <div className="auth-demo-error">{error}</div> : null}
    </section>
  )
}