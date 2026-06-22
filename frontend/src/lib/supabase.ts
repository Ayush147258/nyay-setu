import { createClient, type SupabaseClient } from "@supabase/supabase-js"

export const STORAGE_BUCKETS = ["documents", "voice-recordings", "petitions"] as const
export type StorageBucket = (typeof STORAGE_BUCKETS)[number]

let cachedSupabase: SupabaseClient | null = null

function requireEnv(name: string) {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is not configured. Add it to .env.local.`)
  return value
}

export function getSupabaseAdmin() {
  if (cachedSupabase) return cachedSupabase
  cachedSupabase = createClient(
    requireEnv("NEXT_PUBLIC_SUPABASE_URL"),
    requireEnv("SUPABASE_SERVICE_ROLE_KEY"),
    {
      auth: { persistSession: false, autoRefreshToken: false },
    },
  )
  return cachedSupabase
}

export function sanitizeFileName(fileName: string) {
  const parts = fileName.split(".")
  const extension = parts.length > 1 ? `.${parts.pop()}` : ""
  const base = parts.join(".") || "upload"
  return `${base.toLowerCase().replace(/[^a-z0-9-_]+/g, "-").replace(/^-|-$/g, "")}${extension.toLowerCase()}`
}

export async function uploadFile(
  bucket: StorageBucket,
  userId: string,
  caseId: string,
  file: File,
): Promise<{ path: string; url: string }> {
  const supabase = getSupabaseAdmin()
  const safeName = sanitizeFileName(file.name)
  const path = `${userId}/${caseId}/${crypto.randomUUID()}-${safeName}`
  const buffer = Buffer.from(await file.arrayBuffer())

  const { error } = await supabase.storage.from(bucket).upload(path, buffer, {
    contentType: file.type || "application/octet-stream",
    upsert: false,
  })

  if (error) {
    throw new Error(`Supabase upload failed: ${error.message}`)
  }

  const url = await getSignedUrl(bucket, path)
  return { path, url }
}

export async function getSignedUrl(bucket: StorageBucket | string, path: string, expiresIn = 3600) {
  const supabase = getSupabaseAdmin()
  const { data, error } = await supabase.storage.from(bucket).createSignedUrl(path, expiresIn)
  if (error || !data?.signedUrl) {
    throw new Error(`Could not create signed URL: ${error?.message ?? "missing signed URL"}`)
  }
  return data.signedUrl
}
