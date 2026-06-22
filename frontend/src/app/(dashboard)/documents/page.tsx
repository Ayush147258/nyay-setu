import FileUpload from "@/components/dashboard/FileUpload"

export default function DocumentsPage() {
  return (
    <div className="dash-grid">
      <FileUpload />
      <div className="dash-card">
        <div className="ch">
          <div>
            <div className="ct">Uploaded Documents</div>
            <div className="cs">Select a case on the dashboard before uploading new evidence.</div>
          </div>
        </div>
        <div className="empty-state">Document listing will appear here after files are uploaded to Supabase.</div>
      </div>
    </div>
  )
}
