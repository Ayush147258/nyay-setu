"use client"

import { useState, useRef, useCallback } from "react"
import Link from "next/link"
import {
  Scale,
  Upload,
  FileText,
  Image as ImageIcon,
  File,
  X,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Shield,
  Clock,
} from "lucide-react"

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/jpeg",
  "image/png",
  "image/webp",
  "audio/mpeg",
  "video/mp4",
]

const ACCEPTED_EXTENSIONS = ".pdf,.docx,.jpg,.jpeg,.png,.webp,.mp3,.mp4"

function getFileIcon(type: string) {
  if (type.startsWith("image/")) return ImageIcon
  if (type === "application/pdf") return FileText
  return File
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<"idle" | "success" | "error">("idle")
  const [errorMsg, setErrorMsg] = useState("")

  const handleFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return
    const valid: File[] = []
    for (let i = 0; i < incoming.length; i++) {
      const f = incoming[i]
      if (f.size > 50 * 1024 * 1024) continue // 50MB limit
      valid.push(f)
    }
    setFiles((prev) => [...prev, ...valid].slice(0, 10)) // max 10 files
    setUploadStatus("idle")
    setErrorMsg("")
  }, [])

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
    setUploadStatus("idle")
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
  }, [])

  async function handleUpload() {
    if (files.length === 0) return
    setUploading(true)
    setUploadStatus("idle")
    setErrorMsg("")

    try {
      // Upload each file
      for (const file of files) {
        const formData = new FormData()
        formData.append("file", file)
        formData.append("docType", "evidence")

        const res = await fetch("/api/upload", { method: "POST", body: formData })
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(data.error || `Failed to upload ${file.name}`)
        }
      }
      setUploadStatus("success")
    } catch (e) {
      setUploadStatus("error")
      setErrorMsg(e instanceof Error ? e.message : "Upload failed. Please try again.")
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="app-shell" style={{ minHeight: "100vh" }}>
      <div style={{ maxWidth: 680, margin: "0 auto", padding: "32px 20px 60px" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 40 }}>
          <Link
            href="/"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              color: "var(--muted)",
              fontSize: 14,
              fontWeight: 500,
              transition: "color 0.2s ease",
            }}
          >
            <ArrowLeft size={16} />
            Back
          </Link>
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
            <div style={{
              width: 34,
              height: 34,
              borderRadius: 8,
              background: "var(--ink)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#fff",
            }}>
              <Scale size={16} />
            </div>
            <span style={{ fontWeight: 600, color: "var(--ink)", fontSize: 17 }}>NyaySetu</span>
          </Link>
        </div>

        {/* Title */}
        <div style={{ textAlign: "center", marginBottom: 40 }} className="fade-up">
          <div style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            marginBottom: 16,
            padding: "6px 14px",
            borderRadius: 100,
            background: "var(--gold-muted)",
            border: "0.5px solid #d4b96a",
            color: "#7a5c00",
            fontSize: 12,
            fontWeight: 500,
          }}>
            <Sparkles size={13} />
            AI-powered document analysis
          </div>
          <h1 style={{
            margin: "0 0 10px",
            fontFamily: "var(--font-playfair), Georgia, serif",
            fontSize: 36,
            fontWeight: 600,
            color: "var(--ink)",
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
          }}>
            Upload Your Documents
          </h1>
          <p style={{ margin: 0, color: "var(--muted)", fontSize: 15, lineHeight: 1.6 }}>
            Upload FIRs, legal notices, court orders, or evidence. Our AI will analyze and extract key legal information.
          </p>
        </div>

        {/* Upload Zone */}
        <div className="fade-up" style={{ animationDelay: "0.05s" }}>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            disabled={uploading}
            style={{
              width: "100%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
              padding: "48px 32px",
              borderRadius: 18,
              border: dragActive
                ? "2px solid var(--gold)"
                : "2px dashed var(--border)",
              background: dragActive
                ? "rgba(184, 134, 11, 0.04)"
                : "rgba(255, 255, 255, 0.6)",
              cursor: uploading ? "not-allowed" : "pointer",
              transition: "all 0.25s ease",
              backdropFilter: "blur(12px)",
              boxShadow: dragActive
                ? "0 0 0 4px rgba(184, 134, 11, 0.08)"
                : "0 8px 32px rgba(26, 26, 46, 0.04)",
            }}
          >
            <div style={{
              width: 64,
              height: 64,
              borderRadius: 16,
              background: dragActive
                ? "linear-gradient(135deg, var(--gold-muted), #fef3c7)"
                : "linear-gradient(135deg, #f0eeff, #e8e4f9)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "all 0.25s ease",
            }}>
              <Upload size={28} style={{ color: dragActive ? "var(--gold)" : "#7c3aed" }} />
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontWeight: 600, fontSize: 15, color: "var(--ink)", marginBottom: 4 }}>
                {dragActive ? "Drop files here" : "Drop files here or click to browse"}
              </div>
              <div style={{ color: "var(--subtle)", fontSize: 13 }}>
                PDF, DOCX, JPG, PNG, MP3, MP4 · max 50MB per file
              </div>
            </div>
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            multiple
            style={{ display: "none" }}
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>

        {/* File List */}
        {files.length > 0 && (
          <div style={{ marginTop: 20 }} className="slide-in">
            <div style={{
              borderRadius: 16,
              border: "0.5px solid var(--border)",
              background: "rgba(255, 255, 255, 0.76)",
              backdropFilter: "blur(16px)",
              overflow: "hidden",
            }}>
              <div style={{
                padding: "12px 18px",
                borderBottom: "0.5px solid var(--border2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
                  {files.length} file{files.length > 1 ? "s" : ""} selected
                </span>
                <button
                  onClick={() => { setFiles([]); setUploadStatus("idle") }}
                  style={{
                    fontSize: 12,
                    color: "var(--subtle)",
                    cursor: "pointer",
                    background: "none",
                    border: "none",
                    fontWeight: 500,
                  }}
                >
                  Clear all
                </button>
              </div>
              {files.map((file, idx) => {
                const Icon = getFileIcon(file.type)
                return (
                  <div
                    key={`${file.name}-${idx}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 18px",
                      borderBottom: idx < files.length - 1 ? "0.5px solid var(--border2)" : "none",
                    }}
                  >
                    <div style={{
                      width: 38,
                      height: 38,
                      borderRadius: 10,
                      background: file.type.startsWith("image/") ? "#ecfdf5" : file.type === "application/pdf" ? "#fef2f2" : "#eff6ff",
                      border: "0.5px solid",
                      borderColor: file.type.startsWith("image/") ? "#86efac" : file.type === "application/pdf" ? "#fca5a5" : "#93c5fd",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}>
                      <Icon size={18} style={{
                        color: file.type.startsWith("image/") ? "#059669" : file.type === "application/pdf" ? "#dc2626" : "#2563eb"
                      }} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13,
                        fontWeight: 500,
                        color: "var(--ink)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}>{file.name}</div>
                      <div style={{ fontSize: 11, color: "var(--subtle)" }}>{formatSize(file.size)}</div>
                    </div>
                    <button
                      onClick={() => removeFile(idx)}
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: 8,
                        border: "0.5px solid var(--border)",
                        background: "transparent",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        cursor: "pointer",
                        color: "var(--subtle)",
                        transition: "all 0.15s ease",
                        flexShrink: 0,
                      }}
                    >
                      <X size={14} />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Status messages */}
        {uploadStatus === "success" && (
          <div className="slide-in" style={{
            marginTop: 16,
            padding: "14px 18px",
            borderRadius: 14,
            background: "linear-gradient(135deg, #ecfdf5, #d1fae5)",
            border: "1px solid #86efac",
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: 14,
            fontWeight: 500,
            color: "#166534",
          }}>
            <CheckCircle2 size={18} />
            All files uploaded successfully! Our AI agents will analyze your documents.
          </div>
        )}

        {uploadStatus === "error" && (
          <div className="slide-in" style={{
            marginTop: 16,
            padding: "14px 18px",
            borderRadius: 14,
            background: "linear-gradient(135deg, #fef2f2, #fee2e2)",
            border: "1px solid #fecaca",
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: 14,
            fontWeight: 500,
            color: "#991b1b",
          }}>
            <AlertTriangle size={18} />
            {errorMsg}
          </div>
        )}

        {/* Upload Button */}
        {files.length > 0 && uploadStatus !== "success" && (
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="fade-up"
            style={{
              width: "100%",
              marginTop: 20,
              padding: "16px 24px",
              borderRadius: 14,
              border: "none",
              background: "var(--ink)",
              color: "#fff",
              fontSize: 15,
              fontWeight: 600,
              cursor: uploading ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              transition: "all 0.2s ease",
              opacity: uploading ? 0.7 : 1,
            }}
          >
            {uploading ? (
              <>
                <span style={{
                  width: 16,
                  height: 16,
                  border: "2px solid rgba(255,255,255,0.3)",
                  borderTopColor: "#fff",
                  borderRadius: "50%",
                  animation: "spin 0.6s linear infinite",
                }} />
                Uploading...
              </>
            ) : (
              <>
                <Upload size={18} />
                Upload & Analyze Documents
              </>
            )}
          </button>
        )}

        {/* Continue after success */}
        {uploadStatus === "success" && (
          <div style={{ display: "flex", gap: 12, marginTop: 20 }}>
            <button
              onClick={() => { setFiles([]); setUploadStatus("idle") }}
              style={{
                flex: 1,
                padding: "14px 20px",
                borderRadius: 12,
                border: "0.5px solid var(--border)",
                background: "transparent",
                color: "var(--ink)",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Upload More
            </button>
            <Link
              href="/analyze"
              style={{
                flex: 1,
                padding: "14px 20px",
                borderRadius: 12,
                border: "none",
                background: "var(--ink)",
                color: "#fff",
                fontSize: 14,
                fontWeight: 600,
                textAlign: "center",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
              }}
            >
              Start Analysis →
            </Link>
          </div>
        )}

        {/* Trust badges */}
        <div style={{
          display: "flex",
          justifyContent: "center",
          gap: 24,
          marginTop: 40,
          flexWrap: "wrap",
        }} className="fade-up" >
          {[
            { icon: Shield, text: "End-to-end encrypted" },
            { icon: Clock, text: "Analyzed in seconds" },
            { icon: Sparkles, text: "AI-powered extraction" },
          ].map((item) => (
            <div key={item.text} style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              color: "var(--subtle)",
              fontWeight: 500,
            }}>
              <item.icon size={14} style={{ color: "var(--gold)" }} />
              {item.text}
            </div>
          ))}
        </div>

      </div>
    </div>
  )
}
