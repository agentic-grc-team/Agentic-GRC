import { useEffect, useRef, useState } from "react";

import { listOrganizations } from "../organizations/api.js";
import { DEMO_ASSESSMENT_ID, downloadReportPdf, getReportPreview } from "./api.js";
import "./ReportWorkspace.css";

const ASSESSMENT_STATUS_LABELS = {
  draft: "Draft",
  in_progress: "In progress",
  awaiting_review: "Awaiting review",
  completed: "Completed",
};

function describeReportError(error) {
  if (error?.status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  if (error?.status === 404) {
    return "No report is available for this organization yet.";
  }
  return error?.message || "Something went wrong. Please try again.";
}

export default function ReportWorkspace({ accessToken }) {
  const [organizations, setOrganizations] = useState([]);
  const [isLoadingOrgs, setIsLoadingOrgs] = useState(true);
  const [selectedOrgId, setSelectedOrgId] = useState(null);
  const [orgsError, setOrgsError] = useState(null);
  const [orgsRetryCounter, setOrgsRetryCounter] = useState(0);

  const [preview, setPreview] = useState(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [retryCounter, setRetryCounter] = useState(0);

  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState(null);
  const [downloadError, setDownloadError] = useState(null);

  const isMountedRef = useRef(true);
  const previewRequestRef = useRef(0);
  const orgsRequestRef = useRef(0);
  const downloadRequestRef = useRef(0);
  const prevTokenRef = useRef(accessToken);
  const prevSelectedOrgIdRef = useRef(selectedOrgId);
  const lastLoadedTokenRef = useRef(accessToken);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      ++downloadRequestRef.current;
    };
  }, []);

  useEffect(() => {
    if (prevSelectedOrgIdRef.current !== selectedOrgId) {
      prevSelectedOrgIdRef.current = selectedOrgId;
      ++downloadRequestRef.current;
      setIsDownloading(false);
      setDownloadStatus(null);
      setDownloadError(null);
    }
  }, [selectedOrgId]);

  useEffect(() => {
    if (prevTokenRef.current !== accessToken) {
      prevTokenRef.current = accessToken;
      setOrganizations([]);
      setSelectedOrgId(null);
      setPreview(null);
      setPreviewError(null);
      setDownloadStatus(null);
      setDownloadError(null);
      setIsDownloading(false);
      ++previewRequestRef.current;
      ++downloadRequestRef.current;
    }

    const requestId = ++orgsRequestRef.current;
    setIsLoadingOrgs(true);
    setOrgsError(null);

    listOrganizations(accessToken)
      .then((orgs) => {
        if (!isMountedRef.current || requestId !== orgsRequestRef.current) return;
        lastLoadedTokenRef.current = accessToken;
        const orgList = Array.isArray(orgs) ? orgs : [];
        setOrganizations(orgList);
        setIsLoadingOrgs(false);
        if (orgList.length > 0) {
          setSelectedOrgId(orgList[0].id);
        } else {
          setSelectedOrgId(null);
        }
      })
      .catch((err) => {
        if (!isMountedRef.current || requestId !== orgsRequestRef.current) return;
        lastLoadedTokenRef.current = accessToken;
        setOrganizations([]);
        setOrgsError(err);
        setIsLoadingOrgs(false);
        setSelectedOrgId(null);
      });
  }, [accessToken, orgsRetryCounter]);

  useEffect(() => {
    if (!selectedOrgId || lastLoadedTokenRef.current !== accessToken) {
      ++previewRequestRef.current;
      setPreview(null);
      setIsLoadingPreview(false);
      setPreviewError(null);
      return;
    }

    const requestId = ++previewRequestRef.current;
    setIsLoadingPreview(true);
    setPreviewError(null);
    setDownloadStatus(null);
    setDownloadError(null);

    getReportPreview(selectedOrgId, DEMO_ASSESSMENT_ID, accessToken)
      .then((data) => {
        if (!isMountedRef.current || requestId !== previewRequestRef.current) return;
        setPreview(data);
        setIsLoadingPreview(false);
      })
      .catch((err) => {
        if (!isMountedRef.current || requestId !== previewRequestRef.current) return;
        setPreview(null);
        setPreviewError(err);
        setIsLoadingPreview(false);
      });
  }, [selectedOrgId, accessToken, retryCounter]);

  async function handleDownload() {
    if (!selectedOrgId || isDownloading) return;

    const orgId = selectedOrgId;
    const token = accessToken;
    const downloadId = ++downloadRequestRef.current;

    setIsDownloading(true);
    setDownloadStatus(null);
    setDownloadError(null);

    try {
      const { blob, filename } = await downloadReportPdf(
        orgId,
        DEMO_ASSESSMENT_ID,
        token
      );

      if (!isMountedRef.current || downloadId !== downloadRequestRef.current) return;

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);

      setDownloadStatus("Report downloaded.");
    } catch (err) {
      if (!isMountedRef.current || downloadId !== downloadRequestRef.current) return;
      setDownloadError(describeReportError(err));
    } finally {
      // No return here: a return inside finally would swallow any error thrown above.
      if (isMountedRef.current && downloadId === downloadRequestRef.current) {
        setIsDownloading(false);
      }
    }
  }

  function handleRetry() {
    setRetryCounter((c) => c + 1);
  }

  const showEmptyState = !isLoadingOrgs && !orgsError && organizations.length === 0;

  return (
    <section className="report-workspace" aria-labelledby="report-heading">
      <p className="eyebrow">ASSESSMENT REPORT</p>
      <h1 id="report-heading">Assessment report</h1>
      <p className="report-intro">
        Preview the reviewed results of an assessment and download the PDF for the client. AI drafts that are not reviewed yet are listed separately and are never shown as final results.
      </p>

      {organizations.length >= 2 && (
        <label className="report-org-select">
          Organization
          <select
            value={selectedOrgId || ""}
            onChange={(e) => setSelectedOrgId(e.target.value)}
          >
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {organizations.length === 1 && (
        <p className="report-org-text">Organization: {organizations[0].name}</p>
      )}

      {showEmptyState && (
        <p className="report-empty">
          You are not a member of any organization yet. Ask your administrator for an invitation.
        </p>
      )}

      {!isLoadingOrgs && orgsError && (
        <div role="alert" className="report-error-message">
          <span>{describeReportError(orgsError)}</span>
          <button
            className="text-button"
            type="button"
            onClick={() => setOrgsRetryCounter((c) => c + 1)}
          >
            Try again
          </button>
        </div>
      )}

      {(isLoadingOrgs || isLoadingPreview) && (
        <p role="status">Loading report preview…</p>
      )}

      {!isLoadingPreview && previewError && (
        <div role="alert" className="report-error-message">
          <span>{describeReportError(previewError)}</span>
          <button className="text-button" type="button" onClick={handleRetry}>
            Try again
          </button>
        </div>
      )}

      {!isLoadingPreview && !previewError && preview && (
        <>
          <div className="report-header">
            <div>
              <div className="report-title-wrap">
                <h2>{preview.assessment.title}</h2>
                {preview.is_demo_data && (
                  <span className="report-badge">Demo data</span>
                )}
              </div>
              <p className="report-meta">
                {`${preview.assessment.framework} · Knowledge base ${preview.assessment.kb_version} · Status: ${
                  ASSESSMENT_STATUS_LABELS[preview.assessment.status] || preview.assessment.status
                }`}
              </p>
            </div>
            <button
              className="primary-button"
              type="button"
              disabled={isDownloading}
              onClick={handleDownload}
            >
              {isDownloading ? "Preparing PDF…" : "Download PDF"}
            </button>
          </div>

          {downloadStatus && (
            <p role="status" className="report-status-message">
              {downloadStatus}
            </p>
          )}

          {downloadError && (
            <p role="alert" className="report-download-error">
              {downloadError}
            </p>
          )}

          {preview.summary?.pending > 0 && (
            <p className="report-notice">
              {preview.summary.pending} control(s) pending expert review. They are listed separately and are not presented as final results.
            </p>
          )}

          <dl className="report-summary">
            <div>
              <dt>Controls in scope</dt>
              <dd>{preview.summary?.controls_in_scope ?? 0}</dd>
            </div>
            <div>
              <dt>Final results</dt>
              <dd>{preview.results?.length ?? 0}</dd>
            </div>
            <div>
              <dt>Final results with evidence pending</dt>
              <dd>{preview.summary?.final_with_evidence_pending ?? 0}</dd>
            </div>
            <div>
              <dt>Pending review</dt>
              <dd>{preview.summary?.pending ?? 0}</dd>
            </div>
            <div>
              <dt>Exclusions</dt>
              <dd>{preview.exclusions?.length ?? 0}</dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd>
                {typeof preview.summary?.coverage_pct === "number"
                  ? `${preview.summary.coverage_pct.toFixed(1)}%`
                  : "0.0%"}
              </dd>
            </div>
          </dl>

          <div className="report-section">
            <h3>Reviewed results</h3>
            {preview.summary?.final_with_evidence_pending > 0 && (
              <p className="report-evidence-note">
                Results marked “Evidence pending” were accepted by an Aligo consultant on the basis of the participant's statement; the supporting evidence has not been validated yet.
              </p>
            )}
            {!preview.results || preview.results.length === 0 ? (
              <p>No reviewed results yet.</p>
            ) : (
              <div className="report-table-wrap">
                <table className="report-table" aria-label="Reviewed results">
                  <thead>
                    <tr>
                      <th scope="col">Control</th>
                      <th scope="col">Name</th>
                      <th scope="col">Status</th>
                      <th scope="col">Reviewed by</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.results.map((result) => {
                      const dateStr = result.reviewed_at
                        ? new Date(result.reviewed_at).toISOString().slice(0, 10)
                        : "";
                      const reviewerText = dateStr
                        ? `${result.reviewed_by} · ${dateStr}`
                        : result.reviewed_by;
                      return (
                        <tr key={result.code}>
                          <td>{result.code}</td>
                          <td>{result.title}</td>
                          <td>
                            <span
                              className={`report-status report-status--${result.control_status}`}
                            >
                              {result.status_label}
                            </span>
                            {result.evidence_pending && (
                              <span className="report-evidence-badge">
                                Evidence pending
                              </span>
                            )}
                          </td>
                          <td>{reviewerText}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="report-section">
            <h3>Pending review</h3>
            {!preview.pending || preview.pending.length === 0 ? (
              <p>No items pending review.</p>
            ) : (
              <div className="report-table-wrap">
                <table className="report-table" aria-label="Pending review">
                  <thead>
                    <tr>
                      <th scope="col">Control</th>
                      <th scope="col">Name</th>
                      <th scope="col">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.pending.map((item) => (
                      <tr key={item.code}>
                        <td>{item.code}</td>
                        <td>{item.title}</td>
                        <td>{item.reason_label}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="report-section">
            <h3>Exclusions (not applicable)</h3>
            {!preview.exclusions || preview.exclusions.length === 0 ? (
              <p>No exclusions.</p>
            ) : (
              <div className="report-table-wrap">
                <table className="report-table" aria-label="Exclusions">
                  <thead>
                    <tr>
                      <th scope="col">Control</th>
                      <th scope="col">Name</th>
                      <th scope="col">Justification</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.exclusions.map((item) => (
                      <tr key={item.code}>
                        <td>{item.code}</td>
                        <td>{item.title}</td>
                        <td>{item.justification}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
