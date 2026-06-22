"use client"

export default function PetitionPreview({
  petition,
  complete,
  caseId,
}: {
  petition?: string | null
  complete: boolean
  caseId: string
}) {
  async function downloadPdf() {
    const response = await fetch(`/api/petition/${caseId}/pdf`)
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error ?? "Could not generate PDF")
    window.location.href = payload.url
  }

  return (
    <div className="dash-card">
      <div className="ch">
        <div>
          <div className="ct">Legal Petition</div>
          <div className="cs">Draft v1 · {complete ? "Petition hardened" : "Draft evolving..."}</div>
        </div>
      </div>
      <div className="cb">
        <div className="petition-preview">
          {petition || "The petition will evolve here as the agents argue, attack, mediate, and file the final document."}
        </div>
        <div className="mt-3 flex flex-col gap-2">
          {complete ? (
            <button className="tbtn dark justify-center" type="button" onClick={downloadPdf}>⬇ Download PDF</button>
          ) : null}
          <button className="tbtn justify-center" type="button" disabled={!complete}>📧 File via Email</button>
          <button className="tbtn justify-center" type="button" disabled={!complete}>📱 Send via SMS</button>
          <button
            className="tbtn justify-center"
            type="button"
            disabled={!petition}
            onClick={() => petition && navigator.clipboard.writeText(petition)}
          >
            📋 Copy Text
          </button>
        </div>
      </div>
    </div>
  )
}
