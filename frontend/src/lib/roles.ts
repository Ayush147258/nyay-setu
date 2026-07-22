export const appRoles = ["lawyer", "judge", "citizen"] as const

export type AppRole = (typeof appRoles)[number]

export const roleMeta: Record<AppRole, { label: string; shortLabel: string }> = {
  lawyer: { label: "Lawyer", shortLabel: "Counsel" },
  judge: { label: "Judge", shortLabel: "Bench" },
  citizen: { label: "Citizen", shortLabel: "Case owner" },
}

export function normalizeRole(value?: string | null): AppRole {
  return appRoles.includes(value as AppRole) ? (value as AppRole) : "citizen"
}
