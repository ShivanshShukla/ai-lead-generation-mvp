import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { bulkEnrich, enrichLead } from "../api/hunter";
import { bulkEnrich as apolloBulkEnrich, enrichLead as apolloEnrichLead } from "../api/apollo";
import EmailExtraction from "../components/EmailExtraction";
import LeadAgentLauncher from "../components/LeadAgentLauncher";
import LeadTable from "../components/LeadTable";
import LeadUpload from "../components/LeadUpload";
import api from "../services/api";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import PageHeader from "../components/ui/PageHeader";

function Leads() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState(searchParams.get("campaign_id") || "");
  const [isLoadingCampaigns, setIsLoadingCampaigns] = useState(true);
  const [campaignsError, setCampaignsError] = useState("");
  const [leads, setLeads] = useState([]);
  const [isLoadingLeads, setIsLoadingLeads] = useState(false);
  const [leadsError, setLeadsError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [extractingLeadId, setExtractingLeadId] = useState(null);
  const [leadExtractionMessage, setLeadExtractionMessage] = useState("");
  const [leadExtractionError, setLeadExtractionError] = useState("");
  const [hunterMessage, setHunterMessage] = useState("");
  const [hunterError, setHunterError] = useState("");
  const [enrichingLeadId, setEnrichingLeadId] = useState(null);
  const [isBulkEnriching, setIsBulkEnriching] = useState(false);
  const [apolloMessage, setApolloMessage] = useState("");
  const [apolloError, setApolloError] = useState("");
  const [apolloEnrichingLeadId, setApolloEnrichingLeadId] = useState(null);
  const [isApolloBulkEnriching, setIsApolloBulkEnriching] = useState(false);
  const [isScoringCampaign, setIsScoringCampaign] = useState(false);
  const [scoringJob, setScoringJob] = useState(null);
  const [scoreLimit, setScoreLimit] = useState(10);
  const [scoringLeadId, setScoringLeadId] = useState(null);
  const [leadScoringMessage, setLeadScoringMessage] = useState("");
  const [leadScoringError, setLeadScoringError] = useState("");
  const [leadResearchMessage, setLeadResearchMessage] = useState("");
  const [leadResearchError, setLeadResearchError] = useState("");
  const [researchingLeadId, setResearchingLeadId] = useState(null);
  const [isResearchingCampaign, setIsResearchingCampaign] = useState(false);
  const [researchJob, setResearchJob] = useState(null);
  const [researchLimit, setResearchLimit] = useState(10);
  const [generatingCallScriptLeadId, setGeneratingCallScriptLeadId] = useState(null);
  const [startingCallLeadId, setStartingCallLeadId] = useState(null);
  const [startingCallMode, setStartingCallMode] = useState(null);
  const [callScriptsByLead, setCallScriptsByLead] = useState({});
  const [callMessage, setCallMessage] = useState("");
  const [callError, setCallError] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("All");
  const [qualificationFilter, setQualificationFilter] = useState("All");
  const [sortByScore, setSortByScore] = useState(true);
  const scoringPollRef = useRef(null);
  const researchPollRef = useRef(null);

  const isScoringJobRunning = scoringJob?.status === "pending" || scoringJob?.status === "running";
  const isResearchJobRunning = researchJob?.status === "pending" || researchJob?.status === "running";
  const scoringProgress = scoringJob?.percentage ?? 0;
  const researchProgress = researchJob?.percentage ?? 0;

  const selectedCampaign = useMemo(
    () => campaigns.find((campaign) => String(campaign.id) === String(selectedCampaignId)),
    [campaigns, selectedCampaignId]
  );

  const emailsFoundCount = useMemo(
    () => leads.filter((lead) => lead.email || lead.status === "email_found").length,
    [leads]
  );

  const hunterEligibleLeadCount = useMemo(
    () => leads.filter((lead) => !lead.email && lead.website).length,
    [leads]
  );

  const scoredLeadCount = useMemo(
    () => leads.filter((lead) => lead.ai_score !== null && lead.ai_score !== undefined).length,
    [leads]
  );

  const researchedLeadCount = useMemo(
    () => leads.filter((lead) => lead.research_status === "researched").length,
    [leads]
  );

  const averageResearchConfidence = useMemo(() => {
    const confidenceValues = leads
      .map((lead) => lead.research_confidence)
      .filter((value) => value !== null && value !== undefined);

    if (confidenceValues.length === 0) {
      return 0;
    }

    return confidenceValues.reduce((total, value) => total + Number(value), 0) / confidenceValues.length;
  }, [leads]);

  const visibleLeads = useMemo(() => {
    const filteredLeads = leads.filter((lead) => {
      const priorityMatches = priorityFilter === "All" || lead.ai_priority === priorityFilter;
      const qualificationMatches = qualificationFilter === "All" || lead.ai_qualification === qualificationFilter;

      return priorityMatches && qualificationMatches;
    });

    if (!sortByScore) {
      return filteredLeads;
    }

    return [...filteredLeads].sort((a, b) => (
      (b.ai_score ?? -1) - (a.ai_score ?? -1)
    ));
  }, [leads, priorityFilter, qualificationFilter, sortByScore]);

  useEffect(() => {
    const fetchCampaigns = async () => {
      setIsLoadingCampaigns(true);
      setCampaignsError("");

      try {
        const res = await api.get("/campaigns/");
        setCampaigns(Array.isArray(res.data.data) ? res.data.data : []);
      } catch (err) {
        setCampaignsError(getFriendlyErrorMessage(err, "Could not load campaigns. Please try again."));
        console.error(err);
      } finally {
        setIsLoadingCampaigns(false);
      }
    };

    fetchCampaigns();
  }, []);

  useEffect(() => {
    if (!selectedCampaignId) {
      return;
    }

    const fetchLeads = async () => {
      setIsLoadingLeads(true);
      setLeadsError("");

      try {
        const res = await api.get(`/leads/campaign/${selectedCampaignId}`);
        setLeads(Array.isArray(res.data.data) ? res.data.data : []);
      } catch (err) {
        const detail = err.response?.data?.detail;
        setLeadsError(err.response ? detail || "Could not load leads. Please try again." : getFriendlyErrorMessage(err));
        console.error(err);
      } finally {
        setIsLoadingLeads(false);
      }
    };

    fetchLeads();
  }, [selectedCampaignId, refreshKey]);

  const refreshLeads = () => {
    setRefreshKey((currentKey) => currentKey + 1);
  };

  function stopScoringPolling() {
    if (scoringPollRef.current) {
      clearInterval(scoringPollRef.current);
      scoringPollRef.current = null;
    }
  }

  function stopResearchPolling() {
    if (researchPollRef.current) {
      clearInterval(researchPollRef.current);
      researchPollRef.current = null;
    }
  }

  function handleCompletedScoringJob(nextJob) {
    stopScoringPolling();
    refreshLeads();

    if (nextJob.status === "failed") {
      setLeadScoringError(nextJob.error || "AI lead scoring failed. Please check backend logs.");
      return;
    }

    setLeadScoringMessage(
      `Scoring completed. Scored ${nextJob.scored ?? 0}, skipped ${nextJob.skipped ?? 0}, failed ${nextJob.failed ?? 0}. Processed ${nextJob.processed ?? 0}/${nextJob.total ?? 0} leads. Remaining unscored: ${nextJob.remaining_unscored ?? 0}.`
    );
  }

  function startScoringPolling(jobId) {
    stopScoringPolling();

    const pollJob = async () => {
      try {
        const res = await api.get(`/lead-scoring/scoring-job/${jobId}`);
        const nextJob = res.data;
        setScoringJob(nextJob);

        if (nextJob.status === "completed" || nextJob.status === "failed") {
          handleCompletedScoringJob(nextJob);
        }
      } catch (err) {
        stopScoringPolling();
        setLeadScoringError(getFriendlyErrorMessage(err, "Could not load AI scoring progress."));
        console.error(err);
      }
    };

    pollJob();
    scoringPollRef.current = setInterval(pollJob, 3000);
  }

  function handleCompletedResearchJob(nextJob) {
    stopResearchPolling();
    refreshLeads();

    if (nextJob.status === "failed") {
      setLeadResearchError(nextJob.error || "Campaign lead research failed. Please check backend logs.");
      return;
    }

    setLeadResearchMessage(
      `Research completed. Researched ${nextJob.researched ?? 0}, skipped ${nextJob.skipped ?? 0}, failed ${nextJob.failed ?? 0}. Processed ${nextJob.processed ?? 0}/${nextJob.total ?? 0} leads.`
    );
  }

  function startResearchPolling(jobId) {
    stopResearchPolling();

    const pollJob = async () => {
      try {
        const res = await api.get(`/campaigns/research-job/${jobId}`);
        const nextJob = res.data;
        setResearchJob(nextJob);

        if (nextJob.status === "completed" || nextJob.status === "failed") {
          handleCompletedResearchJob(nextJob);
        }
      } catch (err) {
        stopResearchPolling();
        setLeadResearchError(getFriendlyErrorMessage(err, "Could not load lead research progress."));
        console.error(err);
      }
    };

    pollJob();
    researchPollRef.current = setInterval(pollJob, 3000);
  }

  useEffect(() => {
    return () => {
      stopScoringPolling();
      stopResearchPolling();
    };
  }, []);

  const handleCampaignChange = (e) => {
    const nextCampaignId = e.target.value;
    stopScoringPolling();
    stopResearchPolling();
    setSelectedCampaignId(nextCampaignId);
    setSearchParams(nextCampaignId ? { campaign_id: nextCampaignId } : {});
    setLeads([]);
    setLeadsError("");
    setLeadExtractionMessage("");
    setLeadExtractionError("");
    setHunterMessage("");
    setHunterError("");
    setApolloMessage("");
    setApolloError("");
    setLeadScoringMessage("");
    setLeadScoringError("");
    setScoringJob(null);
    setLeadResearchMessage("");
    setLeadResearchError("");
    setResearchJob(null);
    setCallMessage("");
    setCallError("");
    setCallScriptsByLead({});
    setPriorityFilter("All");
    setQualificationFilter("All");
  };

  const handleHunterEnrichLead = async (lead) => {
    setEnrichingLeadId(lead.id);
    setHunterMessage("");
    setHunterError("");

    try {
      const result = await enrichLead(lead.id, {
        mode: "domain",
        minConfidence: 50,
      });

      if (result.updated) {
        setHunterMessage(
          `Hunter found and saved ${result.email} for ${lead.company_name}. Confidence: ${result.confidence ?? "N/A"}.`
        );
        refreshLeads();
      } else {
        setHunterMessage(result.message || "Hunter did not find a usable email for this lead.");
      }
    } catch (err) {
      setHunterError(getFriendlyErrorMessage(err, "Hunter enrichment failed. Please check the API key and try again."));
      console.error(err);
    } finally {
      setEnrichingLeadId(null);
    }
  };

  const handleHunterBulkEnrich = async () => {
    if (!selectedCampaignId) {
      return;
    }

    const shouldContinue = window.confirm(
      "Hunter bulk enrichment can use API credits for up to 20 leads. Continue?"
    );

    if (!shouldContinue) {
      return;
    }

    setIsBulkEnriching(true);
    setHunterMessage("");
    setHunterError("");

    try {
      const result = await bulkEnrich(selectedCampaignId, {
        mode: "domain",
        limit: 20,
        minConfidence: 50,
      });

      setHunterMessage(
        `Hunter bulk enrichment completed. Found ${result.enriched ?? 0}, skipped ${result.skipped ?? 0}, failed ${result.failed ?? 0}.`
      );
      refreshLeads();
    } catch (err) {
      setHunterError(getFriendlyErrorMessage(err, "Hunter bulk enrichment failed. Please check the API key and try again."));
      console.error(err);
    } finally {
      setIsBulkEnriching(false);
    }
  };

  const handleApolloEnrichLead = async (lead) => {
    setApolloEnrichingLeadId(lead.id);
    setApolloMessage("");
    setApolloError("");

    try {
      const result = await apolloEnrichLead(lead.id);

      if (result.updated) {
        setApolloMessage(
          `Apollo found and saved ${result.email} for ${lead.company_name}. Name: ${result.name || "N/A"}, Title: ${result.title || "N/A"}.`
        );
        refreshLeads();
      } else {
        setApolloMessage(result.message || "Apollo did not find an email for this lead.");
      }
    } catch (err) {
      setApolloError(getFriendlyErrorMessage(err, "Apollo enrichment failed. Please check the API key and try again."));
      console.error(err);
    } finally {
      setApolloEnrichingLeadId(null);
    }
  };

  const handleApolloBulkEnrich = async () => {
    if (!selectedCampaignId) {
      return;
    }

    const shouldContinue = window.confirm(
      "Apollo bulk enrichment can find emails for up to 20 leads. Continue?"
    );

    if (!shouldContinue) {
      return;
    }

    setIsApolloBulkEnriching(true);
    setApolloMessage("");
    setApolloError("");

    try {
      const result = await apolloBulkEnrich(selectedCampaignId, 20);

      setApolloMessage(
        `Apollo bulk enrichment completed. Found ${result.enriched ?? 0}, skipped ${result.skipped ?? 0}.`
      );
      refreshLeads();
    } catch (err) {
      setApolloError(getFriendlyErrorMessage(err, "Apollo bulk enrichment failed. Please check the API key and try again."));
      console.error(err);
    } finally {
      setIsApolloBulkEnriching(false);
    }
  };

  const handleExtractLeadEmail = async (leadId) => {
    setExtractingLeadId(leadId);
    setLeadExtractionMessage("");
    setLeadExtractionError("");

    try {
      const res = await api.post(`/leads/extract-email/${leadId}`);
      const savedEmail = res.data.saved_email;

      setLeadExtractionMessage(
        savedEmail
          ? `Email extraction completed. Saved email: ${savedEmail}.`
          : "Email extraction completed. No public email was found."
      );
      refreshLeads();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setLeadExtractionError(err.response ? detail || "Email extraction failed. Please try again." : getFriendlyErrorMessage(err));
      console.error(err);
    } finally {
      setExtractingLeadId(null);
    }
  };

  const handleScoreCampaignLeads = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsScoringCampaign(true);
    setScoringJob(null);
    setLeadScoringMessage("");
    setLeadScoringError("");

    try {
      const res = await api.post(`/lead-scoring/score-campaign-async/${selectedCampaignId}`, null, {
        params: {
          limit: scoreLimit,
        },
      });

      if (res.data.status === "nothing_to_do") {
        setScoringJob(null);
        setLeadScoringMessage(res.data.message || "No leads need scoring.");
        refreshLeads();
        return;
      }

      setScoringJob(res.data);
      startScoringPolling(res.data.job_id);
    } catch (err) {
      setLeadScoringError(getFriendlyErrorMessage(err, "AI lead scoring failed. Please try again.", "lead-scoring"));
      console.error(err);
    } finally {
      setIsScoringCampaign(false);
    }
  };

  const handleScoreLead = async (lead) => {
    const isRescore = lead.ai_score !== null && lead.ai_score !== undefined;

    setScoringLeadId(lead.id);
    setLeadScoringMessage("");
    setLeadScoringError("");

    try {
      await api.post(`/lead-scoring/score/${lead.id}`, null, {
        params: {
          force: isRescore,
        },
      });
      setLeadScoringMessage(isRescore ? "Lead rescored successfully." : "Lead scored successfully.");
      refreshLeads();
    } catch (err) {
      setLeadScoringError(getFriendlyErrorMessage(err, "AI lead scoring failed. Please try again.", "lead-scoring"));
      console.error(err);
    } finally {
      setScoringLeadId(null);
    }
  };

  const handleResearchLead = async (lead) => {
    setResearchingLeadId(lead.id);
    setLeadResearchMessage("");
    setLeadResearchError("");

    try {
      const res = await api.post(`/leads/${lead.id}/research`);
      const confidence = res.data.research_confidence;
      setLeadResearchMessage(
        `Research completed for ${lead.company_name}. Confidence: ${confidence ?? "N/A"}.`
      );
      refreshLeads();
    } catch (err) {
      setLeadResearchError(getFriendlyErrorMessage(err, "Lead research failed. Please try again."));
      console.error(err);
    } finally {
      setResearchingLeadId(null);
    }
  };

  const handleResearchCampaignLeads = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsResearchingCampaign(true);
    setResearchJob(null);
    setLeadResearchMessage("");
    setLeadResearchError("");

    try {
      const res = await api.post(`/campaigns/${selectedCampaignId}/research-leads-async`, null, {
        params: {
          limit: researchLimit,
        },
      });

      if (res.data.status === "nothing_to_do") {
        setResearchJob(null);
        setLeadResearchMessage(res.data.message || "No leads need research.");
        refreshLeads();
        return;
      }

      setResearchJob(res.data);
      startResearchPolling(res.data.job_id);
    } catch (err) {
      setLeadResearchError(getFriendlyErrorMessage(err, "Campaign lead research failed. Please try again."));
      console.error(err);
    } finally {
      setIsResearchingCampaign(false);
    }
  };

  const handleGenerateCallScript = async (lead) => {
    setGeneratingCallScriptLeadId(lead.id);
    setCallMessage("");
    setCallError("");

    try {
      const res = await api.post("/calls/generate-script", {
        lead_id: lead.id,
        campaign_id: lead.campaign_id,
      });
      setCallScriptsByLead((current) => ({
        ...current,
        [lead.id]: res.data,
      }));
      setCallMessage(`Call script generated for ${lead.company_name}.`);
    } catch (err) {
      setCallError(getFriendlyErrorMessage(err, "Call script could not be generated."));
      console.error(err);
    } finally {
      setGeneratingCallScriptLeadId(null);
    }
  };

  const handleStartLeadCall = async (lead, callMode) => {
    setStartingCallLeadId(lead.id);
    setStartingCallMode(callMode);
    setCallMessage("");
    setCallError("");

    try {
      const res = await api.post("/calls/start-vapi", {
        lead_id: lead.id,
        campaign_id: lead.campaign_id,
        use_test_number: callMode === "test",
        call_mode: callMode,
      });
      setCallMessage(`${callMode === "actual" ? "Actual lead call" : "AI test call"} started. Call log ID: ${res.data.call_log_id}.`);
      refreshLeads();
    } catch (err) {
      setCallError(getFriendlyErrorMessage(err, `${callMode === "actual" ? "Actual lead call" : "AI test call"} could not be started.`));
      console.error(err);
    } finally {
      setStartingCallLeadId(null);
      setStartingCallMode(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Leads"
        description="Upload, enrich, score, and review leads without losing the business context behind each recommendation."
      />

      <div className="space-y-6">
        <Card>
          <div className="mb-4">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Select Campaign</h2>
            <p className="mt-1 text-sm text-muted">
              Leads will be saved under the campaign you choose here.
            </p>
          </div>

          {campaignsError && (
            <p className="mb-4 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
              {campaignsError}
            </p>
          )}

          <select
            value={selectedCampaignId}
            onChange={handleCampaignChange}
            className="field"
            disabled={isLoadingCampaigns || campaigns.length === 0}
          >
            <option value="">
              {isLoadingCampaigns ? "Loading campaigns..." : "Choose a campaign"}
            </option>
            {campaigns.map((campaign) => (
              <option key={campaign.id} value={campaign.id}>
                {campaign.campaign_name}
              </option>
            ))}
          </select>

          {!isLoadingCampaigns && !campaignsError && campaigns.length === 0 && (
            <p className="mt-3 text-sm text-muted">
              Create your first campaign to start lead outreach.
            </p>
          )}
        </Card>

        {selectedCampaign && (
          <Card>
            <div className="mb-4">
              <h2 className="text-xl font-semibold tracking-tight text-ink">Campaign Summary</h2>
              <p className="mt-1 text-sm text-muted">{selectedCampaign.campaign_name}</p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <div className="rounded-2xl border line-1 surface-sunk p-4">
                <p className="text-xs text-muted">Industry</p>
                <p className="mt-1 break-words font-medium text-ink">{selectedCampaign.industry || "N/A"}</p>
              </div>
              <div className="rounded-2xl border line-1 surface-sunk p-4">
                <p className="text-xs text-muted">Location</p>
                <p className="mt-1 break-words font-medium text-ink">{selectedCampaign.location || "N/A"}</p>
              </div>
              <div className="rounded-2xl border line-1 surface-sunk p-4">
                <p className="text-xs text-muted">Target Role</p>
                <p className="mt-1 break-words font-medium text-ink">{selectedCampaign.target_role || "N/A"}</p>
              </div>
              <div className="rounded-2xl border line-1 surface-sunk p-4 sm:col-span-2 xl:col-span-3">
                <p className="text-xs text-muted">Offer</p>
                <p className="mt-1 break-words text-sm leading-6 text-ink">{selectedCampaign.offer || "N/A"}</p>
              </div>
              <div className="rounded-2xl border border-info-soft bg-info-soft p-4">
                <p className="text-xs text-info">Lead Count</p>
                <p className="mt-1 text-2xl font-semibold text-info">{leads.length}</p>
              </div>
              <div className="rounded-2xl border border-success-soft bg-success-soft p-4">
                <p className="text-xs text-success">Emails Found</p>
                <p className="mt-1 text-2xl font-semibold text-success">{emailsFoundCount}</p>
              </div>
              <div className="rounded-2xl border border-violet-soft bg-violet-soft p-4">
                <p className="text-xs text-violet">AI Scored</p>
                <p className="mt-1 text-2xl font-semibold text-violet">{scoredLeadCount}</p>
              </div>
              <div className="rounded-2xl border border-info-soft bg-info-soft p-4">
                <p className="text-xs text-info">AI Researched</p>
                <p className="mt-1 text-2xl font-semibold text-info">{researchedLeadCount}</p>
              </div>
              <div className="rounded-2xl border border-violet-soft bg-violet-soft p-4">
                <p className="text-xs text-violet">Avg Research Confidence</p>
                <p className="mt-1 text-2xl font-semibold text-violet">{averageResearchConfidence.toFixed(1)}</p>
              </div>
            </div>
          </Card>
        )}

        {selectedCampaign && (
          <LeadAgentLauncher
            campaign={selectedCampaign}
            onLeadsFound={refreshLeads}
          />
        )}

        {selectedCampaign && (
          <Card>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-ink">AI Lead Scoring</h2>
                <p className="mt-1 text-sm text-muted">
                  AI scoring runs in the background, one lead at a time, to stay gentle on Gemini quota.
                </p>
                <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-ink-2 md:grid-cols-3">
                  <p className="rounded border bg-success-soft p-3">
                    <span className="font-semibold text-success">Fit Score</span> = company and campaign match.
                  </p>
                  <p className="rounded border bg-warn-soft p-3">
                    <span className="font-semibold text-warn">Contact Confidence</span> = quality of contact details.
                  </p>
                  <p className="rounded border bg-violet-soft p-3">
                    <span className="font-semibold text-violet">Final AI Score</span> = outreach readiness.
                  </p>
                </div>
              </div>

              <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
                <label className="text-sm">
                  <span className="mb-1 block font-medium text-ink-2">Batch size</span>
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={scoreLimit}
                    onChange={(e) => setScoreLimit(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}
                    className="field sm:w-28"
                  />
                </label>
                <Button
                  type="button"
                  variant="indigo"
                  className="w-full self-end lg:w-auto"
                  disabled={!selectedCampaignId || isScoringCampaign || isScoringJobRunning || leads.length === 0}
                  onClick={handleScoreCampaignLeads}
                >
                  {isScoringCampaign
                    ? "Starting scoring..."
                    : isScoringJobRunning
                    ? `Scoring... ${scoringProgress}%`
                    : "Score Leads with AI"}
                </Button>
              </div>
            </div>

            {isScoringJobRunning && (
              <div className="mt-5 rounded-2xl border border-violet-soft bg-violet-soft p-4">
                <div className="mb-2 flex items-center justify-between gap-3 text-xs font-semibold text-violet">
                  <span>Scoring {scoringJob.processed ?? 0}/{scoringJob.total ?? 0} leads</span>
                  <span>{scoringProgress}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full surface-2">
                  <div
                    className="h-full rounded-full bg-violet-solid transition-all duration-500"
                    style={{ width: `${scoringProgress}%` }}
                  />
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <span className="rounded border border-success-soft surface-2 px-2 py-1 text-success">
                    Scored: {scoringJob.scored ?? 0}
                  </span>
                  <span className="rounded border line-1 surface-2 px-2 py-1 text-ink-2">
                    Skipped: {scoringJob.skipped ?? 0}
                  </span>
                  <span className="rounded border border-danger-soft surface-2 px-2 py-1 text-danger">
                    Failed: {scoringJob.failed ?? 0}
                  </span>
                </div>
              </div>
            )}

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <label className="text-sm">
                <span className="mb-1 block font-medium text-ink-2">Priority</span>
                <select
                  value={priorityFilter}
                  onChange={(e) => setPriorityFilter(e.target.value)}
                  className="field"
                >
                  <option>All</option>
                  <option>High</option>
                  <option>Medium</option>
                  <option>Low</option>
                </select>
              </label>

              <label className="text-sm">
                <span className="mb-1 block font-medium text-ink-2">Qualification</span>
                <select
                  value={qualificationFilter}
                  onChange={(e) => setQualificationFilter(e.target.value)}
                  className="field"
                >
                  <option>All</option>
                  <option>Hot</option>
                  <option>Warm</option>
                  <option>Cold</option>
                  <option>Not Relevant</option>
                </select>
              </label>

              <label className="flex min-h-11 items-center gap-2 self-end rounded-2xl border line-1 surface-2 px-3 text-sm font-medium text-ink-2">
                <input
                  type="checkbox"
                  checked={sortByScore}
                  onChange={(e) => setSortByScore(e.target.checked)}
                  className="h-4 w-4"
                />
                Sort by final AI score
              </label>
            </div>
          </Card>
        )}

        {selectedCampaign && (
          <Card>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-ink">AI Lead Research</h2>
                <p className="mt-1 text-sm text-muted">
                  Research uses a lead website plus campaign context before scoring or drafting.
                </p>
                <p className="mt-2 text-xs text-muted">
                  Runs in the background and fetches only a few public pages per lead.
                </p>
              </div>

              <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
                <label className="text-sm">
                  <span className="mb-1 block font-medium text-ink-2">Batch size</span>
                  <input
                    type="number"
                    min="1"
                    max="500"
                    value={researchLimit}
                    onChange={(e) => setResearchLimit(Math.max(1, Math.min(500, Number(e.target.value) || 1)))}
                    className="field sm:w-28"
                  />
                </label>
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full self-end lg:w-auto"
                  disabled={!selectedCampaignId || isResearchingCampaign || isResearchJobRunning || leads.length === 0}
                  onClick={handleResearchCampaignLeads}
                >
                  {isResearchingCampaign
                    ? "Starting research..."
                    : isResearchJobRunning
                    ? `Researching... ${researchProgress}%`
                    : "Research Unresearched Leads"}
                </Button>
              </div>
            </div>

            {isResearchJobRunning && (
              <div className="mt-5 rounded-2xl border border-info-soft bg-info-soft p-4">
                <div className="mb-2 flex items-center justify-between gap-3 text-xs font-semibold text-info">
                  <span>Researching {researchJob.processed ?? 0}/{researchJob.total ?? 0} leads</span>
                  <span>{researchProgress}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full surface-2">
                  <div
                    className="h-full rounded-full bg-info-solid transition-all duration-500"
                    style={{ width: `${researchProgress}%` }}
                  />
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <span className="rounded border border-success-soft surface-2 px-2 py-1 text-success">
                    Researched: {researchJob.researched ?? 0}
                  </span>
                  <span className="rounded border line-1 surface-2 px-2 py-1 text-ink-2">
                    Skipped: {researchJob.skipped ?? 0}
                  </span>
                  <span className="rounded border border-danger-soft surface-2 px-2 py-1 text-danger">
                    Failed: {researchJob.failed ?? 0}
                  </span>
                </div>
              </div>
            )}
          </Card>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <LeadUpload
            campaignId={selectedCampaignId}
            onUploadComplete={refreshLeads}
          />

          <EmailExtraction
            campaignId={selectedCampaignId}
            onExtractionComplete={refreshLeads}
          />
        </div>

        {selectedCampaign && (
          <Card>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-ink">Hunter Email Enrichment</h2>
                <p className="mt-1 text-sm text-muted">
                  Use Hunter.io for leads that have a website but no saved email.
                </p>
                <p className="mt-2 text-xs text-muted">
                  Eligible leads in this campaign: {hunterEligibleLeadCount}
                </p>
              </div>

              <Button
                type="button"
                variant="secondary"
                className="w-full lg:w-auto"
                disabled={!selectedCampaignId || isBulkEnriching || hunterEligibleLeadCount === 0}
                onClick={handleHunterBulkEnrich}
              >
                {isBulkEnriching ? "Searching Hunter..." : "Bulk Find Emails"}
              </Button>
            </div>
          </Card>
        )}

        {selectedCampaign && (
          <Card>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-ink">Apollo Email Enrichment</h2>
                <p className="mt-1 text-sm text-muted">
                  Use Apollo.io to find verified emails and contact details from company databases.
                </p>
                <p className="mt-2 text-xs text-muted">
                  Eligible leads in this campaign: {hunterEligibleLeadCount}
                </p>
              </div>

              <Button
                type="button"
                variant="secondary"
                className="w-full lg:w-auto"
                disabled={!selectedCampaignId || isApolloBulkEnriching || hunterEligibleLeadCount === 0}
                onClick={handleApolloBulkEnrich}
              >
                {isApolloBulkEnriching ? "Searching Apollo..." : "Bulk Search Apollo"}
              </Button>
            </div>
          </Card>
        )}

        {selectedCampaign && (
          <Card>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-ink">Export Leads</h2>
                <p className="mt-1 text-sm text-muted">
                  Download all leads from this campaign as a CSV file.
                </p>
                <p className="mt-2 text-xs text-muted">
                  Total leads: {leads.length}
                </p>
              </div>

              <a
                href={`${import.meta.env.VITE_API_BASE_URL}/leads/campaign/${selectedCampaignId}/export-csv`}
                download
                className="w-full rounded-lg bg-success-solid px-4 py-2 text-center text-white hover:opacity-90 disabled:surface-3 lg:w-auto"
              >
                ⬇ Download Leads CSV
              </a>
            </div>
          </Card>
        )}

        {(leadExtractionMessage || leadExtractionError || hunterMessage || hunterError || apolloMessage || apolloError || leadScoringMessage || leadScoringError || leadResearchMessage || leadResearchError || callMessage || callError) && (
          <Card>
            {callMessage && (
              <p className="rounded-lg border border-violet-soft bg-violet-soft p-3 text-sm text-violet">
                {callMessage}
              </p>
            )}

            {hunterMessage && (
              <p className="mt-3 rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success first:mt-0">
                {hunterMessage}
              </p>
            )}

            {apolloMessage && (
              <p className="mt-3 rounded-lg border border-info-soft bg-info-soft p-3 text-sm text-info first:mt-0">
                {apolloMessage}
              </p>
            )}

            {leadResearchMessage && (
              <p className="mt-3 rounded-lg border border-info-soft bg-info-soft p-3 text-sm text-info first:mt-0">
                {leadResearchMessage}
              </p>
            )}

            {leadExtractionMessage && (
              <p className="mt-3 rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success first:mt-0">
                {leadExtractionMessage}
              </p>
            )}

            {leadScoringMessage && (
              <p className="mt-3 rounded-lg border border-violet-soft bg-violet-soft p-3 text-sm text-violet first:mt-0">
                {leadScoringMessage}
              </p>
            )}

            {leadExtractionError && (
              <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">
                {leadExtractionError}
              </p>
            )}

            {hunterError && (
              <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">
                {hunterError}
              </p>
            )}

            {apolloError && (
              <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">
                {apolloError}
              </p>
            )}

            {leadScoringError && (
              <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">
                {leadScoringError}
              </p>
            )}

            {leadResearchError && (
              <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">
                {leadResearchError}
              </p>
            )}

            {callError && (
              <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">
                {callError}
              </p>
            )}
          </Card>
        )}

        <LeadTable
          leads={visibleLeads}
          isLoading={isLoadingLeads}
          error={leadsError}
          hasSelectedCampaign={Boolean(selectedCampaignId)}
          onExtractEmail={handleExtractLeadEmail}
          extractingLeadId={extractingLeadId}
          onHunterEnrichLead={handleHunterEnrichLead}
          enrichingLeadId={enrichingLeadId}
          onApolloEnrichLead={handleApolloEnrichLead}
          apolloEnrichingLeadId={apolloEnrichingLeadId}
          onScoreLead={handleScoreLead}
          scoringLeadId={scoringLeadId}
          onResearchLead={handleResearchLead}
          researchingLeadId={researchingLeadId}
          onGenerateCallScript={handleGenerateCallScript}
          generatingCallScriptLeadId={generatingCallScriptLeadId}
          onStartTestCall={(lead) => handleStartLeadCall(lead, "test")}
          onStartActualCall={(lead) => handleStartLeadCall(lead, "actual")}
          startingCallLeadId={startingCallLeadId}
          startingCallMode={startingCallMode}
          callScriptsByLead={callScriptsByLead}
        />
      </div>
    </div>
  );
}

export default Leads;
