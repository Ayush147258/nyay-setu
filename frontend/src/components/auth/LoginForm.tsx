"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { ArrowLeft, BadgeCheck, Bot, Database, FileCheck2, Gavel, LockKeyhole, Sparkles } from "lucide-react"
import GoogleButton from "@/components/auth/GoogleButton"
import DemoAccountButtons from "@/components/auth/DemoAccountButtons"

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
    <div className="auth-shell">
      <section className="auth-showcase" aria-label="NyaySetu product preview">
        <Link href="/" className="auth-back"><ArrowLeft size={16} /> Back to landing</Link>
        <div className="auth-brand-lockup">
          <span><Gavel size={20} /></span>
          <strong>NyaySetu</strong>
        </div>
        <div className="auth-showcase-copy">
          <p className="auth-kicker"><Sparkles size={15} /> Track C demo workspace</p>
          <h2>One legal record. Three professional-grade views.</h2>
          <p>
            Upload PDFs, run extraction and synthesis, then ask role-aware questions from the same source-backed case record.
          </p>
        </div>
        <div className="auth-flow-preview">
          <div className="auth-preview-head">
            <span>Live document pipeline</span>
            <strong>Backend ready</strong>
          </div>
          <div className="auth-step-grid">
            <div><Database size={18} /><span>Store</span><strong>PDF preserved</strong></div>
            <div><Bot size={18} /><span>Extract</span><strong>Source spans</strong></div>
            <div><BadgeCheck size={18} /><span>Review</span><strong>Integrity check</strong></div>
            <div><FileCheck2 size={18} /><span>Answer</span><strong>Role output</strong></div>
          </div>
          <div className="auth-record-card">
            <small>Ask the record</small>
            <strong>What weak point will the other side attack?</strong>
            <p>Answer returns with source cards, caveats, and next actions.</p>
          </div>
        </div>
        <div className="auth-metrics" aria-label="NyaySetu demo metrics">
          <div><strong>3</strong><span>role tracks</span></div>
          <div><strong>5</strong><span>pipeline agents</span></div>
          <div><strong>PDF</strong><span>RAG ready</span></div>
        </div>
      </section>

      <section className="auth-full-card" aria-label={isSignup ? "Create account" : "Sign in"}>
        <div className="auth-card-topline">
          <span><LockKeyhole size={15} /> Secure access</span>
          <small>Hackathon demo enabled</small>
        </div>

        <h1>{isSignup ? "Create your account" : "Sign in"}</h1>
        <p className="auth-card-sub">
          {isSignup ? "Create a secure workspace for multilingual legal intake." : "Use Google or open a temporary demo account with full role workspace access."}
        </p>

        {errorMessage ? <div className="auth-error">{errorMessage}</div> : null}

        <GoogleButton label="Continue with Google" />

        {!isSignup ? <DemoAccountButtons /> : null}

        <p className="auth-switch-line">
          {isSignup ? "Already have an account?" : "Need a real account?"} {" "}
          <Link href={isSignup ? "/login" : "/signup"}>{isSignup ? "Sign in" : "Create account"}</Link>
        </p>
        <p className="auth-secure">NextAuth session. Tenant-scoped backend access. Privacy first.</p>
      </section>
    </div>
  )
}
