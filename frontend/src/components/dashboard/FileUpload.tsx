"use client"

import { useRef, useState } from "react"
import { IconCloudUpload } from "@tabler/icons-react"

interface FileUploadProps {
  caseId?: string
}

export default function FileUpload({ caseId }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [status, setStatus] = useState<string>("")
  const [uploading, setUploading] = useState(false)

  async function uploadSelected(file: File | undefined) {
    if (!file) return
    if (!caseId) {
      setStatus("Create or select a case before uploading documents.")
      return
    }
    setUploading(true)
    setStatus("Uploading...")
    try {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("caseId", caseId)
      formData.append("docType", "evidence")
      const response = await fetch("/api/upload", { method: "POST", body: formData })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error ?? "Upload failed")
      setStatus(`${file.name} uploaded successfully.`)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Upload failed")
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="dash-card">
      <div className="ch">
        <div>
          <div className="ct">File Upload</div>
          <div className="cs">PDF, DOCX, JPG, PNG, MP3, MP4 · max 50MB</div>
        </div>
      </div>
      <div className="cb">
        <button
          type="button"
          className="upload-zone w-full"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault()
            uploadSelected(event.dataTransfer.files[0])
          }}
        >
          <IconCloudUpload size={30} />
          <strong>{uploading ? "Uploading..." : "Drop files here or click to upload"}</strong>
          <span>Stored privately in Supabase and attached to the selected case.</span>
        </button>
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          accept=".pdf,.docx,.jpg,.jpeg,.png,.mp3,.mp4,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/jpeg,image/png,audio/mpeg,video/mp4"
          onChange={(event) => uploadSelected(event.target.files?.[0])}
        />
        {status ? <p className="mt-3 text-xs text-[var(--color-text-secondary)]">{status}</p> : null}
      </div>
    </div>
  )
}
