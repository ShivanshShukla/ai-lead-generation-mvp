import { useEffect, useRef, useState } from "react";
import { extractEmailsAsync, getCampaignExtractionStatus, getExtractionJob } from "../api/leads";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Button from "./ui/Button";
import Card from "./ui/Card";

function EmailExtraction({ campaignId, onExtractionComplete }) {
  const [isStarting, setIsStarting] = useState(false);
  const [job, setJob] = useState(null);
  const [campaignStatus, setCampaignStatus] = useState(null);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  const pollIntervalRef = useRef(null);

  const isJobRunning = job?.status === "pending" || job?.status === "running";
  const progress = job?.percentage ?? 0;

  function stopPolling() {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }

  async function refreshCampaignStatus() {
    if (!campaignId) {
      setCampaignStatus(null);
      return;
    }

    try {
      const status = await getCampaignExtractionStatus(campaignId);
      setCampaignStatus(status);

      if (status.running_job_id && !pollIntervalRef.current) {
        setJob(status.running_job);
        startPolling(status.running_job_id);
      }
    } catch (err) {
      console.error(err);
    }
  }

  function handleCompletedJob(nextJob) {
    stopPolling();
    onExtractionComplete?.();
    refreshCampaignStatus();

    if (nextJob.status === "failed") {
      setError(nextJob.error || "Email extraction failed. Please check backend logs.");
      return;
    }

    setSummary(
      `Extraction completed. Found ${nextJob.found ?? 0} emails, skipped ${nextJob.skipped ?? 0}, failed ${nextJob.failed ?? 0}. Processed ${nextJob.processed ?? 0}/${nextJob.total ?? 0} leads.`
    );
  }

  function startPolling(jobId) {
    stopPolling();

    const pollJob = async () => {
      try {
        const nextJob = await getExtractionJob(jobId);
        setJob(nextJob);

        if (nextJob.status === "completed" || nextJob.status === "failed") {
          handleCompletedJob(nextJob);
        }
      } catch (err) {
        stopPolling();
        setError(getFriendlyErrorMessage(err, "Could not load email extraction progress."));
        console.error(err);
      }
    };

    pollJob();
    pollIntervalRef.current = setInterval(pollJob, 3000);
  }

  useEffect(() => {
    stopPolling();
    setJob(null);
    setSummary("");
    setError("");

    if (campaignId) {
      refreshCampaignStatus();
    } else {
      setCampaignStatus(null);
    }

    return () => stopPolling();
  }, [campaignId]);

  const handleExtractCampaignEmails = async () => {
    setSummary("");
    setError("");

    if (!campaignId) {
      setError("Please select a campaign before extracting emails.");
      return;
    }

    setIsStarting(true);

    try {
      const result = await extractEmailsAsync(campaignId, 100);

      if (result.status === "nothing_to_do") {
        setJob(null);
        setSummary("No leads need email extraction. Leads either already have emails or are missing websites.");
        refreshCampaignStatus();
        return;
      }

      setJob(result);
      startPolling(result.job_id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(err.response ? detail || "Email extraction failed. Please try again." : getFriendlyErrorMessage(err));
      console.error(err);
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <Card>
      <div className="mb-4">
        <h2 className="text-xl font-semibold tracking-tight text-ink">Email Extraction</h2>
        <p className="mt-1 text-sm text-muted">
          Find public emails from lead websites for the selected campaign.
        </p>
      </div>

      {campaignStatus && (
        <div className="mb-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div className="rounded-lg border line-1 surface-sunk p-3">
            <p className="text-xs text-muted">Total Leads</p>
            <p className="mt-1 font-semibold text-ink">{campaignStatus.total_leads}</p>
          </div>
          <div className="rounded-lg border border-success-soft bg-success-soft p-3">
            <p className="text-xs text-success">With Email</p>
            <p className="mt-1 font-semibold text-success">{campaignStatus.with_email}</p>
          </div>
          <div className="rounded-lg border border-warn-soft bg-warn-soft p-3">
            <p className="text-xs text-warn">Needs Extraction</p>
            <p className="mt-1 font-semibold text-warn">{campaignStatus.eligible_without_email}</p>
          </div>
          <div className="rounded-lg border border-info-soft bg-info-soft p-3">
            <p className="text-xs text-info">Coverage</p>
            <p className="mt-1 font-semibold text-info">{campaignStatus.coverage_percent}%</p>
          </div>
        </div>
      )}

      {isJobRunning && (
        <div className="mb-4 rounded-lg border border-info-soft bg-info-soft p-3">
          <div className="mb-2 flex items-center justify-between gap-3 text-xs text-info">
            <span>Processing {job.processed ?? 0}/{job.total ?? 0} leads</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full surface-2">
            <div
              className="h-full rounded-full bg-info-solid transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
            <span className="rounded border border-success-soft surface-2 px-2 py-1 text-success">
              Found: {job.found ?? 0}
            </span>
            <span className="rounded border line-1 surface-2 px-2 py-1 text-ink-2">
              Skipped: {job.skipped ?? 0}
            </span>
            <span className="rounded border border-danger-soft surface-2 px-2 py-1 text-danger">
              Failed: {job.failed ?? 0}
            </span>
          </div>
        </div>
      )}

      {summary && (
        <p className="mb-4 rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">
          {summary}
        </p>
      )}

      {error && (
        <p className="mb-4 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
          {error}
        </p>
      )}

      <Button
        type="button"
        className="w-full sm:w-auto"
        disabled={!campaignId || isStarting || isJobRunning}
        onClick={handleExtractCampaignEmails}
      >
        {isStarting
          ? "Starting extraction..."
          : isJobRunning
          ? `Extracting... ${progress}%`
          : "Extract Emails for Campaign"}
      </Button>

      {!campaignId && (
        <p className="mt-3 text-sm text-muted">
          Select a campaign above to enable email extraction.
        </p>
      )}

      {campaignId && (
        <p className="mt-3 text-xs text-muted">
          Runs in the background and checks progress every 3 seconds, so large campaigns avoid Render request timeouts.
        </p>
      )}
    </Card>
  );
}

export default EmailExtraction;
