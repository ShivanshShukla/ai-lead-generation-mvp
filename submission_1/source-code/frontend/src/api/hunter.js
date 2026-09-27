import api from "../services/api";

export const getHunterStatus = () =>
  api.get("/hunter/status").then((response) => response.data);

export const domainSearch = (domain, limit = 10) =>
  api.post("/hunter/domain-search", { domain, limit }).then((response) => response.data);

export const emailFinder = (domain, firstName, lastName) =>
  api
    .post("/hunter/email-finder", {
      domain,
      first_name: firstName,
      last_name: lastName,
    })
    .then((response) => response.data);

export const verifyEmail = (email) =>
  api.post("/hunter/verify", { email }).then((response) => response.data);

export const enrichLead = (leadId, options = {}) =>
  api
    .post(`/hunter/enrich-lead/${leadId}`, null, {
      params: {
        mode: options.mode || "domain",
        min_confidence: options.minConfidence ?? 50,
      },
    })
    .then((response) => response.data);

export const bulkEnrich = (campaignId, options = {}) =>
  api
    .post("/hunter/bulk-enrich", {
      campaign_id: Number(campaignId),
      mode: options.mode || "domain",
      limit: options.limit ?? 20,
      min_confidence: options.minConfidence ?? 50,
    })
    .then((response) => response.data);
