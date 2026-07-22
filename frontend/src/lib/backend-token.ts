import "server-only"

type BackendTokenInput = {
  userId: string
  email?: string | null
  tenantId?: string
  expiresInSeconds?: number
}

function base64Url(value: string | Uint8Array) {
  const bytes = typeof value === "string" ? Buffer.from(value, "utf8") : Buffer.from(value)
  return bytes.toString("base64url")
}

export async function createBackendAccessToken({
  userId,
  email,
  tenantId = "default",
  expiresInSeconds = 300,
}: BackendTokenInput) {
  const secret = process.env.BACKEND_JWT_SECRET
  if (!secret || secret.length < 32) throw new Error("BACKEND_JWT_SECRET is not configured")

  const now = Math.floor(Date.now() / 1000)
  const header = base64Url(JSON.stringify({ alg: "HS256", typ: "JWT" }))
  const payload = base64Url(
    JSON.stringify({
      sub: userId,
      tenant_id: tenantId,
      email: email ?? undefined,
      iss: process.env.BACKEND_JWT_ISSUER ?? "nyaysetu-frontend",
      aud: process.env.BACKEND_JWT_AUDIENCE ?? "nyaysetu-backend",
      iat: now,
      exp: now + expiresInSeconds,
      jti: crypto.randomUUID(),
    }),
  )
  const unsigned = `${header}.${payload}`
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  )
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(unsigned))
  return `${unsigned}.${base64Url(new Uint8Array(signature))}`
}
