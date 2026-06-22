import { Suspense } from "react"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import LoginForm from "@/components/auth/LoginForm"
import AuthSkeleton from "@/components/auth/AuthSkeleton"

export default async function SignupPage() {
  const session = await auth()
  if (session?.user) redirect("/dashboard")

  return (
    <main className="auth-full-page">
      <Suspense fallback={<AuthSkeleton />}>
        <LoginForm mode="signup" />
      </Suspense>
    </main>
  )
}
