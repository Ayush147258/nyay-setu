import { relations, sql, eq } from "drizzle-orm"
import {
  integer,
  jsonb,
  pgEnum,
  pgTable,
  text,
  timestamp,
  uuid,
  boolean,
  varchar
} from "drizzle-orm/pg-core"

import { getDb } from "@/lib/db"

export const documentTypeEnum = pgEnum("document_type", [
  "evidence",
  "id_proof",
  "fir_copy",
  "medical_report",
  "petition",
  "other",
])

export const users = pgTable("users", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  email: varchar("email", { length: 255 }).notNull().unique(),
  name: varchar("name", { length: 255 }),
  avatarUrl: varchar("avatar_url", { length: 512 }),
  googleId: varchar("google_id", { length: 255 }).unique(),
  role: varchar("role", { length: 50 }).default("citizen"),
  preferredLang: varchar("preferred_lang", { length: 10 }).default("hi"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
})

export const cases = pgTable("cases", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  userId: uuid("user_id").references(() => users.id, { onDelete: "cascade" }),
  caseType: varchar("case_type", { length: 100 }).notNull().default("other"),
  rawInput: text("raw_input"),
  detectedLanguage: varchar("detected_language", { length: 10 }).default("hi"),
  status: varchar("status", { length: 50 }).default("intake"),
  title: varchar("title", { length: 255 }),
  description: text("description"),
  aiSummary: text("ai_summary"),
  priority: varchar("priority", { length: 50 }).default("medium"),
  district: varchar("district", { length: 100 }),
  state: varchar("state", { length: 100 }),
  debateRound: integer("debate_round").default(0),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
})

export const debateTurns = pgTable("agent_runs", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  caseId: uuid("case_id").notNull().references(() => cases.id, { onDelete: "cascade" }),
  agentName: varchar("agent_name", { length: 100 }).notNull(),
  roundNumber: integer("round_number").default(0),
  inputSummary: text("input_summary"),
  outputSummary: text("output_summary"),
  score: integer("score"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
})

export const petitions = pgTable("petitions", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  caseId: uuid("case_id").notNull().references(() => cases.id, { onDelete: "cascade" }),
  finalDocumentText: text("final_document_text").notNull(),
  pdfUrl: varchar("pdf_url", { length: 512 }),
  filedAt: timestamp("filed_at", { withTimezone: true }).notNull().defaultNow(),
})

export const followUps = pgTable("follow_ups", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  caseId: uuid("case_id").notNull().references(() => cases.id, { onDelete: "cascade" }),
  nextCheckAt: timestamp("next_check_at", { withTimezone: true }).notNull(),
  lastStatus: varchar("last_status", { length: 255 }),
  escalated: boolean("escalated").default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
})

export const documents = pgTable("documents", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  caseId: uuid("case_id").notNull().references(() => cases.id, { onDelete: "cascade" }),
  userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  fileName: text("file_name").notNull(),
  fileType: text("file_type"),
  fileSize: integer("file_size"),
  supabasePath: text("supabase_path").notNull(),
  supabaseUrl: text("supabase_url"),
  docType: documentTypeEnum("doc_type").notNull().default("other"),
  uploadedAt: timestamp("uploaded_at", { withTimezone: true }).notNull().defaultNow(),
})

export const voiceSessions = pgTable("voice_sessions", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  caseId: uuid("case_id").references(() => cases.id, { onDelete: "cascade" }),
  userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  transcript: text("transcript"),
  language: text("language").notNull().default("hi"),
  durationSec: integer("duration_sec"),
  supabasePath: text("supabase_path"),
  sarvamResponse: jsonb("sarvam_response").$type<Record<string, unknown>>(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
})

export const activityLog = pgTable("activity_log", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  caseId: uuid("case_id").references(() => cases.id, { onDelete: "set null" }),
  action: text("action").notNull(),
  metadata: jsonb("metadata").$type<Record<string, unknown>>(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
})

