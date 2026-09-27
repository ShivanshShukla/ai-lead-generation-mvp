import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../services/api";
import { formatDateTimeIST, getDateTimestampISTSafe } from "../utils/dateUtils";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import PageHeader from "../components/ui/PageHeader";

function formatPercent(value) {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return "0.0%";
  }

  return `${numericValue.toFixed(1)}%`;
}

function getLatestFollowUp(followUps) {
  if (!followUps.length) {
    return null;
  }

  return [...followUps].sort((a, b) => {
    const numberDiff = (b.follow_up_number || 0) - (a.follow_up_number || 0);

    if (numberDiff !== 0) {
      return numberDiff;
    }

    return getDateTimestampISTSafe(b.created_at) - getDateTimestampISTSafe(a.created_at);
  })[0];
}

function getLatestResponseDraft(responseDrafts) {
  if (!responseDrafts.length) {
    return null;
  }

  return [...responseDrafts].sort((a, b) => (
    getDateTimestampISTSafe(b.created_at) - getDateTimestampISTSafe(a.created_at)
  ))[0];
}

function getPreviewText(value, maxLength = 220) {
  const text = String(value || "").trim();

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength).trim()}...`;
}

function getKnowledgeUsedItems(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const match = item.match(/^(.*)\s+\((Manual|Document)\)$/i);

      if (!match) {
        return {
          title: item,
          sourceType: "",
          label: item,
        };
      }

      return {
        title: match[1].trim(),
        sourceType: match[2],
        label: item,
      };
    });
}

function isReplyClassified(draft) {
  return Boolean(draft.reply_intent || draft.reply_classified_at);
}

function Emails() {
  const [searchParams] = useSearchParams();
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState(searchParams.get("campaign_id") || "");
  const selectedDraftId = searchParams.get("draft_id") || "";
  const [isLoadingCampaigns, setIsLoadingCampaigns] = useState(true);
  const [campaignsError, setCampaignsError] = useState("");
  const [drafts, setDrafts] = useState([]);
  const [isLoadingDrafts, setIsLoadingDrafts] = useState(false);
  const [draftsError, setDraftsError] = useState("");
  const [followUps, setFollowUps] = useState([]);
  const [isLoadingFollowUps, setIsLoadingFollowUps] = useState(false);
  const [followUpsError, setFollowUpsError] = useState("");
  const [responseDrafts, setResponseDrafts] = useState([]);
  const [isLoadingResponseDrafts, setIsLoadingResponseDrafts] = useState(false);
  const [responseDraftsError, setResponseDraftsError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isGeneratingFollowUps, setIsGeneratingFollowUps] = useState(false);
  const [generatingFollowUpDraftId, setGeneratingFollowUpDraftId] = useState(null);
  const [isGeneratingResponses, setIsGeneratingResponses] = useState(false);
  const [generatingResponseDraftId, setGeneratingResponseDraftId] = useState(null);
  const [generationError, setGenerationError] = useState("");
  const [generationSummary, setGenerationSummary] = useState(null);
  const [followUpSummary, setFollowUpSummary] = useState(null);
  const [responseDraftSummary, setResponseDraftSummary] = useState(null);
  const [updatingDraftId, setUpdatingDraftId] = useState(null);
  const [updatingFollowUpId, setUpdatingFollowUpId] = useState(null);
  const [updatingResponseDraftId, setUpdatingResponseDraftId] = useState(null);
  const [sendingDraftId, setSendingDraftId] = useState(null);
  const [sendingFollowUpId, setSendingFollowUpId] = useState(null);
  const [sendingResponseDraftId, setSendingResponseDraftId] = useState(null);
  const [isSendingCampaign, setIsSendingCampaign] = useState(false);
  const [isSendingFollowUps, setIsSendingFollowUps] = useState(false);
  const [isSendingResponses, setIsSendingResponses] = useState(false);
  const [sendSummary, setSendSummary] = useState(null);
  const [campaignAnalytics, setCampaignAnalytics] = useState(null);
  const [isLoadingAnalytics, setIsLoadingAnalytics] = useState(false);
  const [analyticsError, setAnalyticsError] = useState("");
  const [isCheckingReplies, setIsCheckingReplies] = useState(false);
  const [checkingReplyDraftId, setCheckingReplyDraftId] = useState(null);
  const [replyCheckSummary, setReplyCheckSummary] = useState(null);
  const [isClassifyingReplies, setIsClassifyingReplies] = useState(false);
  const [classifyingReplyDraftId, setClassifyingReplyDraftId] = useState(null);
  const [replyClassificationSummary, setReplyClassificationSummary] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusError, setStatusError] = useState("");
  const [expandedDraftIds, setExpandedDraftIds] = useState({});
  const [expandedFollowUpIds, setExpandedFollowUpIds] = useState({});
  const [editingDraftId, setEditingDraftId] = useState(null);
  const [draftEditValues, setDraftEditValues] = useState({ subject: "", body: "" });
  const [editingFollowUpId, setEditingFollowUpId] = useState(null);
  const [followUpEditValues, setFollowUpEditValues] = useState({ subject: "", body: "" });
  const [editingResponseDraftId, setEditingResponseDraftId] = useState(null);
  const [responseDraftEditValues, setResponseDraftEditValues] = useState({ subject: "", body: "" });

  const selectedCampaign = useMemo(
    () => campaigns.find((campaign) => String(campaign.id) === String(selectedCampaignId)),
    [campaigns, selectedCampaignId]
  );

  const approvedDraftCount = useMemo(
    () => drafts.filter((draft) => draft.status === "approved").length,
    [drafts]
  );

  const approvedFollowUpCount = useMemo(
    () => followUps.filter((followUp) => followUp.status === "approved").length,
    [followUps]
  );

  const approvedResponseCount = useMemo(
    () => responseDrafts.filter((responseDraft) => responseDraft.status === "approved").length,
    [responseDrafts]
  );

  const followUpsByDraftId = useMemo(() => (
    followUps.reduce((groupedFollowUps, followUp) => {
      const key = String(followUp.original_email_draft_id);

      if (!groupedFollowUps[key]) {
        groupedFollowUps[key] = [];
      }

      groupedFollowUps[key].push(followUp);
      groupedFollowUps[key].sort((a, b) => (
        (a.follow_up_number || 0) - (b.follow_up_number || 0)
      ));

      return groupedFollowUps;
    }, {})
  ), [followUps]);

  const responseDraftsByDraftId = useMemo(() => (
    responseDrafts.reduce((groupedResponseDrafts, responseDraft) => {
      const key = String(responseDraft.original_email_draft_id);

      if (!groupedResponseDrafts[key]) {
        groupedResponseDrafts[key] = [];
      }

      groupedResponseDrafts[key].push(responseDraft);
      groupedResponseDrafts[key].sort((a, b) => (
        getDateTimestampISTSafe(b.created_at) - getDateTimestampISTSafe(a.created_at)
      ));

      return groupedResponseDrafts;
    }, {})
  ), [responseDrafts]);

  const draftSummary = useMemo(() => ({
    total: drafts.length,
    generated: drafts.filter((draft) => draft.status === "generated").length,
    approved: drafts.filter((draft) => draft.status === "approved").length,
    sent: drafts.filter((draft) => draft.status === "sent").length,
    replied: drafts.filter((draft) => draft.status === "replied").length,
    failed: drafts.filter((draft) => draft.status === "failed").length,
  }), [drafts]);

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

  const fetchDrafts = async (campaignId) => {
    if (!campaignId) {
      setDrafts([]);
      return;
    }

    setIsLoadingDrafts(true);
    setDraftsError("");

    try {
      const res = await api.get(`/emails/campaign/${campaignId}`);
      setDrafts(Array.isArray(res.data.data) ? res.data.data : []);
    } catch (err) {
      setDraftsError(getFriendlyErrorMessage(err, "Could not load email drafts. Please try again."));
      console.error(err);
    } finally {
      setIsLoadingDrafts(false);
    }
  };

  const fetchFollowUps = async (campaignId) => {
    if (!campaignId) {
      setFollowUps([]);
      return;
    }

    setIsLoadingFollowUps(true);
    setFollowUpsError("");

    try {
      const res = await api.get(`/followups/campaign/${campaignId}`);
      setFollowUps(Array.isArray(res.data.data) ? res.data.data : []);
    } catch (err) {
      setFollowUpsError(getFriendlyErrorMessage(err, "Could not load follow-up drafts. Please try again."));
      console.error(err);
    } finally {
      setIsLoadingFollowUps(false);
    }
  };

  const fetchResponseDrafts = async (campaignId) => {
    if (!campaignId) {
      setResponseDrafts([]);
      return;
    }

    setIsLoadingResponseDrafts(true);
    setResponseDraftsError("");

    try {
      const res = await api.get(`/reply-responses/campaign/${campaignId}`);
      setResponseDrafts(Array.isArray(res.data.data) ? res.data.data : []);
    } catch (err) {
      setResponseDraftsError(getFriendlyErrorMessage(err, "Could not load response drafts. Please try again.", "response"));
      console.error(err);
    } finally {
      setIsLoadingResponseDrafts(false);
    }
  };

  const fetchCampaignAnalytics = async (campaignId) => {
    if (!campaignId) {
      setCampaignAnalytics(null);
      return;
    }

    setIsLoadingAnalytics(true);
    setAnalyticsError("");

    try {
      const res = await api.get(`/analytics/campaign/${campaignId}`);
      setCampaignAnalytics(res.data.data || null);
    } catch (err) {
      setAnalyticsError(getFriendlyErrorMessage(err, "Could not load campaign analytics. Please try again."));
      console.error(err);
    } finally {
      setIsLoadingAnalytics(false);
    }
  };

  const refreshCampaignData = async (campaignId) => {
    await Promise.all([
      fetchDrafts(campaignId),
      fetchFollowUps(campaignId),
      fetchResponseDrafts(campaignId),
      fetchCampaignAnalytics(campaignId),
    ]);
  };

  useEffect(() => {
    if (!selectedCampaignId) {
      return;
    }

    const loadSelectedCampaignData = async () => {
      await Promise.all([
        fetchDrafts(selectedCampaignId),
        fetchFollowUps(selectedCampaignId),
        fetchResponseDrafts(selectedCampaignId),
        fetchCampaignAnalytics(selectedCampaignId),
      ]);
    };

    loadSelectedCampaignData();
  }, [selectedCampaignId]);

  const handleCampaignChange = (e) => {
    const nextCampaignId = e.target.value;

    setSelectedCampaignId(nextCampaignId);
    setDrafts([]);
    setFollowUps([]);
    setResponseDrafts([]);
    setCampaignAnalytics(null);
    setDraftsError("");
    setFollowUpsError("");
    setResponseDraftsError("");
    setAnalyticsError("");
    setGenerationSummary(null);
    setGenerationError("");
    setSendSummary(null);
    setFollowUpSummary(null);
    setResponseDraftSummary(null);
    setReplyCheckSummary(null);
    setReplyClassificationSummary(null);
    setStatusMessage("");
    setStatusError("");
    setExpandedDraftIds({});
    setExpandedFollowUpIds({});
    setEditingDraftId(null);
    setEditingFollowUpId(null);
    setEditingResponseDraftId(null);
  };

  const toggleDraftExpanded = (draftId) => {
    setExpandedDraftIds((current) => ({
      ...current,
      [draftId]: !current[draftId],
    }));
  };

  const toggleFollowUpExpanded = (followUpId) => {
    setExpandedFollowUpIds((current) => ({
      ...current,
      [followUpId]: !current[followUpId],
    }));
  };

  const startDraftEdit = (draft) => {
    setEditingDraftId(draft.id);
    setDraftEditValues({
      subject: draft.subject || "",
      body: draft.body || "",
    });
    setStatusMessage("");
    setStatusError("");
  };

  const cancelDraftEdit = () => {
    setEditingDraftId(null);
    setDraftEditValues({ subject: "", body: "" });
  };

  const startFollowUpEdit = (followUp) => {
    setEditingFollowUpId(followUp.id);
    setFollowUpEditValues({
      subject: followUp.subject || "",
      body: followUp.body || "",
    });
    setStatusMessage("");
    setStatusError("");
  };

  const cancelFollowUpEdit = () => {
    setEditingFollowUpId(null);
    setFollowUpEditValues({ subject: "", body: "" });
  };

  const startResponseDraftEdit = (responseDraft) => {
    setEditingResponseDraftId(responseDraft.id);
    setResponseDraftEditValues({
      subject: responseDraft.subject || "",
      body: responseDraft.body || "",
    });
    setStatusMessage("");
    setStatusError("");
  };

  const cancelResponseDraftEdit = () => {
    setEditingResponseDraftId(null);
    setResponseDraftEditValues({ subject: "", body: "" });
  };

  const validateDraftEditValues = ({ subject, body }) => {
    return Boolean(String(subject || "").trim() && String(body || "").trim());
  };

  const handleGenerateCampaignEmails = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsGenerating(true);
    setGenerationError("");
    setGenerationSummary(null);
    setFollowUpSummary(null);
    setResponseDraftSummary(null);
    setSendSummary(null);
    setReplyClassificationSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/ai/generate-emails/campaign/${selectedCampaignId}?limit=5`);
      setGenerationSummary({
        generated: res.data.generated ?? 0,
        skipped: res.data.skipped ?? 0,
        failed: res.data.failed ?? 0,
        remaining: res.data.remaining ?? 0,
      });
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setGenerationError(getFriendlyErrorMessage(err, "AI generation failed. Please check Gemini API key or try again.", "ai"));
      console.error(err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleUpdateStatus = async (emailId, nextStatus) => {
    setUpdatingDraftId(emailId);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.patch(`/emails/${emailId}/status`, {
        status: nextStatus,
      });
      const updatedDraft = res.data.data;

      setDrafts((currentDrafts) =>
        currentDrafts.map((draft) => (
          draft.id === emailId ? updatedDraft : draft
        ))
      );
      setStatusMessage("Email status updated successfully.");
      await fetchCampaignAnalytics(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Something went wrong. Please try again."));
      console.error(err);
    } finally {
      setUpdatingDraftId(null);
    }
  };

  const handleSaveDraftEdit = async (emailId) => {
    if (!validateDraftEditValues(draftEditValues)) {
      setStatusError("Subject and body are required.");
      return;
    }

    setUpdatingDraftId(emailId);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.patch(`/emails/${emailId}`, {
        subject: draftEditValues.subject,
        body: draftEditValues.body,
      });
      const updatedDraft = res.data.data;

      setDrafts((currentDrafts) =>
        currentDrafts.map((draft) => (
          draft.id === emailId ? updatedDraft : draft
        ))
      );
      cancelDraftEdit();
      setStatusMessage("Email draft updated successfully. Editing an approved draft requires approval again before sending.");
      await fetchCampaignAnalytics(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Failed to update draft. Please try again.", "draft-edit"));
      console.error(err);
    } finally {
      setUpdatingDraftId(null);
    }
  };

  const handleSendDraft = async (emailId) => {
    setSendingDraftId(emailId);
    setSendSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/gmail/send-draft/${emailId}`);
      const result = res.data.data;

      if (result?.status === "sent") {
        setStatusMessage("Email sent successfully.");
      } else {
        setStatusError(
          result?.error === "Lead email is missing."
            ? "This lead does not have an email address."
            : result?.error || "Something went wrong. Please try again."
        );
      }

      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Something went wrong. Please try again.", "gmail"));
      console.error(err);
    } finally {
      setSendingDraftId(null);
    }
  };

  const handleSendApprovedCampaignEmails = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsSendingCampaign(true);
    setSendSummary(null);
    setFollowUpSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/gmail/send-approved/campaign/${selectedCampaignId}?limit=5`);
      setSendSummary({
        sent: res.data.sent ?? 0,
        failed: res.data.failed ?? 0,
        remainingApproved: res.data.remaining_approved ?? 0,
      });
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Something went wrong. Please try again.", "gmail"));
      console.error(err);
    } finally {
      setIsSendingCampaign(false);
    }
  };

  const handleCheckCampaignReplies = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsCheckingReplies(true);
    setReplyCheckSummary(null);
    setReplyClassificationSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/replies/check-campaign/${selectedCampaignId}?limit=5`);
      setReplyCheckSummary({
        processed: res.data.processed ?? 0,
        replied: res.data.replied ?? 0,
        noReply: res.data.no_reply ?? 0,
        failed: res.data.failed ?? 0,
      });
      setStatusMessage("Reply check completed.");
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Reply check failed. Please try again.", "reply"));
      console.error(err);
    } finally {
      setIsCheckingReplies(false);
    }
  };

  const handleCheckDraftReply = async (emailId) => {
    setCheckingReplyDraftId(emailId);
    setReplyCheckSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/replies/check-draft/${emailId}`);

      if (res.data.replied) {
        setStatusMessage("Reply found for this email.");
      } else {
        setStatusMessage("No reply found for this email yet.");
      }

      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Reply check failed. Please try again.", "reply"));
      console.error(err);
    } finally {
      setCheckingReplyDraftId(null);
    }
  };

  const handleClassifyCampaignReplies = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsClassifyingReplies(true);
    setReplyClassificationSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/reply-classification/classify-campaign/${selectedCampaignId}?limit=5`);
      setReplyClassificationSummary({
        processed: res.data.processed ?? 0,
        classified: res.data.classified ?? 0,
        skipped: res.data.skipped ?? 0,
        failed: res.data.failed ?? 0,
        remaining: res.data.remaining_unclassified ?? 0,
      });
      setStatusMessage("Reply classification completed.");
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Reply classification failed. Please try again.", "classification"));
      console.error(err);
    } finally {
      setIsClassifyingReplies(false);
    }
  };

  const handleClassifyDraftReply = async (emailId, force = false) => {
    setClassifyingReplyDraftId(emailId);
    setReplyClassificationSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      await api.post(`/reply-classification/classify/${emailId}?force=${force ? "true" : "false"}`);
      setStatusMessage(force ? "Reply reclassified successfully." : "Reply classified successfully.");
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Reply classification failed. Please try again.", "classification"));
      console.error(err);
    } finally {
      setClassifyingReplyDraftId(null);
    }
  };

  const handleGenerateFollowUp = async (emailId) => {
    setGeneratingFollowUpDraftId(emailId);
    setFollowUpSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/followups/generate/${emailId}`);
      setStatusMessage(res.data.message || "Follow-up draft generated.");
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Follow-up generation failed. Please try again.", "followup"));
      console.error(err);
    } finally {
      setGeneratingFollowUpDraftId(null);
    }
  };

  const handleGenerateCampaignFollowUps = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsGeneratingFollowUps(true);
    setFollowUpSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/followups/generate-campaign/${selectedCampaignId}?limit=5`);
      setFollowUpSummary({
        mode: "generated",
        processed: res.data.processed ?? 0,
        generated: res.data.generated ?? 0,
        skipped: res.data.skipped ?? 0,
        failed: res.data.failed ?? 0,
        remaining: res.data.remaining ?? 0,
      });
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Follow-up generation failed. Please try again.", "followup"));
      console.error(err);
    } finally {
      setIsGeneratingFollowUps(false);
    }
  };

  const handleUpdateFollowUpStatus = async (followUpId, nextStatus) => {
    setUpdatingFollowUpId(followUpId);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.patch(`/followups/${followUpId}/status`, {
        status: nextStatus,
      });
      const updatedFollowUp = res.data.data;

      setFollowUps((currentFollowUps) =>
        currentFollowUps.map((followUp) => (
          followUp.id === followUpId ? updatedFollowUp : followUp
        ))
      );
      setStatusMessage("Follow-up status updated successfully.");
      await fetchCampaignAnalytics(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Something went wrong. Please try again.", "followup"));
      console.error(err);
    } finally {
      setUpdatingFollowUpId(null);
    }
  };

  const handleSaveFollowUpEdit = async (followUpId) => {
    if (!validateDraftEditValues(followUpEditValues)) {
      setStatusError("Subject and body are required.");
      return;
    }

    setUpdatingFollowUpId(followUpId);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.patch(`/followups/${followUpId}`, {
        subject: followUpEditValues.subject,
        body: followUpEditValues.body,
      });
      const updatedFollowUp = res.data.data;

      setFollowUps((currentFollowUps) =>
        currentFollowUps.map((followUp) => (
          followUp.id === followUpId ? updatedFollowUp : followUp
        ))
      );
      cancelFollowUpEdit();
      setStatusMessage("Follow-up draft updated successfully. Editing an approved draft requires approval again before sending.");
      await fetchCampaignAnalytics(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Failed to update draft. Please try again.", "draft-edit"));
      console.error(err);
    } finally {
      setUpdatingFollowUpId(null);
    }
  };

  const handleSendFollowUp = async (followUpId) => {
    setSendingFollowUpId(followUpId);
    setFollowUpSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/followups/send/${followUpId}`);
      const result = res.data.data;

      if (result?.status === "sent") {
        setStatusMessage("Follow-up sent successfully.");
      } else {
        setStatusError(result?.send_error || "Follow-up sending failed. Please try again.");
      }

      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Follow-up sending failed. Please try again.", "followup"));
      console.error(err);
    } finally {
      setSendingFollowUpId(null);
    }
  };

  const handleSendApprovedCampaignFollowUps = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsSendingFollowUps(true);
    setFollowUpSummary(null);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/followups/send-approved/campaign/${selectedCampaignId}?limit=5`);
      setFollowUpSummary({
        mode: "sent",
        sent: res.data.sent ?? 0,
        failed: res.data.failed ?? 0,
        skipped: res.data.skipped ?? 0,
        remainingApproved: res.data.remaining_approved ?? 0,
      });
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Follow-up sending failed. Please try again.", "followup"));
      console.error(err);
    } finally {
      setIsSendingFollowUps(false);
    }
  };

  const handleGenerateResponseDraft = async (emailId, force = false) => {
    setGeneratingResponseDraftId(emailId);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/reply-responses/generate/${emailId}?force=${force ? "true" : "false"}`);
      setStatusMessage(res.data.message || "Response draft generated.");
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Response draft generation failed. Please try again.", "response"));
      console.error(err);
    } finally {
      setGeneratingResponseDraftId(null);
    }
  };

  const handleGenerateCampaignResponses = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsGeneratingResponses(true);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/reply-responses/generate-campaign/${selectedCampaignId}?limit=5`);
      setResponseDraftSummary({
        mode: "generated",
        processed: res.data.processed ?? 0,
        generated: res.data.generated ?? 0,
        skipped: res.data.skipped ?? 0,
        failed: res.data.failed ?? 0,
        remaining: res.data.remaining ?? 0,
      });
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Response draft generation failed. Please try again.", "response"));
      console.error(err);
    } finally {
      setIsGeneratingResponses(false);
    }
  };

  const handleUpdateResponseStatus = async (responseDraftId, nextStatus) => {
    setUpdatingResponseDraftId(responseDraftId);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.patch(`/reply-responses/${responseDraftId}/status`, {
        status: nextStatus,
      });
      const updatedResponseDraft = res.data.data;

      setResponseDrafts((currentResponseDrafts) =>
        currentResponseDrafts.map((responseDraft) => (
          responseDraft.id === responseDraftId ? updatedResponseDraft : responseDraft
        ))
      );
      setStatusMessage("Response draft status updated successfully.");
      await fetchCampaignAnalytics(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Response draft status could not be updated.", "response"));
      console.error(err);
    } finally {
      setUpdatingResponseDraftId(null);
    }
  };

  const handleSaveResponseDraftEdit = async (responseDraftId) => {
    if (!validateDraftEditValues(responseDraftEditValues)) {
      setStatusError("Subject and body are required.");
      return;
    }

    setUpdatingResponseDraftId(responseDraftId);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.patch(`/reply-responses/${responseDraftId}`, {
        subject: responseDraftEditValues.subject,
        body: responseDraftEditValues.body,
      });
      const updatedResponseDraft = res.data.data;

      setResponseDrafts((currentResponseDrafts) =>
        currentResponseDrafts.map((responseDraft) => (
          responseDraft.id === responseDraftId ? updatedResponseDraft : responseDraft
        ))
      );
      cancelResponseDraftEdit();
      setStatusMessage("Response draft updated successfully. Editing an approved draft requires approval again before sending.");
      await fetchCampaignAnalytics(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Failed to update draft. Please try again.", "draft-edit"));
      console.error(err);
    } finally {
      setUpdatingResponseDraftId(null);
    }
  };

  const handleSendResponseDraft = async (responseDraftId) => {
    setSendingResponseDraftId(responseDraftId);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/reply-responses/send/${responseDraftId}`);
      const result = res.data.data;

      if (result?.status === "sent") {
        setStatusMessage("Response draft sent successfully.");
      } else {
        setStatusError(result?.send_error || "Response sending failed. Please try again.");
      }

      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Response sending failed. Please try again.", "response"));
      console.error(err);
    } finally {
      setSendingResponseDraftId(null);
    }
  };

  const handleSendApprovedCampaignResponses = async () => {
    if (!selectedCampaignId) {
      return;
    }

    setIsSendingResponses(true);
    setResponseDraftSummary(null);
    setStatusMessage("");
    setStatusError("");

    try {
      const res = await api.post(`/reply-responses/send-approved/campaign/${selectedCampaignId}?limit=5`);
      setResponseDraftSummary({
        mode: "sent",
        sent: res.data.sent ?? 0,
        failed: res.data.failed ?? 0,
        skipped: res.data.skipped ?? 0,
        remainingApproved: res.data.remaining_approved ?? 0,
      });
      await refreshCampaignData(selectedCampaignId);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Response sending failed. Please try again.", "response"));
      console.error(err);
    } finally {
      setIsSendingResponses(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Emails"
        description="Generate, approve, send, check replies, and manage follow-ups from one focused workspace."
      />

      <div className="space-y-6">
        <div className="rounded-3xl border line-1 surface-2 p-5 elev-1 backdrop-blur sm:p-6">
          <div className="mb-4">
            <h2 className="text-xl font-semibold">Select Campaign</h2>
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
        </div>

        {selectedCampaign && (
          <div className="rounded-3xl border line-1 surface-2 p-5 elev-1 backdrop-blur sm:p-6">
            <div className="mb-4">
              <h2 className="text-xl font-semibold">Campaign Summary</h2>
              <p className="text-sm text-muted mt-1">{selectedCampaign.campaign_name}</p>
            </div>

            <div className="grid grid-cols-2 gap-4 md:grid-cols-6">
              <div className="rounded-lg border surface-sunk p-4">
                <p className="text-xs text-muted">Total Drafts</p>
                <p className="mt-1 text-2xl font-semibold text-ink">{draftSummary.total}</p>
              </div>
              <div className="rounded-lg border bg-info-soft p-4">
                <p className="text-xs text-info">Generated</p>
                <p className="mt-1 text-2xl font-semibold text-info">{draftSummary.generated}</p>
              </div>
              <div className="rounded-lg border bg-success-soft p-4">
                <p className="text-xs text-success">Approved</p>
                <p className="mt-1 text-2xl font-semibold text-success">{draftSummary.approved}</p>
              </div>
              <div className="rounded-lg border bg-violet-soft p-4">
                <p className="text-xs text-violet">Sent</p>
                <p className="mt-1 text-2xl font-semibold text-violet">{draftSummary.sent}</p>
              </div>
              <div className="rounded-lg border bg-success-soft p-4">
                <p className="text-xs text-success">Replied</p>
                <p className="mt-1 text-2xl font-semibold text-success">{draftSummary.replied}</p>
              </div>
              <div className="rounded-lg border bg-danger-soft p-4">
                <p className="text-xs text-danger">Failed</p>
                <p className="mt-1 text-2xl font-semibold text-danger">{draftSummary.failed}</p>
              </div>
            </div>
          </div>
        )}

        {selectedCampaign && (
          <div className="rounded-3xl border line-1 surface-2 p-5 elev-1 backdrop-blur sm:p-6">
            <div className="mb-4">
              <h2 className="text-xl font-semibold">Campaign Analytics</h2>
              <p className="text-sm text-muted mt-1">
                Reply tracking uses Gmail readonly access and does not send emails.
              </p>
            </div>

            {isLoadingAnalytics && (
              <div className="rounded-lg border surface-sunk p-4 text-sm text-ink-2">
                Loading campaign analytics...
              </div>
            )}

            {!isLoadingAnalytics && analyticsError && (
              <div className="rounded-lg border border-danger-soft bg-danger-soft p-4 text-sm text-danger">
                {analyticsError}
              </div>
            )}

            {!isLoadingAnalytics && !analyticsError && campaignAnalytics && (
              <div className="space-y-5">
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                  <div className="rounded-lg border surface-sunk p-4">
                    <p className="text-xs text-muted">Leads</p>
                    <p className="mt-1 text-2xl font-semibold text-ink">{campaignAnalytics.lead_count}</p>
                  </div>
                  <div className="rounded-lg border surface-sunk p-4">
                    <p className="text-xs text-muted">Drafts</p>
                    <p className="mt-1 text-2xl font-semibold text-ink">{campaignAnalytics.draft_count}</p>
                  </div>
                  <div className="rounded-lg border bg-violet-soft p-4">
                    <p className="text-xs text-violet">Sent</p>
                    <p className="mt-1 text-2xl font-semibold text-violet">{campaignAnalytics.sent_count}</p>
                  </div>
                  <div className="rounded-lg border bg-danger-soft p-4">
                    <p className="text-xs text-danger">Failed</p>
                    <p className="mt-1 text-2xl font-semibold text-danger">{campaignAnalytics.failed_count}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">Replied</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{campaignAnalytics.replied_count}</p>
                  </div>
                  <div className="rounded-lg border bg-info-soft p-4">
                    <p className="text-xs text-info">Classified Replies</p>
                    <p className="mt-1 text-2xl font-semibold text-info">{campaignAnalytics.classified_replies ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-danger-soft p-4">
                    <p className="text-xs text-danger">High Priority Replies</p>
                    <p className="mt-1 text-2xl font-semibold text-danger">{campaignAnalytics.high_priority_replies ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">Interested</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{campaignAnalytics.interested_replies ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-info-soft p-4">
                    <p className="text-xs text-info">Pricing</p>
                    <p className="mt-1 text-2xl font-semibold text-info">{campaignAnalytics.pricing_replies ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">Meeting Requests</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{campaignAnalytics.meeting_request_replies ?? 0}</p>
                  </div>
                  <div className="rounded-lg border surface-sunk p-4">
                    <p className="text-xs text-ink-2">Not Interested</p>
                    <p className="mt-1 text-2xl font-semibold text-ink">{campaignAnalytics.not_interested_replies ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-danger-soft p-4">
                    <p className="text-xs text-danger">Unsubscribe</p>
                    <p className="mt-1 text-2xl font-semibold text-danger">{campaignAnalytics.unsubscribe_replies ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-info-soft p-4">
                    <p className="text-xs text-info">Reply Rate</p>
                    <p className="mt-1 text-2xl font-semibold text-info">{formatPercent(campaignAnalytics.reply_rate)}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">Send Success</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{formatPercent(campaignAnalytics.send_success_rate)}</p>
                  </div>
                  <div className="rounded-lg border bg-warn-soft p-4">
                    <p className="text-xs text-warn">Needs Follow-up</p>
                    <p className="mt-1 text-2xl font-semibold text-warn">{campaignAnalytics.needs_follow_up_count}</p>
                  </div>
                  <div className="rounded-lg border bg-info-soft p-4">
                    <p className="text-xs text-info">Follow-ups Generated</p>
                    <p className="mt-1 text-2xl font-semibold text-info">{campaignAnalytics.followups_generated_count ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">Follow-ups Approved</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{campaignAnalytics.followups_approved_count ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-violet-soft p-4">
                    <p className="text-xs text-violet">Follow-ups Sent</p>
                    <p className="mt-1 text-2xl font-semibold text-violet">{campaignAnalytics.followups_sent_count ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-danger-soft p-4">
                    <p className="text-xs text-danger">Follow-ups Failed</p>
                    <p className="mt-1 text-2xl font-semibold text-danger">{campaignAnalytics.followups_failed_count ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-info-soft p-4">
                    <p className="text-xs text-info">Responses Generated</p>
                    <p className="mt-1 text-2xl font-semibold text-info">{campaignAnalytics.response_drafts_generated ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">Responses Approved</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{campaignAnalytics.response_drafts_approved ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-violet-soft p-4">
                    <p className="text-xs text-violet">Responses Sent</p>
                    <p className="mt-1 text-2xl font-semibold text-violet">{campaignAnalytics.response_drafts_sent ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-danger-soft p-4">
                    <p className="text-xs text-danger">Responses Failed</p>
                    <p className="mt-1 text-2xl font-semibold text-danger">{campaignAnalytics.response_drafts_failed ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-violet-soft p-4">
                    <p className="text-xs text-violet">AI Scored Leads</p>
                    <p className="mt-1 text-2xl font-semibold text-violet">{campaignAnalytics.scored_leads ?? 0}</p>
                  </div>
                  <div className="rounded-lg border surface-sunk p-4">
                    <p className="text-xs text-muted">Unscored Leads</p>
                    <p className="mt-1 text-2xl font-semibold text-ink">{campaignAnalytics.unscored_leads ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-violet-soft p-4">
                    <p className="text-xs text-violet">Avg AI Score</p>
                    <p className="mt-1 text-2xl font-semibold text-violet">{Number(campaignAnalytics.average_ai_score ?? 0).toFixed(1)}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">High Priority</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{campaignAnalytics.high_priority_leads ?? 0}</p>
                  </div>
                  <div className="rounded-lg border bg-success-soft p-4">
                    <p className="text-xs text-success">Hot Leads</p>
                    <p className="mt-1 text-2xl font-semibold text-success">{campaignAnalytics.hot_leads ?? 0}</p>
                  </div>
                </div>

                {campaignAnalytics.recent_replies?.length > 0 && (
                  <div className="rounded-lg border surface-sunk p-4">
                    <h3 className="text-sm font-semibold text-ink">Recent Replies</h3>
                    <div className="mt-3 space-y-3">
                      {campaignAnalytics.recent_replies.map((reply) => (
                        <div key={reply.email_draft_id} className="border-t pt-3 first:border-t-0 first:pt-0">
                          <p className="text-sm font-medium text-ink">
                            {reply.company_name || reply.lead_email || `Lead ID ${reply.lead_id}`}
                          </p>
                          <p className="mt-1 text-xs text-muted">
                            {[reply.lead_email, formatDateTimeIST(reply.replied_at)].filter(Boolean).join(" | ")}
                          </p>
                          {(reply.reply_intent || reply.reply_priority || reply.reply_sentiment) && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {reply.reply_intent && <Badge variant={reply.reply_intent}>{reply.reply_intent}</Badge>}
                              {reply.reply_sentiment && <Badge variant={reply.reply_sentiment}>{reply.reply_sentiment}</Badge>}
                              {reply.reply_priority && <Badge variant={reply.reply_priority}>{reply.reply_priority}</Badge>}
                            </div>
                          )}
                          {reply.reply_snippet && (
                            <p className="mt-2 text-sm text-ink-2">{reply.reply_snippet}</p>
                          )}
                          {reply.reply_next_action && (
                            <p className="mt-2 text-sm font-medium text-ink-2">Next: {reply.reply_next_action}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="rounded-3xl border line-1 surface-2 p-5 elev-1 backdrop-blur sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-ink">Outreach Actions</h2>
              {selectedCampaign && (
                <p className="mt-1 text-sm text-muted">
                  {selectedCampaign.campaign_name}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
              <Button
                type="button"
                variant="primary"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isGenerating || isSendingCampaign || isGeneratingFollowUps || isGeneratingResponses}
                onClick={handleGenerateCampaignEmails}
              >
                {isGenerating ? "Generating emails..." : "Generate Next 5 Emails"}
              </Button>

              <Button
                type="button"
                variant="indigo"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isSendingCampaign || approvedDraftCount === 0}
                onClick={handleSendApprovedCampaignEmails}
              >
                {isSendingCampaign ? "Sending approved emails..." : "Send Approved Emails"}
              </Button>

              <Button
                type="button"
                variant="success"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isCheckingReplies || isClassifyingReplies || isSendingCampaign || isGenerating || isGeneratingFollowUps || isGeneratingResponses}
                onClick={handleCheckCampaignReplies}
              >
                {isCheckingReplies ? "Checking replies..." : "Check Replies"}
              </Button>

              <Button
                type="button"
                variant="warning"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isClassifyingReplies || isCheckingReplies || isSendingCampaign || isGenerating || isGeneratingFollowUps || isGeneratingResponses}
                onClick={handleClassifyCampaignReplies}
              >
                {isClassifyingReplies ? "Classifying replies..." : "Classify Replies"}
              </Button>

              <Button
                type="button"
                variant="indigo"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isGeneratingResponses || isSendingResponses || isClassifyingReplies || isCheckingReplies}
                onClick={handleGenerateCampaignResponses}
              >
                {isGeneratingResponses ? "Generating responses..." : "Generate Response Drafts"}
              </Button>

              <Button
                type="button"
                variant="secondary"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isSendingResponses || approvedResponseCount === 0}
                onClick={handleSendApprovedCampaignResponses}
              >
                {isSendingResponses ? "Sending responses..." : "Send Approved Responses"}
              </Button>

              <Button
                type="button"
                variant="secondary"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isGeneratingFollowUps || isGenerating || isSendingFollowUps}
                onClick={handleGenerateCampaignFollowUps}
              >
                {isGeneratingFollowUps ? "Generating follow-ups..." : "Generate Follow-ups"}
              </Button>

              <Button
                type="button"
                variant="secondary"
                className="w-full sm:w-auto"
                disabled={!selectedCampaignId || isSendingFollowUps || approvedFollowUpCount === 0}
                onClick={handleSendApprovedCampaignFollowUps}
              >
                {isSendingFollowUps ? "Sending follow-ups..." : "Send Approved Follow-ups"}
              </Button>
            </div>
          </div>

          <p className="mt-3 text-sm text-muted">
            For safety, only 5 leads are processed per click.
          </p>
          <p className="mt-1 text-sm text-muted">
            Only approved drafts are sent. Sending is limited to 5 per click.
          </p>
          <p className="mt-1 text-sm text-muted">
            Reply checking uses Gmail readonly access and does not send emails.
          </p>
          <p className="mt-1 text-sm text-muted">
            AI reply classification only suggests next actions. It does not send replies automatically.
          </p>
          <p className="mt-1 text-sm text-muted">
            AI response drafts are not sent automatically. Approve before sending. Do not include pricing unless verified.
          </p>
          <p className="mt-1 text-sm text-muted">
            AI uses saved company knowledge when relevant. Review before sending.
          </p>
          <p className="mt-1 text-sm text-muted">
            Follow-ups are generated only for sent emails without replies.
          </p>
          <p className="mt-1 text-sm text-muted">
            Follow-ups are never sent automatically. Only approved follow-ups can be sent.
          </p>

          {generationSummary && (
            <p className="mt-4 rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">
              Generated: {generationSummary.generated}, Skipped: {generationSummary.skipped}, Failed: {generationSummary.failed}, Remaining: {generationSummary.remaining}
            </p>
          )}

          {generationError && (
            <p className="mt-4 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
              {generationError}
            </p>
          )}

          {sendSummary && (
            <p className="mt-4 rounded-lg border border-violet-soft bg-violet-soft p-3 text-sm text-violet">
              Sent: {sendSummary.sent}, Failed: {sendSummary.failed}, Remaining approved: {sendSummary.remainingApproved}
            </p>
          )}

          {replyCheckSummary && (
            <p className="mt-4 rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">
              Checked: {replyCheckSummary.processed}, Replies found: {replyCheckSummary.replied}, No reply: {replyCheckSummary.noReply}, Failed: {replyCheckSummary.failed}
            </p>
          )}

          {replyClassificationSummary && (
            <p className="mt-4 rounded-lg border border-warn-soft bg-warn-soft p-3 text-sm text-warn">
              Classified {replyClassificationSummary.classified} replies, skipped {replyClassificationSummary.skipped}, failed {replyClassificationSummary.failed}. Remaining: {replyClassificationSummary.remaining}.
            </p>
          )}

          {followUpSummary?.mode === "generated" && (
            <p className="mt-4 rounded-lg border border-violet-soft bg-violet-soft p-3 text-sm text-violet">
              Processed: {followUpSummary.processed}, Generated: {followUpSummary.generated}, Skipped: {followUpSummary.skipped}, Failed: {followUpSummary.failed}, Remaining: {followUpSummary.remaining}
            </p>
          )}

          {followUpSummary?.mode === "sent" && (
            <p className="mt-4 rounded-lg border line-1 surface-sunk p-3 text-sm text-ink-2">
              Follow-ups sent: {followUpSummary.sent}, Failed: {followUpSummary.failed}, Skipped: {followUpSummary.skipped}, Remaining approved: {followUpSummary.remainingApproved}
            </p>
          )}

          {responseDraftSummary?.mode === "generated" && (
            <p className="mt-4 rounded-lg border border-info-soft bg-info-soft p-3 text-sm text-info">
              Responses processed: {responseDraftSummary.processed}, Generated: {responseDraftSummary.generated}, Skipped: {responseDraftSummary.skipped}, Failed: {responseDraftSummary.failed}, Remaining: {responseDraftSummary.remaining}
            </p>
          )}

          {responseDraftSummary?.mode === "sent" && (
            <p className="mt-4 rounded-lg border line-1 surface-sunk p-3 text-sm text-ink-2">
              Responses sent: {responseDraftSummary.sent}, Failed: {responseDraftSummary.failed}, Skipped: {responseDraftSummary.skipped}, Remaining approved: {responseDraftSummary.remainingApproved}
            </p>
          )}
        </div>

        {(statusMessage || statusError) && (
          <div className="rounded-3xl border line-1 surface-2 p-5 elev-1 backdrop-blur sm:p-6">
            {statusMessage && (
              <p className="rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">
                {statusMessage}
              </p>
            )}

            {statusError && (
              <p className="rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
                {statusError}
              </p>
            )}
          </div>
        )}

        <div className="rounded-3xl border line-1 surface-2 p-5 elev-1 backdrop-blur sm:p-6">
          <div className="mb-4">
            <h2 className="text-xl font-semibold">Email Drafts</h2>
          </div>

          {!selectedCampaignId && (
            <div className="border border-dashed rounded-lg p-6 text-center">
              <h3 className="font-medium text-ink">Select a campaign</h3>
              <p className="text-sm text-muted mt-1">
                Select a campaign to generate and manage email drafts.
              </p>
            </div>
          )}

          {selectedCampaignId && isLoadingDrafts && (
            <div className="border rounded-lg p-5 text-sm text-ink-2">
              Loading email drafts...
            </div>
          )}

          {selectedCampaignId && !isLoadingDrafts && isLoadingFollowUps && (
            <div className="mb-4 border rounded-lg p-4 text-sm text-ink-2">
              Loading follow-up drafts...
            </div>
          )}

          {selectedCampaignId && !isLoadingDrafts && isLoadingResponseDrafts && (
            <div className="mb-4 border rounded-lg p-4 text-sm text-ink-2">
              Loading response drafts...
            </div>
          )}

          {selectedCampaignId && !isLoadingDrafts && draftsError && (
            <div className="border border-danger-soft bg-danger-soft text-danger rounded-lg p-4 text-sm">
              {draftsError}
            </div>
          )}

          {selectedCampaignId && !isLoadingDrafts && !draftsError && followUpsError && (
            <div className="mb-4 border border-danger-soft bg-danger-soft text-danger rounded-lg p-4 text-sm">
              {followUpsError}
            </div>
          )}

          {selectedCampaignId && !isLoadingDrafts && !draftsError && responseDraftsError && (
            <div className="mb-4 border border-danger-soft bg-danger-soft text-danger rounded-lg p-4 text-sm">
              {responseDraftsError}
            </div>
          )}

          {selectedCampaignId && !isLoadingDrafts && !draftsError && drafts.length === 0 && (
            <div className="border border-dashed rounded-lg p-6 text-center">
              <h3 className="font-medium text-ink">No email drafts found.</h3>
              <p className="text-sm text-muted mt-1">
                Generate AI drafts for this campaign.
              </p>
            </div>
          )}

          {selectedCampaignId && !isLoadingDrafts && !draftsError && drafts.length > 0 && (
            <div className="space-y-4">
              {drafts.map((draft) => {
                const draftFollowUps = followUpsByDraftId[String(draft.id)] || [];
                const draftResponseDrafts = responseDraftsByDraftId[String(draft.id)] || [];
                const latestResponseDraft = getLatestResponseDraft(draftResponseDrafts);
                const knowledgeUsedItems = getKnowledgeUsedItems(latestResponseDraft?.knowledge_used);
                const isEditingResponseDraft = latestResponseDraft && editingResponseDraftId === latestResponseDraft.id;
                const latestFollowUp = getLatestFollowUp(draftFollowUps);
                const canGenerateFollowUp = (
                  draft.status === "sent" &&
                  draftFollowUps.length < 2 &&
                  (!latestFollowUp || latestFollowUp.status === "sent")
                );
                const replyClassified = isReplyClassified(draft);
                const canGenerateResponseDraft = (
                  draft.status === "replied" &&
                  replyClassified
                );
                const isDraftExpanded = Boolean(expandedDraftIds[draft.id]);
                const shouldCollapseDraft = String(draft.body || "").length > 220;
                const isEditingDraft = editingDraftId === draft.id;
                const canEditDraft = ["generated", "approved", "failed"].includes(draft.status);
                const isCallFollowUp = draft.source_type === "call_follow_up" || draft.ai_model === "vapi-call-followup-template";
                const isLinkedDraft = selectedDraftId && String(draft.id) === String(selectedDraftId);
                const draftKnowledgeUsedItems = getKnowledgeUsedItems(draft.knowledge_used);

                return (
                <div
                  key={draft.id}
                  className={[
                    "rounded-3xl border surface-2 p-4 elev-1 sm:p-5",
                    isLinkedDraft ? "border-violet-soft ring-4 ring-violet-soft" : "line-1",
                  ].join(" ")}
                >
                  <div className="flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-sm text-muted">
                        {draft.lead_company_name || `Lead ID ${draft.lead_id}`}
                      </p>
                      {isEditingDraft ? (
                        <input
                          type="text"
                          value={draftEditValues.subject}
                          onChange={(e) => setDraftEditValues((current) => ({
                            ...current,
                            subject: e.target.value,
                          }))}
                          className="field mt-2 font-semibold"
                          placeholder="Subject"
                        />
                      ) : (
                        <h3 className="mt-1 break-words text-lg font-semibold text-ink">
                          {draft.subject}
                        </h3>
                      )}
                      {(draft.lead_contact_name || draft.lead_contact_role) && (
                        <p className="mt-1 break-words text-sm text-muted">
                          {[draft.lead_contact_name, draft.lead_contact_role].filter(Boolean).join(" · ")}
                        </p>
                      )}
                      {draft.lead_email && (
                        <p className="mt-1 break-words text-sm text-muted">
                          To: {draft.lead_email}
                        </p>
                      )}
                      {isCallFollowUp && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Badge variant="asked_details">Call Follow-up</Badge>
                          {draft.call_log_id && <Badge variant="neutral">Call #{draft.call_log_id}</Badge>}
                        </div>
                      )}
                      {isCallFollowUp && draft.call_log_id && (
                        <p className="mt-2 text-xs font-medium text-violet">
                          Based on call {draft.call_created_at ? `from ${formatDateTimeIST(draft.call_started_at || draft.call_created_at)}` : `#${draft.call_log_id}`}
                          {draft.call_outcome ? ` | Outcome: ${draft.call_outcome}` : ""}
                        </p>
                      )}
                      {draft.lead_ai_score !== null && draft.lead_ai_score !== undefined ? (
                        <p className="mt-2 text-sm font-medium text-violet">
                          Final AI Score: {draft.lead_ai_score}
                          {draft.lead_ai_fit_score !== null && draft.lead_ai_fit_score !== undefined ? ` | Fit ${draft.lead_ai_fit_score}` : ""}
                          {draft.lead_ai_contact_confidence_score !== null && draft.lead_ai_contact_confidence_score !== undefined ? ` | Contact ${draft.lead_ai_contact_confidence_score}` : ""}
                          {draft.lead_ai_priority ? ` | ${draft.lead_ai_priority}` : ""}
                          {draft.lead_ai_qualification ? ` | ${draft.lead_ai_qualification}` : ""}
                        </p>
                      ) : (
                        <p className="mt-2 text-sm text-warn">
                          This lead has not been AI-scored yet.
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2 sm:justify-end">
                      {isCallFollowUp && <Badge variant="asked_details">Call Follow-up</Badge>}
                      <Badge variant={draft.status}>{draft.status}</Badge>
                    </div>
                  </div>

                  <div className="mt-4 rounded-2xl surface-sunk p-4">
                    {isEditingDraft ? (
                      <div>
                        <textarea
                          value={draftEditValues.body}
                          onChange={(e) => setDraftEditValues((current) => ({
                            ...current,
                            body: e.target.value,
                          }))}
                          className="field min-h-44"
                          placeholder="Email body"
                        />
                        <p className="mt-2 text-xs text-muted">
                          Editing an approved draft will require approval again before sending. Replace placeholders like [Your Name] manually before sending.
                        </p>
                      </div>
                    ) : (
                      <>
                        <p className="whitespace-pre-line break-words text-sm leading-6 text-ink-2">
                          {isDraftExpanded ? draft.body : getPreviewText(draft.body)}
                        </p>
                        {shouldCollapseDraft && (
                          <button
                            type="button"
                            className="mt-3 text-sm font-semibold text-info hover:text-info"
                            onClick={() => toggleDraftExpanded(draft.id)}
                          >
                            {isDraftExpanded ? "Hide full email" : "Show full email"}
                          </button>
                        )}
                      </>
                    )}
                  </div>

                  {(draft.sent_at || draft.send_error || draft.gmail_message_id) && (
                    <div className="mt-4 rounded-2xl border line-1 surface-sunk p-3 text-xs text-ink-2">
                      {draft.sent_at && (
                        <p>Sent at: {formatDateTimeIST(draft.sent_at)}</p>
                      )}
                      {draft.gmail_message_id && (
                        <p>Gmail message ID: {draft.gmail_message_id}</p>
                      )}
                      {draft.send_error && (
                        <p className="text-danger">Send error: {draft.send_error}</p>
                      )}
                    </div>
                  )}

                  {isCallFollowUp && draftKnowledgeUsedItems.length > 0 && (
                    <div className="mt-4 rounded-xl border border-violet-soft bg-violet-soft p-3">
                      <p className="text-xs font-semibold uppercase text-muted">Knowledge used</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {draftKnowledgeUsedItems.map((item, index) => (
                          <span
                            key={`${item.label}-${index}`}
                            className="inline-flex flex-wrap items-center gap-2 rounded-xl border line-1 surface-2 px-3 py-2 text-xs text-ink-2"
                          >
                            <span className="font-medium">{item.title}</span>
                            {item.sourceType && (
                              <Badge variant={String(item.sourceType).toLowerCase() === "document" ? "sent" : "neutral"}>
                                {item.sourceType}
                              </Badge>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {draft.status === "replied" && (draft.reply_snippet || draft.replied_at) && (
                    <div className="mt-4 rounded-2xl border border-success-soft bg-success-soft p-4 text-sm text-success">
                      <p className="font-medium">Replied</p>
                      {draft.replied_at && (
                        <p className="mt-1 text-xs text-success">Replied at: {formatDateTimeIST(draft.replied_at)}</p>
                      )}
                      {draft.reply_snippet && (
                        <p className="mt-2 text-sm leading-6">{draft.reply_snippet}</p>
                      )}
                    </div>
                  )}

                  {draft.status === "replied" && replyClassified && (
                    <div className="mt-4 rounded-2xl border border-info-soft bg-info-soft p-4 text-sm text-ink">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <p className="font-semibold text-ink">AI Reply Classification</p>
                          {draft.reply_classified_at && (
                            <p className="mt-1 text-xs text-muted">
                              Classified at: {formatDateTimeIST(draft.reply_classified_at)}
                            </p>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {draft.reply_intent && <Badge variant={draft.reply_intent}>{draft.reply_intent}</Badge>}
                          {draft.reply_sentiment && <Badge variant={draft.reply_sentiment}>{draft.reply_sentiment}</Badge>}
                          {draft.reply_priority && <Badge variant={draft.reply_priority}>{draft.reply_priority}</Badge>}
                        </div>
                      </div>

                      {draft.reply_summary && (
                        <div className="mt-4">
                          <p className="text-xs font-semibold uppercase text-muted">Summary</p>
                          <p className="mt-1 leading-6 text-ink-2">{draft.reply_summary}</p>
                        </div>
                      )}

                      {draft.reply_next_action && (
                        <div className="mt-3">
                          <p className="text-xs font-semibold uppercase text-muted">Next action</p>
                          <p className="mt-1 leading-6 text-ink-2">{draft.reply_next_action}</p>
                        </div>
                      )}

                      {draft.reply_suggested_response_direction && (
                        <div className="mt-3">
                          <p className="text-xs font-semibold uppercase text-muted">Suggested response direction</p>
                          <p className="mt-1 leading-6 text-ink-2">{draft.reply_suggested_response_direction}</p>
                        </div>
                      )}

                      {draft.reply_classification_error && (
                        <p className="mt-3 rounded-lg border border-warn-soft bg-warn-soft p-3 text-xs text-warn">
                          {draft.reply_classification_error}
                        </p>
                      )}
                    </div>
                  )}

                  {draft.status === "replied" && latestResponseDraft && (
                    <div className="mt-4 rounded-2xl border border-violet-soft bg-violet-soft p-4 text-sm text-ink">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
	                        <div>
	                          <p className="font-semibold text-ink">AI Response Draft</p>
	                          {isEditingResponseDraft ? (
	                            <input
	                              type="text"
	                              value={responseDraftEditValues.subject}
	                              onChange={(e) => setResponseDraftEditValues((current) => ({
	                                ...current,
	                                subject: e.target.value,
	                              }))}
	                              className="field mt-2 font-semibold"
	                              placeholder="Subject"
	                            />
	                          ) : (
	                            <h4 className="mt-1 break-words text-sm font-semibold text-ink">
	                              {latestResponseDraft.subject}
	                            </h4>
	                          )}
	                        </div>
	                        <Badge variant={latestResponseDraft.status}>{latestResponseDraft.status}</Badge>
	                      </div>

	                      {isEditingResponseDraft ? (
	                        <div className="mt-4">
	                          <textarea
	                            value={responseDraftEditValues.body}
	                            onChange={(e) => setResponseDraftEditValues((current) => ({
	                              ...current,
	                              body: e.target.value,
	                            }))}
	                            className="field min-h-44"
	                            placeholder="Response body"
	                          />
	                          <p className="mt-2 text-xs text-muted">
	                            Editing an approved draft will require approval again before sending. Replace placeholders like [Your Name] manually before sending.
	                          </p>
	                        </div>
	                      ) : (
	                        <p className="mt-4 whitespace-pre-line break-words leading-6 text-ink-2">
	                          {latestResponseDraft.body}
	                        </p>
	                      )}

                      {knowledgeUsedItems.length > 0 && (
                        <div className="mt-4 rounded-xl border border-violet-soft surface-2 p-3">
                          <p className="text-xs font-semibold uppercase text-muted">Knowledge used</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {knowledgeUsedItems.map((item, index) => (
                              <span
                                key={`${item.label}-${index}`}
                                className="inline-flex flex-wrap items-center gap-2 rounded-xl border line-1 surface-2 px-3 py-2 text-xs text-ink-2"
                              >
                                <span className="font-medium">{item.title}</span>
                                {item.sourceType && (
                                  <Badge variant={String(item.sourceType).toLowerCase() === "document" ? "sent" : "neutral"}>
                                    {item.sourceType}
                                  </Badge>
                                )}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="mt-4 space-y-1 text-xs text-ink-2">
                        <p>Generated: {formatDateTimeIST(latestResponseDraft.generated_at || latestResponseDraft.created_at)}</p>
                        {latestResponseDraft.approved_at && (
                          <p>Approved: {formatDateTimeIST(latestResponseDraft.approved_at)}</p>
                        )}
                        {latestResponseDraft.sent_at && (
                          <p>Sent: {formatDateTimeIST(latestResponseDraft.sent_at)}</p>
                        )}
                        {latestResponseDraft.gmail_message_id && (
                          <p>Gmail message ID: {latestResponseDraft.gmail_message_id}</p>
                        )}
                        {latestResponseDraft.gmail_thread_id && (
                          <p>Gmail thread ID: {latestResponseDraft.gmail_thread_id}</p>
                        )}
                        {latestResponseDraft.send_error && (
                          <p className={latestResponseDraft.status === "failed" ? "text-danger" : "text-warn"}>
                            {latestResponseDraft.status === "failed" ? "Send error" : "Generation note"}: {latestResponseDraft.send_error}
                          </p>
                        )}
                      </div>

	                      <div className="mt-4 flex flex-wrap gap-2">
	                        {isEditingResponseDraft ? (
	                          <>
	                            <button
	                              className="rounded bg-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:surface-3"
	                              disabled={updatingResponseDraftId === latestResponseDraft.id}
	                              onClick={() => handleSaveResponseDraftEdit(latestResponseDraft.id)}
	                            >
	                              {updatingResponseDraftId === latestResponseDraft.id ? "Saving..." : "Save"}
	                            </button>
	                            <button
	                              className="rounded border line-1 surface-2 px-3 py-2 text-xs font-medium text-ink-2 hover:surface-2"
	                              onClick={cancelResponseDraftEdit}
	                            >
	                              Cancel
	                            </button>
	                          </>
	                        ) : (
	                          <>
	                        {latestResponseDraft.status === "generated" && (
	                          <>
                            <button
                              className="rounded bg-success-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-success-solid"
                              disabled={updatingResponseDraftId === latestResponseDraft.id}
                              onClick={() => handleUpdateResponseStatus(latestResponseDraft.id, "approved")}
                            >
                              {updatingResponseDraftId === latestResponseDraft.id ? "Updating..." : "Approve"}
                            </button>
                            <button
                              className="rounded bg-danger-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-danger-solid"
                              disabled={updatingResponseDraftId === latestResponseDraft.id}
                              onClick={() => handleUpdateResponseStatus(latestResponseDraft.id, "rejected")}
                            >
                              {updatingResponseDraftId === latestResponseDraft.id ? "Updating..." : "Reject"}
                            </button>
                          </>
                        )}

                        {latestResponseDraft.status === "approved" && (
                          <>
                            <button
                              className="rounded bg-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:surface-3"
                              disabled={sendingResponseDraftId === latestResponseDraft.id || isSendingResponses}
                              onClick={() => handleSendResponseDraft(latestResponseDraft.id)}
                            >
                              {sendingResponseDraftId === latestResponseDraft.id ? "Sending..." : "Send Response"}
                            </button>
                            <button
                              className="rounded bg-danger-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-danger-solid"
                              disabled={updatingResponseDraftId === latestResponseDraft.id || sendingResponseDraftId === latestResponseDraft.id}
                              onClick={() => handleUpdateResponseStatus(latestResponseDraft.id, "rejected")}
                            >
                              {updatingResponseDraftId === latestResponseDraft.id ? "Updating..." : "Reject"}
                            </button>
	                          </>
	                        )}
	                            {["generated", "approved", "failed"].includes(latestResponseDraft.status) && (
	                              <button
	                                className="rounded border line-1 surface-2 px-3 py-2 text-xs font-medium text-ink-2 hover:surface-2"
	                                onClick={() => startResponseDraftEdit(latestResponseDraft)}
	                              >
	                                Edit
	                              </button>
	                            )}
	                          </>
	                        )}
	                      </div>
                    </div>
                  )}

                  <div className="mt-5 flex flex-col gap-3 border-t line-1 pt-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="text-xs text-muted">
                      <span>{draft.ai_model || "AI model unavailable"}</span>
                      <span className="mx-2">|</span>
                      <span>{formatDateTimeIST(draft.created_at)}</span>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {isEditingDraft ? (
                        <>
                          <button
                            className="rounded bg-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:surface-3"
                            disabled={updatingDraftId === draft.id}
                            onClick={() => handleSaveDraftEdit(draft.id)}
                          >
                            {updatingDraftId === draft.id ? "Saving..." : "Save"}
                          </button>
                          <button
                            className="rounded border line-1 surface-2 px-3 py-2 text-xs font-medium text-ink-2 hover:surface-2"
                            onClick={cancelDraftEdit}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                      {draft.status === "generated" && (
                        <>
                          <button
                            className="rounded bg-success-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-success-solid"
                            disabled={updatingDraftId === draft.id || sendingDraftId === draft.id}
                            onClick={() => handleUpdateStatus(draft.id, "approved")}
                          >
                            {updatingDraftId === draft.id ? "Updating..." : "Approve"}
                          </button>
                          <button
                            className="rounded bg-danger-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-danger-solid"
                            disabled={updatingDraftId === draft.id || sendingDraftId === draft.id}
                            onClick={() => handleUpdateStatus(draft.id, "rejected")}
                          >
                            {updatingDraftId === draft.id ? "Updating..." : "Reject"}
                          </button>
                        </>
                      )}
                      {draft.status === "approved" && (
                        <>
                          <button
                            className="rounded bg-violet-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-violet-solid"
                            disabled={sendingDraftId === draft.id || isSendingCampaign}
                            onClick={() => handleSendDraft(draft.id)}
                          >
                            {sendingDraftId === draft.id ? "Sending..." : "Send"}
                          </button>
                          <button
                            className="rounded bg-danger-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-danger-solid"
                            disabled={updatingDraftId === draft.id || sendingDraftId === draft.id}
                            onClick={() => handleUpdateStatus(draft.id, "rejected")}
                          >
                            {updatingDraftId === draft.id ? "Updating..." : "Reject"}
                          </button>
                        </>
                      )}
                      {draft.status === "sent" && (
                        <>
                          <button
                            className="rounded bg-success-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-success-solid"
                            disabled={checkingReplyDraftId === draft.id || isCheckingReplies}
                            onClick={() => handleCheckDraftReply(draft.id)}
                          >
                            {checkingReplyDraftId === draft.id ? "Checking..." : "Check Reply"}
                          </button>
                          {canGenerateFollowUp && (
                            <button
                              className="rounded bg-violet-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-violet-solid"
                              disabled={generatingFollowUpDraftId === draft.id || isGeneratingFollowUps}
                              onClick={() => handleGenerateFollowUp(draft.id)}
                            >
                              {generatingFollowUpDraftId === draft.id ? "Generating..." : "Generate Follow-up"}
                            </button>
                          )}
                        </>
                      )}
                      {draft.status === "replied" && (
                        <>
                          <button
                            className="rounded bg-warn-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-warn-solid"
                            disabled={classifyingReplyDraftId === draft.id || isClassifyingReplies}
                            onClick={() => handleClassifyDraftReply(draft.id, replyClassified)}
                          >
                            {classifyingReplyDraftId === draft.id
                              ? "Classifying..."
                              : replyClassified
                                ? "Reclassify"
                                : "Classify Reply"}
                          </button>

                          {canGenerateResponseDraft && latestResponseDraft?.status !== "sent" && (
                            <button
                              className="rounded bg-violet-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-violet-solid"
                              disabled={generatingResponseDraftId === draft.id || isGeneratingResponses}
                              onClick={() => handleGenerateResponseDraft(draft.id, Boolean(latestResponseDraft))}
                            >
                              {generatingResponseDraftId === draft.id
                                ? "Generating..."
                                : latestResponseDraft
                                  ? "Regenerate Response"
                                  : "Generate Response Draft"}
                            </button>
                          )}
                        </>
                      )}
                          {canEditDraft && (
                            <button
                              className="rounded border line-1 surface-2 px-3 py-2 text-xs font-medium text-ink-2 hover:surface-2"
                              onClick={() => startDraftEdit(draft)}
                            >
                              Edit
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>

                  {draftFollowUps.length > 0 && (
                    <div className="mt-5 border-t pt-4">
                      <h4 className="text-sm font-semibold text-ink">Follow-ups</h4>
                      <div className="mt-3 divide-y">
                        {draftFollowUps.map((followUp) => {
                          const isFollowUpExpanded = Boolean(expandedFollowUpIds[followUp.id]);
                          const shouldCollapseFollowUp = String(followUp.body || "").length > 180;
                          const isEditingFollowUp = editingFollowUpId === followUp.id;
                          const canEditFollowUp = ["generated", "approved", "failed"].includes(followUp.status);

                          return (
                          <div key={followUp.id} className="py-4 first:pt-0 last:pb-0">
                            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                              <div>
                                <p className="text-xs font-medium text-muted">
                                  Follow-up #{followUp.follow_up_number}
                                </p>
                                {isEditingFollowUp ? (
                                  <input
                                    type="text"
                                    value={followUpEditValues.subject}
                                    onChange={(e) => setFollowUpEditValues((current) => ({
                                      ...current,
                                      subject: e.target.value,
                                    }))}
                                    className="field mt-2 font-semibold"
                                    placeholder="Subject"
                                  />
                                ) : (
                                  <h5 className="mt-1 text-sm font-semibold text-ink">
                                    {followUp.subject}
                                  </h5>
                                )}
                              </div>

                              <Badge variant={followUp.status}>{followUp.status}</Badge>
                            </div>

                            {isEditingFollowUp ? (
                              <div className="mt-3">
                                <textarea
                                  value={followUpEditValues.body}
                                  onChange={(e) => setFollowUpEditValues((current) => ({
                                    ...current,
                                    body: e.target.value,
                                  }))}
                                  className="field min-h-44"
                                  placeholder="Follow-up body"
                                />
                                <p className="mt-2 text-xs text-muted">
                                  Editing an approved draft will require approval again before sending. Replace placeholders like [Your Name] manually before sending.
                                </p>
                              </div>
                            ) : (
                              <>
                                <p className="mt-3 whitespace-pre-line text-sm leading-6 text-ink-2">
                                  {isFollowUpExpanded ? followUp.body : getPreviewText(followUp.body, 180)}
                                </p>
                                {shouldCollapseFollowUp && (
                                  <button
                                    type="button"
                                    className="mt-2 text-xs font-semibold text-info hover:text-info"
                                    onClick={() => toggleFollowUpExpanded(followUp.id)}
                                  >
                                    {isFollowUpExpanded ? "Hide follow-up" : "Show full follow-up"}
                                  </button>
                                )}
                              </>
                            )}

                            <div className="mt-3 text-xs text-muted">
                              <p>Generated: {formatDateTimeIST(followUp.generated_at || followUp.created_at)}</p>
                              {followUp.sent_at && (
                                <p>Sent at: {formatDateTimeIST(followUp.sent_at)}</p>
                              )}
                              {followUp.gmail_message_id && (
                                <p>Gmail message ID: {followUp.gmail_message_id}</p>
                              )}
                              {followUp.send_error && (
                                <p className="text-danger">Send error: {followUp.send_error}</p>
                              )}
                            </div>

                            <div className="mt-3 flex flex-wrap gap-2">
                              {isEditingFollowUp ? (
                                <>
                                  <button
                                    className="rounded bg-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:surface-3"
                                    disabled={updatingFollowUpId === followUp.id}
                                    onClick={() => handleSaveFollowUpEdit(followUp.id)}
                                  >
                                    {updatingFollowUpId === followUp.id ? "Saving..." : "Save"}
                                  </button>
                                  <button
                                    className="rounded border line-1 surface-2 px-3 py-2 text-xs font-medium text-ink-2 hover:surface-2"
                                    onClick={cancelFollowUpEdit}
                                  >
                                    Cancel
                                  </button>
                                </>
                              ) : (
                                <>
                                  {followUp.status === "generated" && (
                                    <>
                                      <button
                                        className="rounded bg-success-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-success-solid"
                                        disabled={updatingFollowUpId === followUp.id}
                                        onClick={() => handleUpdateFollowUpStatus(followUp.id, "approved")}
                                      >
                                        {updatingFollowUpId === followUp.id ? "Updating..." : "Approve"}
                                      </button>
                                      <button
                                        className="rounded bg-danger-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-danger-solid"
                                        disabled={updatingFollowUpId === followUp.id}
                                        onClick={() => handleUpdateFollowUpStatus(followUp.id, "rejected")}
                                      >
                                        {updatingFollowUpId === followUp.id ? "Updating..." : "Reject"}
                                      </button>
                                    </>
                                  )}

                                  {followUp.status === "approved" && (
                                    <>
                                      <button
                                        className="rounded bg-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:surface-3"
                                        disabled={sendingFollowUpId === followUp.id || isSendingFollowUps}
                                        onClick={() => handleSendFollowUp(followUp.id)}
                                      >
                                        {sendingFollowUpId === followUp.id ? "Sending..." : "Send"}
                                      </button>
                                      <button
                                        className="rounded bg-danger-solid px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:bg-danger-solid"
                                        disabled={updatingFollowUpId === followUp.id || sendingFollowUpId === followUp.id}
                                        onClick={() => handleUpdateFollowUpStatus(followUp.id, "rejected")}
                                      >
                                        {updatingFollowUpId === followUp.id ? "Updating..." : "Reject"}
                                      </button>
                                    </>
                                  )}
                                  {canEditFollowUp && (
                                    <button
                                      className="rounded border line-1 surface-2 px-3 py-2 text-xs font-medium text-ink-2 hover:surface-2"
                                      onClick={() => startFollowUpEdit(followUp)}
                                    >
                                      Edit
                                    </button>
                                  )}
                                </>
                              )}
                            </div>
                          </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Emails;
