import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";
import { formatDateTimeIST } from "../utils/dateUtils";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import PageHeader from "../components/ui/PageHeader";

const emptyForm = {
  title: "",
  raw_goal: "",
  target_domain: "",
  target_location: "",
  offer: "",
};

function splitLines(value) {
  return String(value || "")
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseFollowUps(value) {
  const text = String(value || "").trim();

  if (!text) {
    return [];
  }

  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      return parsed.map((item, index) => ({
        step: item.step || index + 1,
        purpose: item.purpose || "Follow up",
        message: item.message || "",
      }));
    }
  } catch {
    return splitLines(text).map((message, index) => ({
      step: index + 1,
      purpose: "Follow up",
      message,
    }));
  }

  return [];
}

function TextBlock({ label, value, className = "" }) {
  if (!value) {
    return null;
  }

  return (
    <div className={`glass rounded-2xl p-4 ${className}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 whitespace-pre-line break-words text-sm leading-6 text-ink-2">{value}</p>
    </div>
  );
}

function ListBlock({ label, value }) {
  const items = splitLines(value);

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="rounded-2xl border line-1 surface-2 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {items.map((item, index) => (
          <span key={`${item}-${index}`} className="rounded-full border line-1 surface-sunk px-3 py-1 text-xs font-medium text-ink-2">
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function StrategyView({ opportunity, onConvert, onCreateDiscoveryJob, isConverting, isCreatingDiscoveryJob }) {
  if (!opportunity) {
    return (
      <Card>
        <p className="text-sm text-muted">Select an opportunity to view or generate its strategy.</p>
      </Card>
    );
  }

  const followUps = parseFollowUps(opportunity.follow_up_sequence);
  const hasStrategy = Boolean(opportunity.ai_summary || opportunity.suggested_campaign_name);

  return (
    <Card>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={opportunity.status}>{opportunity.status}</Badge>
            {opportunity.converted_campaign_id && <Badge variant="success">Campaign created</Badge>}
          </div>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-ink">
            {opportunity.title}
          </h2>
          <p className="mt-2 max-w-3xl whitespace-pre-line break-words text-sm leading-6 text-ink-2">
            {opportunity.raw_goal}
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row lg:flex-col">
          <Button
            type="button"
            variant="success"
            disabled={!hasStrategy || isConverting || Boolean(opportunity.converted_campaign_id)}
            onClick={() => onConvert(opportunity)}
          >
            {isConverting ? "Creating..." : opportunity.converted_campaign_id ? "Campaign Created" : "Create Campaign from Strategy"}
          </Button>
          {opportunity.converted_campaign_id && (
            <Button as={Link} to="/campaigns" variant="secondary">
              Open Campaigns
            </Button>
          )}
          <Button
            type="button"
            variant="indigo"
            disabled={!hasStrategy || isCreatingDiscoveryJob}
            onClick={() => onCreateDiscoveryJob(opportunity)}
          >
            {isCreatingDiscoveryJob ? "Creating..." : "Create Lead Discovery Job"}
          </Button>
        </div>
      </div>

      {!hasStrategy ? (
        <div className="mt-6 rounded-2xl border border-dashed line-1 p-6 text-center">
          <p className="text-sm font-medium text-ink-2">No strategy generated yet.</p>
          <p className="mt-1 text-sm text-muted">Generate the strategy from the opportunity card.</p>
        </div>
      ) : (
        <div className="mt-6 space-y-5">
          <div className="grid gap-4 xl:grid-cols-2">
            <TextBlock label="AI summary" value={opportunity.ai_summary} />
            <TextBlock label="Target audience" value={opportunity.target_audience} />
            <TextBlock label="Value proposition" value={opportunity.value_proposition} />
            <TextBlock label="Outreach angle" value={opportunity.outreach_angle} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <ListBlock label="Ideal roles" value={opportunity.ideal_roles} />
            <ListBlock label="Industries" value={opportunity.industries} />
            <ListBlock label="Locations" value={opportunity.locations} />
            <ListBlock label="Pain points" value={opportunity.pain_points} />
            <ListBlock label="Search keywords" value={opportunity.search_keywords} />
            <ListBlock label="Lead source ideas" value={opportunity.lead_source_ideas} />
            <ListBlock label="Qualification criteria" value={opportunity.qualification_criteria} />
            <ListBlock label="Risk flags" value={opportunity.risk_flags} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <TextBlock label="Email script" value={opportunity.email_script} />
            <TextBlock label="Call script" value={opportunity.call_script} />
          </div>

          {followUps.length > 0 && (
            <div className="rounded-2xl border line-1 surface-2 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Follow-up sequence</p>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                {followUps.map((step) => (
                  <div key={`${step.step}-${step.purpose}`} className="rounded-xl border line-1 surface-sunk p-3">
                    <p className="text-sm font-semibold text-ink">Step {step.step}: {step.purpose}</p>
                    <p className="mt-2 whitespace-pre-line break-words text-sm leading-6 text-ink-2">{step.message}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-violet-soft bg-violet-soft p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-violet">Suggested campaign</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <TextBlock label="Name" value={opportunity.suggested_campaign_name} />
              <TextBlock label="Industry" value={opportunity.suggested_campaign_industry} />
              <TextBlock label="Location" value={opportunity.suggested_campaign_location} />
              <TextBlock label="Target role" value={opportunity.suggested_campaign_target_role} />
              <TextBlock label="Offer" value={opportunity.suggested_campaign_offer} className="md:col-span-2 xl:col-span-5" />
            </div>
          </div>

          <div className="rounded-2xl border border-info-soft bg-info-soft p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-info">Suggested discovery</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <TextBlock label="Target type" value={opportunity.suggested_discovery_target_type} />
              <TextBlock label="Department/domain" value={opportunity.suggested_discovery_department} />
              <TextBlock label="Role" value={opportunity.suggested_discovery_role} />
              <ListBlock label="Search queries" value={opportunity.suggested_discovery_queries} />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function Opportunities() {
  const navigate = useNavigate();
  const [opportunities, setOpportunities] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [formValues, setFormValues] = useState(emptyForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [generatingId, setGeneratingId] = useState(null);
  const [convertingId, setConvertingId] = useState(null);
  const [creatingDiscoveryJobId, setCreatingDiscoveryJobId] = useState(null);
  const [archivingId, setArchivingId] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const selectedOpportunity = useMemo(
    () => opportunities.find((opportunity) => opportunity.id === selectedId) || opportunities[0] || null,
    [opportunities, selectedId]
  );

  const loadOpportunities = async () => {
    setIsLoading(true);
    setErrorMessage("");

    try {
      const res = await api.get("/opportunities/");
      const data = Array.isArray(res.data.data) ? res.data.data : [];
      setOpportunities(data);
      if (!selectedId && data.length > 0) {
        setSelectedId(data[0].id);
      }
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Could not load opportunities. Please try again."));
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadOpportunities();
    }, 0);

    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateFormValue = (field, value) => {
    setFormValues((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setStatusMessage("");
    setErrorMessage("");

    if (!formValues.title.trim() || !formValues.raw_goal.trim()) {
      setErrorMessage("Title and raw goal are required.");
      return;
    }

    setIsCreating(true);

    try {
      const payload = {
        title: formValues.title.trim(),
        raw_goal: formValues.raw_goal.trim(),
        target_domain: formValues.target_domain.trim() || null,
        target_location: formValues.target_location.trim() || null,
        offer: formValues.offer.trim() || null,
      };
      const res = await api.post("/opportunities/", payload);
      const created = res.data.data;
      setFormValues(emptyForm);
      setSelectedId(created.id);
      setStatusMessage("Opportunity created. Generate a strategy when ready.");
      await loadOpportunities();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Opportunity could not be created. Please try again."));
      console.error(err);
    } finally {
      setIsCreating(false);
    }
  };

  const handleGenerate = async (opportunity) => {
    setGeneratingId(opportunity.id);
    setStatusMessage("");
    setErrorMessage("");

    try {
      const res = await api.post(`/opportunities/${opportunity.id}/generate`, {
        force: true,
      });
      const generated = res.data.data;
      setSelectedId(generated.id);
      setStatusMessage("AI strategy generated successfully.");
      await loadOpportunities();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "AI strategy generation failed. Please try again."));
      console.error(err);
    } finally {
      setGeneratingId(null);
    }
  };

  const handleArchive = async (opportunity) => {
    setArchivingId(opportunity.id);
    setStatusMessage("");
    setErrorMessage("");

    try {
      await api.delete(`/opportunities/${opportunity.id}`);
      setStatusMessage("Opportunity archived.");
      if (selectedId === opportunity.id) {
        setSelectedId(null);
      }
      await loadOpportunities();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Opportunity could not be archived. Please try again."));
      console.error(err);
    } finally {
      setArchivingId(null);
    }
  };

  const handleConvert = async (opportunity) => {
    setConvertingId(opportunity.id);
    setStatusMessage("");
    setErrorMessage("");

    try {
      const res = await api.post(`/opportunities/${opportunity.id}/convert-to-campaign`, {
        force_new: false,
      });
      setStatusMessage(
        res.data.already_converted
          ? `Campaign already exists. Campaign ID: ${res.data.campaign_id}.`
          : `Campaign created successfully. Campaign ID: ${res.data.campaign_id}.`
      );
      await loadOpportunities();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Campaign could not be created from strategy. Please try again."));
      console.error(err);
    } finally {
      setConvertingId(null);
    }
  };

  const handleCreateDiscoveryJob = async (opportunity) => {
    setCreatingDiscoveryJobId(opportunity.id);
    setStatusMessage("");
    setErrorMessage("");

    try {
      const res = await api.post(`/opportunities/${opportunity.id}/create-discovery-job`, {
        campaign_id: opportunity.converted_campaign_id || null,
      });
      const jobId = res.data.discovery_job_id;
      setStatusMessage(`Discovery job created successfully. Job ID: ${jobId}.`);
      navigate(`/discovery?job_id=${jobId}`);
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Discovery job could not be created from strategy. Please try again."));
      console.error(err);
    } finally {
      setCreatingDiscoveryJobId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Opportunities"
        description="Turn a rough outreach idea into a reviewable campaign strategy before creating a campaign."
      />

      <div className="space-y-6">
        <Card>
          <div className="mb-5">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Create Opportunity</h2>
            <p className="mt-1 text-sm text-muted">
              Start with a rough goal. The strategy can target professors, colleges, SMEs, clinics, restaurants, startups, or any other segment.
            </p>
          </div>

          <form className="grid gap-4 lg:grid-cols-2" onSubmit={handleCreate}>
            <label className="text-sm">
              <span className="mb-1 block font-medium text-ink-2">Title</span>
              <input
                type="text"
                value={formValues.title}
                onChange={(e) => updateFormValue("title", e.target.value)}
                className="field"
                placeholder="Professor Research Collaboration"
              />
            </label>

            <label className="text-sm">
              <span className="mb-1 block font-medium text-ink-2">Target domain</span>
              <input
                type="text"
                value={formValues.target_domain}
                onChange={(e) => updateFormValue("target_domain", e.target.value)}
                className="field"
                placeholder="Engineering Colleges / Research"
              />
            </label>

            <label className="text-sm lg:col-span-2">
              <span className="mb-1 block font-medium text-ink-2">Raw goal / idea</span>
              <textarea
                value={formValues.raw_goal}
                onChange={(e) => updateFormValue("raw_goal", e.target.value)}
                className="field min-h-32"
                placeholder="Reach engineering professors for research/project implementation assistance for students."
              />
            </label>

            <label className="text-sm">
              <span className="mb-1 block font-medium text-ink-2">Target location</span>
              <input
                type="text"
                value={formValues.target_location}
                onChange={(e) => updateFormValue("target_location", e.target.value)}
                className="field"
                placeholder="India"
              />
            </label>

            <label className="text-sm">
              <span className="mb-1 block font-medium text-ink-2">Offer</span>
              <input
                type="text"
                value={formValues.offer}
                onChange={(e) => updateFormValue("offer", e.target.value)}
                className="field"
                placeholder="SIP, final-year projects, prototype support, mentorship, documentation"
              />
            </label>

            <div className="lg:col-span-2">
              <Button type="submit" disabled={isCreating}>
                {isCreating ? "Creating..." : "Create Opportunity"}
              </Button>
            </div>
          </form>
        </Card>

        {(statusMessage || errorMessage) && (
          <Card>
            {statusMessage && (
              <p className="rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">
                {statusMessage}
              </p>
            )}
            {errorMessage && (
              <p className="mt-3 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger first:mt-0">
                {errorMessage}
              </p>
            )}
          </Card>
        )}

        <div className="grid gap-6 xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
          <Card>
            <div className="mb-4">
              <h2 className="text-xl font-semibold tracking-tight text-ink">Opportunity List</h2>
              <p className="mt-1 text-sm text-muted">
                {opportunities.length} active opportunities.
              </p>
            </div>

            {isLoading ? (
              <p className="rounded-2xl border line-1 surface-sunk p-4 text-sm text-ink-2">Loading opportunities...</p>
            ) : opportunities.length === 0 ? (
              <p className="rounded-2xl border border-dashed line-1 p-6 text-center text-sm text-muted">
                No opportunities yet.
              </p>
            ) : (
              <div className="space-y-3">
                {opportunities.map((opportunity) => (
                  <article
                    key={opportunity.id}
                    className={[
                      "rounded-2xl border p-4 transition",
                      selectedOpportunity?.id === opportunity.id
                        ? "line-3 surface-sunk"
                        : "line-1 surface-2 hover:surface-2",
                    ].join(" ")}
                  >
                    <button
                      type="button"
                      className="block w-full text-left"
                      onClick={() => setSelectedId(opportunity.id)}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={opportunity.status}>{opportunity.status}</Badge>
                        {opportunity.converted_campaign_id && <Badge variant="success">converted</Badge>}
                      </div>
                      <h3 className="mt-3 break-words text-base font-semibold text-ink">{opportunity.title}</h3>
                      <p className="mt-2 line-clamp-3 break-words text-sm leading-6 text-ink-2">
                        {opportunity.raw_goal}
                      </p>
                      <p className="mt-2 text-xs text-faint">
                        Created: {formatDateTimeIST(opportunity.created_at)}
                      </p>
                    </button>

                    <div className="mt-4 grid gap-2 sm:grid-cols-3">
                      <Button
                        type="button"
                        size="sm"
                        variant="indigo"
                        disabled={generatingId === opportunity.id}
                        onClick={() => handleGenerate(opportunity)}
                      >
                        {generatingId === opportunity.id ? "Generating..." : "Generate Strategy"}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => setSelectedId(opportunity.id)}
                      >
                        View Strategy
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="danger"
                        disabled={archivingId === opportunity.id}
                        onClick={() => handleArchive(opportunity)}
                      >
                        {archivingId === opportunity.id ? "Archiving..." : "Archive"}
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </Card>

          <StrategyView
            opportunity={selectedOpportunity}
            onConvert={handleConvert}
            onCreateDiscoveryJob={handleCreateDiscoveryJob}
            isConverting={Boolean(selectedOpportunity && convertingId === selectedOpportunity.id)}
            isCreatingDiscoveryJob={Boolean(selectedOpportunity && creatingDiscoveryJobId === selectedOpportunity.id)}
          />
        </div>
      </div>
    </div>
  );
}

export default Opportunities;
