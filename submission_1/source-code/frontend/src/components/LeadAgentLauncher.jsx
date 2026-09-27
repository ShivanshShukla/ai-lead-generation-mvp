import axios from "axios";
import { useEffect, useMemo, useRef, useState } from "react";
import Button from "./ui/Button";
import Card from "./ui/Card";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const maxResultOptions = [25, 50, 100, 200];
const queryOptions = [1, 2, 3];

function normalizeList(value) {
  return String(value || "")
    .split(/[,/;|\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildPreviewQueries(campaign, maxQueries = 5) {
  const industry = campaign?.target_industry || campaign?.industry || "startup";
  const location = campaign?.target_location || campaign?.location || "India";
  const role = campaign?.target_role || "Founder";
  const sectors = normalizeList(industry).slice(0, 3);
  const cities = normalizeList(location).slice(0, 3);
  const safeSectors = sectors.length ? sectors : [industry];
  const safeCities = cities.length ? cities : [location];
  const queries = [];

  safeCities.forEach((city) => {
    safeSectors.forEach((sector) => {
      queries.push(`"${city}" "${sector}" "startup" "contact"`);
      queries.push(`"${city}" "${sector}" "${role}" "email"`);
    });
  });

  return queries.slice(0, maxQueries);
}

function LeadAgentLauncher({ campaign, onLeadsFound }) {
  const [maxResults, setMaxResults] = useState(100);
  const [queriesPerDay, setQueriesPerDay] = useState(1);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);
  const [status, setStatus] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const pollIntervalRef = useRef(null);
  const hasRefreshedForRunRef = useRef(false);

  const targetIndustry = campaign?.target_industry || campaign?.industry || "N/A";
  const targetLocation = campaign?.target_location || campaign?.location || "N/A";
  const estimatedQueries = queriesPerDay;
  const estimatedLeads = maxResults * queriesPerDay;
  const estimatedApifyCost = ((maxResults * queriesPerDay) * 0.004).toFixed(2);
  const previewQueries = useMemo(
    () => buildPreviewQueries(campaign, estimatedQueries),
    [campaign, estimatedQueries]
  );
  const displayedQueries = success?.search_queries?.length ? success.search_queries : previewQueries;

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  const pollStatus = async (currentBaseline = baseline) => {
    if (!campaign?.id) {
      return;
    }

    try {
      const response = await axios.get(`${API_BASE_URL}/lead-agent/status/${campaign.id}`);
      const nextStatus = response.data;
      setStatus(nextStatus);

      const leadsIncreased = currentBaseline && nextStatus.total_leads > currentBaseline.total_leads;
      const importedIncreased = currentBaseline && nextStatus.imported_contacts > currentBaseline.imported_contacts;
      const discoveredIncreased = currentBaseline && nextStatus.discovered_contacts > currentBaseline.discovered_contacts;

      if (!hasRefreshedForRunRef.current && (leadsIncreased || importedIncreased || discoveredIncreased)) {
        hasRefreshedForRunRef.current = true;
        onLeadsFound?.(nextStatus);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const startPolling = (nextBaseline) => {
    stopPolling();
    pollStatus(nextBaseline);
    pollIntervalRef.current = setInterval(() => pollStatus(nextBaseline), 10000);
  };

  useEffect(() => {
    stopPolling();
    setSuccess(null);
    setError("");
    setStatus(null);
    setBaseline(null);
    hasRefreshedForRunRef.current = false;

    if (campaign?.id) {
      pollStatus(null);
    }

    return () => stopPolling();
  }, [campaign?.id]);

  const handleStart = async () => {
    if (!campaign?.id) {
      setError("Select a campaign before starting Lead Agent.");
      return;
    }

    setIsStarting(true);
    setError("");
    setSuccess(null);
    hasRefreshedForRunRef.current = false;

    try {
      const statusResponse = await axios.get(`${API_BASE_URL}/lead-agent/status/${campaign.id}`);
      const nextBaseline = statusResponse.data;
      setBaseline(nextBaseline);
      setStatus(nextBaseline);

      const response = await axios.post(`${API_BASE_URL}/lead-agent/start`, {
        campaign_id: campaign.id,
        max_results: maxResults,
        target_leads: maxResults,
        queries_per_day: queriesPerDay,
      });

      setSuccess(response.data);
      startPolling(nextBaseline);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || "Lead Agent could not be started. Check n8n webhook configuration.");
      console.error(err);
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight text-ink">Lead Agent</h2>
          <p className="mt-1 text-sm text-muted">
            Trigger the n8n workflow for this campaign and watch for new leads.
          </p>
          <div className="mt-3 grid gap-2 text-xs text-ink-2 sm:grid-cols-2">
            <p className="rounded-lg border line-1 surface-sunk p-3">
              <span className="block font-semibold text-ink">Industry</span>
              {targetIndustry}
            </p>
            <p className="rounded-lg border line-1 surface-sunk p-3">
              <span className="block font-semibold text-ink">Location</span>
              {targetLocation}
            </p>
          </div>
        </div>

        <div className="grid w-full gap-3 sm:grid-cols-2 lg:max-w-md">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-ink-2">Max results</span>
            <select
              value={maxResults}
              onChange={(event) => setMaxResults(Number(event.target.value))}
              className="field"
            >
              {maxResultOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium text-ink-2">Queries per day</span>
            <select
              value={queriesPerDay}
              onChange={(event) => setQueriesPerDay(Number(event.target.value))}
              className="field"
            >
              {queryOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-info-soft bg-info-soft p-4">
          <p className="text-xs text-info">Estimated leads</p>
          <p className="mt-1 text-2xl font-semibold text-info">Up to {estimatedLeads}</p>
        </div>
        <div className="rounded-xl border border-violet-soft bg-violet-soft p-4">
          <p className="text-xs text-violet">Search queries</p>
          <p className="mt-1 text-2xl font-semibold text-violet">{estimatedQueries}</p>
        </div>
        <div className="rounded-xl border border-success-soft bg-success-soft p-4">
          <p className="text-xs text-success">Estimated cost</p>
          <p className="mt-1 text-2xl font-semibold text-success">
            ~${estimatedApifyCost} Apify cost
          </p>
          <p className="mt-1 text-xs text-success">
            Charged to your Apify account ($0.004 per lead)
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Button
          type="button"
          className="w-full sm:w-auto"
          disabled={isStarting || !campaign?.id}
          onClick={handleStart}
        >
          {isStarting ? "Starting Lead Agent..." : "Find Leads Now"}
        </Button>

        {status && (
          <p className="text-sm text-muted">
            Current leads: <span className="font-semibold text-ink">{status.total_leads}</span>
          </p>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
          {error}
        </p>
      )}

      {success && (
        <div className="mt-4 rounded-xl border border-success-soft bg-success-soft p-4">
          <p className="font-semibold text-success">Lead Agent started successfully.</p>
          <p className="mt-1 text-sm text-success">Leads will appear in 3-5 minutes.</p>
          {success.ai_generated !== undefined && (
            <p className="mt-1 text-xs text-success">
              {success.ai_generated ? "Queries generated with Gemini." : "Queries generated from custom sectors."}
            </p>
          )}

          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-success">Search queries</p>
            <div className="mt-2 grid gap-2 lg:grid-cols-2">
              {displayedQueries.map((query) => (
                <p key={query} className="break-words rounded-lg border border-success-soft surface-2 p-3 text-sm text-ink-2">
                  {query}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      {status && success && (
        <div className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          <div className="rounded-lg border line-1 surface-sunk p-3">
            <p className="text-xs text-muted">Discovered contacts</p>
            <p className="mt-1 font-semibold text-ink">{status.discovered_contacts}</p>
          </div>
          <div className="rounded-lg border line-1 surface-sunk p-3">
            <p className="text-xs text-muted">Imported contacts</p>
            <p className="mt-1 font-semibold text-ink">{status.imported_contacts}</p>
          </div>
          <div className="rounded-lg border line-1 surface-sunk p-3">
            <p className="text-xs text-muted">Leads with email</p>
            <p className="mt-1 font-semibold text-ink">{status.leads_with_email}</p>
          </div>
        </div>
      )}
    </Card>
  );
}

export default LeadAgentLauncher;
