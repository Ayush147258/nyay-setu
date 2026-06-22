import { NextResponse } from "next/server"
import { and, eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { getDb } from "@/lib/db"
import { cases, documents, documentTypeEnum } from "@/db/schema"
import { getSignedUrl, type StorageBucket, uploadFile } from "@/lib/supabase"

const MAX_FILE_SIZE = 50 * 1024 * 1024
const ALLOWED_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/jpeg",
  "image/png",
  "audio/mpeg",
  "audio/mp3",
  "video/mp4",
])

function getSessionUserId(session: { user?: { id?: string } } | null) {
  const userId = session?.user ? (session.user as typeof session.user & { id?: string }).id : undefined
  return userId || null
}

function inferBucket(file: File, docType: string): StorageBucket {
  if (docType === "petition") return "petitions"
  if (file.type.startsWith("audio/") || file.type.startsWith("video/")) return "voice-recordings"
  return "documents"
}

export async function POST(request: Request) {
  try {
    const session = await auth()
    const userId = getSessionUserId(session)
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

    const formData = await request.formData()
    const file = formData.get("file")
    const caseId = String(formData.get("caseId") ?? "")
    const requestedDocType = String(formData.get("docType") ?? "other")

    if (!(file instanceof File)) {
      return NextResponse.json({ error: "Missing file" }, { status: 400 })
    }
    if (!caseId) {
      return NextResponse.json({ error: "Missing caseId" }, { status: 400 })
    }
    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json({ error: "File exceeds 50MB limit" }, { status: 413 })
    }
    if (!ALLOWED_TYPES.has(file.type)) {
      return NextResponse.json({ error: `Unsupported file type: ${file.type || "unknown"}` }, { status: 415 })
    }

    const docType = documentTypeEnum.enumValues.includes(requestedDocType as (typeof documentTypeEnum.enumValues)[number])
      ? (requestedDocType as (typeof documentTypeEnum.enumValues)[number])
      : "other"

    const db = getDb()
    const [ownedCase] = await db
      .select({ id: cases.id })
      .from(cases)
      .where(and(eq(cases.id, caseId), eq(cases.userId, userId)))
      .limit(1)

    if (!ownedCase) {
      return NextResponse.json({ error: "Case not found" }, { status: 404 })
    }

    const bucket = inferBucket(file, docType)
    const uploaded = await uploadFile(bucket, userId, caseId, file)

    const [document] = await db
      .insert(documents)
      .values({
        caseId,
        userId,
        fileName: file.name,
        fileType: file.type,
        fileSize: file.size,
        supabasePath: uploaded.path,
        supabaseUrl: uploaded.url,
        docType,
      })
      .returning()

    return NextResponse.json({ document, bucket }, { status: 201 })
  } catch (error) {
    console.error("[upload:POST]", error)
    return NextResponse.json({ error: "Failed to upload file" }, { status: 500 })
  }
}

export async function GET(request: Request) {
  try {
    const session = await auth()
    const userId = getSessionUserId(session)
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

    const { searchParams } = new URL(request.url)
    const documentId = searchParams.get("documentId")
    if (!documentId) return NextResponse.json({ error: "Missing documentId" }, { status: 400 })

    const db = getDb()
    const [document] = await db
      .select()
      .from(documents)
      .where(and(eq(documents.id, documentId), eq(documents.userId, userId)))
      .limit(1)

    if (!document) return NextResponse.json({ error: "Document not found" }, { status: 404 })

    const bucket: StorageBucket = document.docType === "petition"
      ? "petitions"
      : document.fileType?.startsWith("audio/") || document.fileType?.startsWith("video/")
        ? "voice-recordings"
        : "documents"

    const url = await getSignedUrl(bucket, document.supabasePath)
    return NextResponse.json({ url })
  } catch (error) {
    console.error("[upload:GET]", error)
    return NextResponse.json({ error: "Failed to create download link" }, { status: 500 })
  }
}