export const usersRelations = relations(users, ({ many }) => ({
  cases: many(cases),
  documents: many(documents),
  voiceSessions: many(voiceSessions),
  debateTurns: many(debateTurns),
  activityLog: many(activityLog),
}))

export const casesRelations = relations(cases, ({ one, many }) => ({
  user: one(users, { fields: [cases.userId], references: [users.id] }),
  documents: many(documents),
  voiceSessions: many(voiceSessions),
  debateTurns: many(debateTurns),
  petitions: many(petitions),
  followUps: many(followUps),
  activityLog: many(activityLog),
}))

export const debateTurnsRelations = relations(debateTurns, ({ one }) => ({
  case: one(cases, { fields: [debateTurns.caseId], references: [cases.id] }),
}))

export const followUpsRelations = relations(followUps, ({ one }) => ({
  case: one(cases, { fields: [followUps.caseId], references: [cases.id] }),
}))

export const petitionsRelations = relations(petitions, ({ one }) => ({
  case: one(cases, { fields: [petitions.caseId], references: [cases.id] }),
}))

export const documentsRelations = relations(documents, ({ one }) => ({
  user: one(users, { fields: [documents.userId], references: [users.id] }),
  case: one(cases, { fields: [documents.caseId], references: [cases.id] }),
}))

export const voiceSessionsRelations = relations(voiceSessions, ({ one }) => ({
  user: one(users, { fields: [voiceSessions.userId], references: [users.id] }),
  case: one(cases, { fields: [voiceSessions.caseId], references: [cases.id] }),
}))

export const activityLogRelations = relations(activityLog, ({ one }) => ({
  user: one(users, { fields: [activityLog.userId], references: [users.id] }),
  case: one(cases, { fields: [activityLog.caseId], references: [cases.id] }),
}))

export type User = typeof users.$inferSelect
export type NewUser = typeof users.$inferInsert
export type LegalCase = typeof cases.$inferSelect
export type NewLegalCase = typeof cases.$inferInsert
export type Document = typeof documents.$inferSelect
export type NewDocument = typeof documents.$inferInsert
export type DebateTurn = typeof debateTurns.$inferSelect
export type Petition = typeof petitions.$inferSelect
export type FollowUp = typeof followUps.$inferSelect
export type VoiceSession = typeof voiceSessions.$inferSelect
export type ActivityLog = typeof activityLog.$inferSelect

export type CaseType = "fir" | "domestic_violence" | "land_dispute" | "consumer" | "cyber_fraud" | "wage_theft" | "crop_insurance" | "flood_relief" | "other"
export type CaseStatus = "intake" | "advocating" | "under_attack" | "mediating" | "petition_ready" | "filed" | "resolved"
export type CasePriority = "low" | "medium" | "high" | "urgent"
export type DocumentType = (typeof documentTypeEnum.enumValues)[number]

export const caseTypeEnum = { enumValues: ["fir", "domestic_violence", "land_dispute", "consumer", "cyber_fraud", "wage_theft", "crop_insurance", "flood_relief", "other"] as const }
export const caseStatusEnum = { enumValues: ["intake", "advocating", "under_attack", "mediating", "petition_ready", "filed", "resolved"] as const }
export const casePriorityEnum = { enumValues: ["low", "medium", "high", "urgent"] as const }

// Query Helpers
export async function getCasesForUser(userId: string) {
  const db = getDb()
  return db.select().from(cases).where(eq(cases.userId, userId)).orderBy(cases.createdAt)
}

export async function getCaseById(caseId: string) {
  const db = getDb()
  const [c] = await db.select().from(cases).where(eq(cases.id, caseId)).limit(1)
  return c || null
}

export async function getDebateTurnsForCase(caseId: string) {
  const db = getDb()
  return db.select().from(debateTurns).where(eq(debateTurns.caseId, caseId)).orderBy(debateTurns.createdAt)
}

// Aliases for backward compatibility
export const agentRuns = debateTurns
export type AgentRun = DebateTurn
