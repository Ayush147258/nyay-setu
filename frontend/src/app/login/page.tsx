import { Suspense } from "react"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import LoginForm from "@/components/auth/LoginForm"
import AuthSkeleton from "@/components/auth/AuthSkeleton"

type LoginPageProps = {
  searchParams?: Promise<{ callbackUrl?: string }>
}

function safeCallbackUrl(value?: string) {
  if (value && value.startsWith("/") && !value.startsWith("//")) return value
  return "/choose-role"
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const session = await auth()
  const params = await searchParams
  if (session?.user) redirect(safeCallbackUrl(params?.callbackUrl))

  return (
    <main className="auth-full-page">
      <Suspense fallback={<AuthSkeleton />}>
        <LoginForm mode="login" />
      </Suspense>
    </main>
  )
}

