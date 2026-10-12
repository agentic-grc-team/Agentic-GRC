import { useRef, useState } from "react";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");
const EVIDENCE_URL = `${apiBaseUrl}/evidence/`;
const ALLOWED_EXTENSIONS = [".pdf", ".txt", ".docx", ".csv", ".xlsx"];
const MAX_FILE_SIZE = 10 * 1024 * 1024;

function validateFile(file) {
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `Format not allowed. Supported: ${ALLOWED_EXTENSIONS.join(", ")}.`;
  }
  if (file.size > MAX_FILE_SIZE) {
    return "File exceeds 10MB limit.";
  }
  return "";
}

function describeError(status, detail) {
  if (status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  if (status === 403) {
    return "You need active membership in this organization to upload evidence.";
  }
  if (typeof detail === "string") {
    return detail;
  }
  return `Upload failed (${status}).`;
}

export default function EvidenceUpload({ organizationId, accessToken }) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState(null);

  const isUploading = status === "uploading";

  async function uploadFile(file) {
    const validationError = validateFile(file);
    if (validationError) {
      setStatus("error");
      setMessage(validationError);
      setResult(null);
      return;
    }

    const formData = new FormData();
    formData.append("organization_id", organizationId);
    formData.append("file", file);

    setStatus("uploading");
    setMessage(`Uploading ${file.name}...`);
    setResult(null);

    try {
      const response = await fetch(EVIDENCE_URL, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
        credentials: "omit",
      });
      const body = await response.json().catch(() => ({}));

      if (!response.ok) {
        setStatus("error");
        setMessage(describeError(response.status, body?.detail));
        return;
      }

      setStatus("success");
      setMessage(body.info || "File uploaded and parsed successfully.");
      setResult(body);
    } catch {
      setStatus("error");
      setMessage("Could not reach the API. Check that the backend is running.");
    }
  }

  function handleFiles(files) {
    const file = files?.[0];
    if (file && !isUploading) {
      void uploadFile(file);
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  function handleDragOver(event) {
    event.preventDefault();
    setIsDragging(true);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <div className="form-card evidence-upload">
      <div className="form-card-heading">
        <span className="step-indicator">EV</span>
        <div>
          <h2>Upload evidence</h2>
          <p className="muted-copy">PDF, DOCX, TXT, CSV or XLSX, up to 10MB.</p>
        </div>
      </div>

      <div
        className={`evidence-dropzone${isDragging ? " is-dragging" : ""}${isUploading ? " is-busy" : ""}`}
        role="button"
        tabIndex={0}
        aria-disabled={isUploading}
        onClick={() => !isUploading && inputRef.current?.click()}
        onKeyDown={handleKeyDown}
        onDragOver={handleDragOver}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <strong>{isDragging ? "Drop the file to upload" : "Drag and drop a file here"}</strong>
        <span>or click to browse</span>
        <input
          ref={inputRef}
          type="file"
          hidden
          accept={ALLOWED_EXTENSIONS.join(",")}
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {message && (
        <p
          className={status === "error" ? "inline-error" : "muted-copy"}
          role={status === "error" ? "alert" : "status"}
        >
          {message}
        </p>
      )}

      {status === "success" && result?.extracted_content_preview && (
        <div className="evidence-preview">
          <span className="muted-copy">{result.original_filename}</span>
          <pre>{result.extracted_content_preview}</pre>
        </div>
      )}
    </div>
  );
}
