"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { IconScale } from "@tabler/icons-react"
import GoogleButton from "@/components/auth/GoogleButton"

interface LoginFormProps {
  mode: "login" | "signup"
}

export default function LoginForm({ mode }: LoginFormProps) {
  const searchParams = useSearchParams()
  const isSignup = mode === "signup"
  const oauthError = searchParams.get("error")
  const errorMessage = oauthError
    ? "Google sign-in did not complete. The provider may have been cancelled or blocked."
    : ""

  return (
    <div className="auth-full-card">
      <Link href="/" className="auth-logo" aria-label="NyaySetu home">
        <span className="auth-logo-icon"><IconScale size={18} /></span>
        <span>
          <span className="auth-logo-name">NyaySetu</span>
          <span className="auth-logo-sub">India&apos;s Autonomous Legal Rights Navigator</span>
        </span>
      </Link>

      <h1>{isSignup ? "Create your account" : "Welcome back"}</h1>
      <p className="auth-card-sub">
        {isSignup ? "Start a multilingual case intake with a secure judge workspace." : "Sign in to continue to the NyaySetu dashboard."}
      </p>

      {errorMessage ? (
        <div className="mb-4 rounded-[10px] border border-[#f2b8b5] bg-[#fff1f0] p-3 text-sm text-[#a32d2d]">
          {errorMessage}
        </div>
      ) : null}

      <GoogleButton label="Continue with Google" />

      <p className="auth-switch-line">
        {isSignup ? "Already have an account?" : "Need access?"} {" "}
        <Link href={isSignup ? "/login" : "/signup"}>{isSignup ? "Sign in" : "Sign up"}</Link>
      </p>
      <p className="auth-secure">Secured by NextAuth. Privacy first. Made in India.</p>
    </div>
  )
}
