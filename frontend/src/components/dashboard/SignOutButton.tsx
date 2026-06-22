"use client"

import { signOut } from "next-auth/react"

export default function SignOutButton() {
  return (
    <button type="button" className="ni w-full" onClick={() => signOut({ callbackUrl: "/login" })}>
      Sign Out
    </button>
  )
}
