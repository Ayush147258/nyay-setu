export type DemoRole = "lawyer" | "judge" | "citizen"

export const DEMO_ACCOUNT_PASSWORD = "password123"

export const DEMO_ACCOUNTS: Array<{
  role: DemoRole
  title: string
  email: string
  name: string
  tenantId: string
  route: string
  accent: string
}> = [
  {
    role: "lawyer",
    title: "Lawyer",
    email: "lawyer@nyaysetu.demo",
    name: "NyaySetu Demo Lawyer",
    tenantId: "demo-lawyer",
    route: "/lawyer",
    accent: "#f0c36a",
  },
  {
    role: "judge",
    title: "Judge",
    email: "judge@nyaysetu.demo",
    name: "NyaySetu Demo Judge",
    tenantId: "demo-judge",
    route: "/judge",
    accent: "#9fc4f6",
  },
  {
    role: "citizen",
    title: "Citizen",
    email: "citizen@nyaysetu.demo",
    name: "NyaySetu Demo Citizen",
    tenantId: "demo-citizen",
    route: "/citizen",
    accent: "#0f8f86",
  },
]

export function demoAccountForEmail(email: string) {
  const normalized = email.trim().toLowerCase()
  return DEMO_ACCOUNTS.find((account) => account.email === normalized) ?? null
}

export function demoAccountForRole(role: DemoRole) {
  return DEMO_ACCOUNTS.find((account) => account.role === role) ?? DEMO_ACCOUNTS[2]
}

export function isDemoEmail(email?: string | null) {
  return Boolean(email?.toLowerCase().endsWith("@nyaysetu.demo"))
}