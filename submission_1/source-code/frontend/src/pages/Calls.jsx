import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../services/api";
import { formatDateTimeIST } from "../utils/dateUtils";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";

const emptyManualLog = {
  outcome: "asked_details",
  notes: "",
  summary: "",
  next_action: "",
};

function display(value, fallback = "N/A") {
  return value || fallback;
}

function getCallModeLabel(callLog) {
  if (callLog.provider === "manual") {
    return "Manual Call";
  }

  return callLog.call_mode === "actual" ? "Actual Lead Call" : "Test Call";
}

function getCallModeVariant(callLog) {
  if (callLog.provider === "manual") {
    return "neutral";
  }

  return callLog.call_mode === "actual" ? "actual" : "test";
}

function ScriptPreview({ script }) {
  if (!script) {
    return (
      <Card>
        <p className="text-sm text-muted">Generate a call script to preview opener, questions, objection handling, and closing.</p>
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-xl font-semibold tracking-tight text-ink">Call Script Preview</h2>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="rounded-2xl border line-1 surface-sunk p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Opener</p>
          <p className="mt-2 whitespace-pre-line break-words text-sm leading-6 text-ink-2">{script.opener}</p>
        </div>
        <div className="rounded-2xl border line-1 surface-sunk p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Purpose</p>
          <p className="mt-2 whitespace-pre-line break-words text-sm leading-6 text-ink-2">{script.purpose}</p>
        </div>
        <div className="rounded-2xl border line-1 surface-sunk p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Questions</p>
          <p className="mt-2 whitespace-pre-line break-words text-sm leading-6 text-ink-2">{script.questions}</p>
        </div>
        <div className="rounded-2xl border line-1 surface-sunk p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Objection handling</p>
          <p className="mt-2 whitespace-pre-line break-words text-sm leading-6 text-ink-2">{script.objection_handling}</p>
        </div>
        <div className="rounded-2xl border line-1 surface-sunk p-4 lg:col-span-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Closing</p>
          <p className="mt-2 whitespace-pre-line break-words text-sm leading-6 text-ink-2">{script.closing}</p>
        </div>
      </div>
    </Card>
  );
}

function CallLogCard({ callLog, onCreateFollowup, creatingFollowupId }) {
  return (
    <article className="rounded-2xl border line-1 surface-2 p-4 elev-1">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2">
            <Badge variant={getCallModeVariant(callLog)}>{getCallModeLabel(callLog)}</Badge>
            <Badge variant={callLog.status}>{callLog.status}</Badge>
            {callLog.outcome && <Badge variant={callLog.outcome}>{callLog.outcome}</Badge>}
            {callLog.sentiment && <Badge variant={callLog.sentiment}>{callLog.sentiment}</Badge>}
            {callLog.priority && <Badge variant={callLog.priority}>{callLog.priority}</Badge>}
          </div>
          <h3 className="mt-3 break-words text-base font-semibold text-ink">
            {display(callLog.lead_company_name, "Unlinked call")}
          </h3>
          <p className="mt-1 break-words text-sm text-muted">
            {[callLog.lead_name, callLog.lead_contact_role, callLog.campaign_name].filter(Boolean).join(" | ") || "No lead context"}
          </p>
          <p className="mt-1 break-words text-xs text-faint">
            Called: {display(callLog.called_number || callLog.phone_number)} | Duration: {callLog.duration_seconds ?? "-"}s
          </p>
        </div>
        <p className="text-xs text-faint lg:text-right">{formatDateTimeIST(callLog.created_at)}</p>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {callLog.summary && (
          <p className="rounded-xl border line-1 surface-sunk p-3 text-sm leading-6 text-ink-2">{callLog.summary}</p>
        )}
        {callLog.next_action && (
          <p className="rounded-xl border border-info-soft bg-info-soft p-3 text-sm leading-6 text-info">{callLog.next_action}</p>
        )}
      </div>

      {callLog.recording_url && (
        <a href={callLog.recording_url} target="_blank" rel="noreferrer" className="mt-3 block break-all text-sm font-medium text-info">
          Recording
        </a>
      )}

      {callLog.error_message && (
        <p className="mt-3 rounded-xl border border-danger-soft bg-danger-soft p-3 text-sm text-danger">{callLog.error_message}</p>
      )}

      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {["asked_details", "interested", "call_later"].includes(callLog.outcome) && (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={creatingFollowupId === callLog.id}
            onClick={() => onCreateFollowup(callLog)}
          >
            {creatingFollowupId === callLog.id ? "Creating..." : "Create Follow-up Draft"}
          </Button>
        )}
      </div>

      {callLog.transcript && (
        <details className="mt-4 rounded-xl border line-1 surface-sunk">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-ink-2">Transcript</summary>
          <p className="whitespace-pre-line break-words border-t line-1 px-4 py-3 text-sm leading-6 text-ink-2">
            {callLog.transcript}
          </p>
        </details>
      )}
    </article>
  );
}

function Calls() {
  const [searchParams] = useSearchParams();
  const [configStatus, setConfigStatus] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [leads, setLeads] = useState([]);
  const [callLogs, setCallLogs] = useState([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState(searchParams.get("campaign_id") || "");
  const [selectedLeadId, setSelectedLeadId] = useState(searchParams.get("lead_id") || "");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [useTestNumber, setUseTestNumber] = useState(true);
  const [testPhoneNumber, setTestPhoneNumber] = useState("");
  const [script, setScript] = useState(null);
  const [manualLog, setManualLog] = useState(emptyManualLog);
  const [isLoading, setIsLoading] = useState(true);
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);
  const [isStartingCall, setIsStartingCall] = useState(false);
  const [isSavingManualLog, setIsSavingManualLog] = useState(false);
  const [creatingFollowupId, setCreatingFollowupId] = useState(null);
  const [createdFollowupDraft, setCreatedFollowupDraft] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const selectedLead = useMemo(
    () => leads.find((lead) => String(lead.id) === String(selectedLeadId)),
    [leads, selectedLeadId]
  );

  const selectedCampaign = useMemo(
    () => campaigns.find((campaign) => String(campaign.id) === String(selectedCampaignId)),
    [campaigns, selectedCampaignId]
  );

  const callingNumber = useTestNumber
    ? testPhoneNumber || configStatus?.default_test_phone || ""
    : selectedLead?.phone || "";
  const callingLabel = useTestNumber ? "Test number" : "Actual lead number";

  const loadCallLogs = async (leadId = selectedLeadId, campaignId = selectedCampaignId) => {
    const params = {};
    if (leadId) {
      params.lead_id = leadId;
    } else if (campaignId) {
      params.campaign_id = campaignId;
    }
    const res = await api.get("/calls/", { params });
    setCallLogs(Array.isArray(res.data.data) ? res.data.data : []);
  };

  useEffect(() => {
    const loadInitial = async () => {
      setIsLoading(true);
      setErrorMessage("");

      try {
        const [configRes, campaignRes] = await Promise.all([
          api.get("/calls/config/status"),
          api.get("/campaigns/"),
        ]);
        const campaignData = Array.isArray(campaignRes.data.data) ? campaignRes.data.data : [];
        setConfigStatus(configRes.data);
        setCampaigns(campaignData);
      } catch (err) {
        setErrorMessage(getFriendlyErrorMessage(err, "Could not load Calls page. Please try again."));
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };

    loadInitial();
  }, []);

  useEffect(() => {
    const loadLeads = async () => {
      if (!selectedCampaignId) {
        setLeads([]);
        return;
      }

      try {
        const res = await api.get(`/leads/campaign/${selectedCampaignId}`);
        const leadData = Array.isArray(res.data.data) ? res.data.data : [];
        setLeads(leadData);
        if (!selectedLeadId && leadData.length > 0) {
          setSelectedLeadId(String(leadData[0].id));
        }
      } catch (err) {
        setErrorMessage(getFriendlyErrorMessage(err, "Could not load campaign leads. Please try again."));
        console.error(err);
      }
    };

    loadLeads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCampaignId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPhoneNumber(selectedLead?.phone || "");
    }, 0);

    return () => window.clearTimeout(timer);
  }, [selectedLead]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadCallLogs().catch((err) => {
        console.error(err);
      });
    }, 0);

    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeadId, selectedCampaignId]);

  const handleGenerateScript = async () => {
    if (!selectedLeadId) {
      setErrorMessage("Select a lead first.");
      return;
    }

    setIsGeneratingScript(true);
    setStatusMessage("");
    setErrorMessage("");
    setCreatedFollowupDraft(null);

    try {
      const res = await api.post("/calls/generate-script", {
        lead_id: Number(selectedLeadId),
        campaign_id: selectedCampaignId ? Number(selectedCampaignId) : null,
      });
      setScript(res.data);
      setStatusMessage("Call script generated.");
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Call script could not be generated."));
      console.error(err);
    } finally {
      setIsGeneratingScript(false);
    }
  };

  const handleStartCall = async () => {
    if (!selectedLeadId) {
      setErrorMessage("Select a lead first.");
      return;
    }

    setIsStartingCall(true);
    setStatusMessage("");
    setErrorMessage("");
    setCreatedFollowupDraft(null);

    try {
      const res = await api.post("/calls/start-vapi", {
        lead_id: Number(selectedLeadId),
        campaign_id: selectedCampaignId ? Number(selectedCampaignId) : null,
        use_test_number: useTestNumber,
        test_phone_number: testPhoneNumber || null,
        call_mode: useTestNumber ? "test" : "actual",
      });
      setStatusMessage(`${useTestNumber ? "Test call" : "Actual lead call"} started. Call log ID: ${res.data.call_log_id}.`);
      await loadCallLogs();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "AI call could not be started."));
      console.error(err);
    } finally {
      setIsStartingCall(false);
    }
  };

  const handleManualLog = async () => {
    if (!selectedLeadId) {
      setErrorMessage("Select a lead first.");
      return;
    }

    setIsSavingManualLog(true);
    setStatusMessage("");
    setErrorMessage("");
    setCreatedFollowupDraft(null);

    try {
      await api.post("/calls/manual-log", {
        lead_id: Number(selectedLeadId),
        campaign_id: selectedCampaignId ? Number(selectedCampaignId) : null,
        phone_number: phoneNumber || null,
        outcome: manualLog.outcome,
        notes: manualLog.notes || null,
        summary: manualLog.summary || null,
        next_action: manualLog.next_action || null,
      });
      setManualLog(emptyManualLog);
      setStatusMessage("Manual call log saved.");
      await loadCallLogs();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Manual call log could not be saved."));
      console.error(err);
    } finally {
      setIsSavingManualLog(false);
    }
  };

  const handleCreateFollowup = async (callLog) => {
    setCreatingFollowupId(callLog.id);
    setStatusMessage("");
    setErrorMessage("");
    setCreatedFollowupDraft(null);

    try {
      const res = await api.post(`/calls/${callLog.id}/create-followup-email`);
      setCreatedFollowupDraft({
        id: res.data.email_draft_id,
        campaignId: res.data.campaign_id || callLog.campaign_id,
      });
      setStatusMessage(res.data.message || "Follow-up draft created.");
      await loadCallLogs();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Follow-up email draft could not be created."));
      console.error(err);
    } finally {
      setCreatingFollowupId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Calls"
        description="Generate call scripts, start selected Vapi calls, and review call outcomes before follow-up."
      />

      <div className="space-y-6">
        <Card>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-ink">Vapi Status</h2>
              <p className="mt-1 text-sm text-muted">Calls are started only from this backend. Vapi secrets never go to the browser.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant={configStatus?.vapi_enabled ? "success" : "warning"}>
                {configStatus?.vapi_enabled ? "Enabled" : "Disabled"}
              </Badge>
              <Badge variant={configStatus?.configured ? "success" : "warning"}>
                {configStatus?.configured ? "Configured" : "Vapi not configured"}
              </Badge>
              <Badge variant={configStatus?.assistant_configured ? "success" : "warning"}>Assistant</Badge>
              <Badge variant={configStatus?.phone_configured ? "success" : "warning"}>Phone Number</Badge>
            </div>
          </div>
          {configStatus && !configStatus.configured && (
            <p className="mt-4 rounded-2xl border border-warn-soft bg-warn-soft p-3 text-sm text-warn">
              Vapi not configured. You can still generate call scripts and save manual call logs.
            </p>
          )}
        </Card>

        {(statusMessage || errorMessage) && (
          <Card>
            {statusMessage && <p className="rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">{statusMessage}</p>}
            {createdFollowupDraft?.id && (
              <div className="mt-3 flex flex-col gap-2 rounded-lg border border-violet-soft bg-violet-soft p-3 text-sm text-violet sm:flex-row sm:items-center sm:justify-between">
                <span>Draft #{createdFollowupDraft.id} is ready for manual review. It was not sent.</span>
                <Button
                  as={Link}
                  to={`/emails?campaign_id=${createdFollowupDraft.campaignId || ""}&draft_id=${createdFollowupDraft.id}`}
                  size="sm"
                  variant="indigo"
                  className="w-full sm:w-auto"
                >
                  View in Emails
                </Button>
              </div>
            )}
            {errorMessage && <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">{errorMessage}</p>}
          </Card>
        )}

        <div className="grid gap-6 xl:grid-cols-[minmax(320px,460px)_minmax(0,1fr)]">
          <Card>
            <h2 className="text-xl font-semibold tracking-tight text-ink">Start AI Call</h2>
            <div className="mt-4 grid gap-4">
              <label className="text-sm">
                <span className="mb-1 block font-medium text-ink-2">Campaign</span>
                <select
                  value={selectedCampaignId}
                  onChange={(e) => {
                    setSelectedCampaignId(e.target.value);
                    setSelectedLeadId("");
                    setScript(null);
                  }}
                  className="field"
                >
                  <option value="">Choose campaign</option>
                  {campaigns.map((campaign) => (
                    <option key={campaign.id} value={campaign.id}>{campaign.campaign_name}</option>
                  ))}
                </select>
              </label>

              <label className="text-sm">
                <span className="mb-1 block font-medium text-ink-2">Lead</span>
                <select
                  value={selectedLeadId}
                  onChange={(e) => {
                    setSelectedLeadId(e.target.value);
                    setScript(null);
                  }}
                  className="field"
                  disabled={!selectedCampaignId}
                >
                  <option value="">Choose lead</option>
                  {leads.map((lead) => (
                    <option key={lead.id} value={lead.id}>{lead.company_name} {lead.contact_name ? `- ${lead.contact_name}` : ""}</option>
                  ))}
                </select>
              </label>

              <label className="text-sm">
                <span className="mb-1 block font-medium text-ink-2">Lead phone number</span>
                <input
                  type="tel"
                  value={selectedLead?.phone || ""}
                  readOnly
                  className="field"
                  placeholder="+91..."
                />
                <span className="mt-1 block text-xs text-muted">
                  {selectedLead?.phone ? "Saved on the selected lead." : "No saved lead phone. Keep test number checked."}
                </span>
              </label>

              <label className="flex items-center gap-2 rounded-2xl border line-1 surface-sunk p-3 text-sm font-medium text-ink-2">
                <input type="checkbox" checked={useTestNumber} onChange={(e) => setUseTestNumber(e.target.checked)} className="h-4 w-4" />
                Use test phone number
              </label>
              {!useTestNumber && selectedLead?.phone && (
                <p className="rounded-2xl border border-warn-soft bg-warn-soft p-3 text-sm text-warn">
                  Test number is off. Starting the call will use this lead phone number.
                </p>
              )}
              {!useTestNumber && !selectedLead?.phone && (
                <p className="rounded-2xl border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
                  Lead does not have a phone number.
                </p>
              )}

              {useTestNumber && (
                <label className="text-sm">
                  <span className="mb-1 block font-medium text-ink-2">Test phone number override</span>
                  <input
                    type="tel"
                    value={testPhoneNumber}
                    onChange={(e) => setTestPhoneNumber(e.target.value)}
                    className="field"
                    placeholder="Leave blank to use backend default"
                  />
                </label>
              )}

              {selectedLead?.do_not_call && (
                <p className="rounded-2xl border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
                  This lead is marked do-not-call. AI calling is disabled.
                </p>
              )}

              <p className="rounded-2xl border line-1 surface-sunk p-3 text-sm font-semibold text-ink">
                Calling: {callingLabel} {display(callingNumber)}
              </p>

              {selectedCampaign && selectedLead && (
                <div className="rounded-2xl border border-violet-soft bg-violet-soft p-3 text-sm leading-6 text-violet">
                  <p className="font-semibold text-violet">Call context preview</p>
                  <p className="mt-1">
                    This call will use campaign: {selectedCampaign.campaign_name}, offer: {selectedCampaign.offer}, lead: {selectedLead.contact_name || selectedLead.company_name}.
                  </p>
                </div>
              )}

              <div className="grid gap-2 sm:grid-cols-2">
                <Button type="button" variant="secondary" disabled={!selectedLeadId || isGeneratingScript} onClick={handleGenerateScript}>
                  {isGeneratingScript ? "Generating..." : "Generate Call Script"}
                </Button>
                <Button type="button" variant="indigo" disabled={!selectedLeadId || isStartingCall || selectedLead?.do_not_call || (!useTestNumber && !selectedLead?.phone)} onClick={handleStartCall}>
                  {isStartingCall ? "Starting..." : useTestNumber ? "Start Test AI Call" : "Start Actual Lead Call"}
                </Button>
              </div>
            </div>
          </Card>

          <ScriptPreview script={script} />
        </div>

        <Card>
          <h2 className="text-xl font-semibold tracking-tight text-ink">Manual Call Log</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <label className="text-sm">
              <span className="mb-1 block font-medium text-ink-2">Outcome</span>
              <select
                value={manualLog.outcome}
                onChange={(e) => setManualLog((current) => ({ ...current, outcome: e.target.value }))}
                className="field"
              >
                <option value="interested">interested</option>
                <option value="asked_details">asked_details</option>
                <option value="call_later">call_later</option>
                <option value="not_interested">not_interested</option>
                <option value="wrong_person">wrong_person</option>
                <option value="no_answer">no_answer</option>
                <option value="do_not_call">do_not_call</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block font-medium text-ink-2">Next action</span>
              <input
                type="text"
                value={manualLog.next_action}
                onChange={(e) => setManualLog((current) => ({ ...current, next_action: e.target.value }))}
                className="field"
                placeholder="Send proposal by email"
              />
            </label>
            <label className="text-sm lg:col-span-2">
              <span className="mb-1 block font-medium text-ink-2">Notes</span>
              <textarea
                value={manualLog.notes}
                onChange={(e) => setManualLog((current) => ({ ...current, notes: e.target.value }))}
                className="field min-h-24"
                placeholder="Professor asked to send proposal over email."
              />
            </label>
          </div>
          <div className="mt-4">
            <Button type="button" disabled={!selectedLeadId || isSavingManualLog} onClick={handleManualLog}>
              {isSavingManualLog ? "Saving..." : "Save Manual Call Log"}
            </Button>
          </div>
        </Card>

        <Card>
          <div className="mb-5">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Call Logs</h2>
            <p className="mt-1 text-sm text-muted">Latest Vapi and manual calls for the selected lead or campaign.</p>
          </div>

          {isLoading ? (
            <p className="rounded-2xl border line-1 surface-sunk p-4 text-sm text-ink-2">Loading calls...</p>
          ) : callLogs.length === 0 ? (
            <EmptyState title="No calls yet" description="Generate a script, start a selected AI call, or save a manual call log." />
          ) : (
            <div className="space-y-3">
              {callLogs.map((callLog) => (
                <CallLogCard
                  key={callLog.id}
                  callLog={callLog}
                  onCreateFollowup={handleCreateFollowup}
                  creatingFollowupId={creatingFollowupId}
                />
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export default Calls;
