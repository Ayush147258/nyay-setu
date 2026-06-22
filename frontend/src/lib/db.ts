import { neon } from "@neondatabase/serverless"
import { drizzle, type NeonHttpDatabase } from "drizzle-orm/neon-http"
import * as schema from "@/db/schema"

export type NyaySetuDb = NeonHttpDatabase<typeof schema>

let cachedDb: NyaySetuDb | null = null

export function getDatabaseUrl() {
  const databaseUrl = process.env.DATABASE_URL
  if (!databaseUrl) {
    throw new Error("DATABASE_URL is not configured. Add it to .env.local before using database-backed routes.")
  }
  return databaseUrl
}

export function getDb(): NyaySetuDb {
  if (cachedDb) return cachedDb
  const sql = neon(getDatabaseUrl())
  cachedDb = drizzle(sql, { schema })
  return cachedDb
}
