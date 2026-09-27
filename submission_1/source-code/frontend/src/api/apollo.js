import api from "../services/api";

export const getApolloStatus = () =>
  api.get("/apollo/status").then((response) => response.data);

export const enrichLead = (leadId) =>
  api
    .post(`/apollo/enrich-lead/${leadId}`)
    .then((response) => response.data);

export const bulkEnrich = (campaignId, limit = 20) =>
  api
    .post("/apollo/bulk-enrich", {
      campaign_id: Number(campaignId),
      limit: limit,
    })
    .then((response) => response.data);
