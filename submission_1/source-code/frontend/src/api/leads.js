import api from "../services/api";

export const extractEmailsAsync = (campaignId, limit = 100) =>
  api
    .post(`/leads/campaign/${campaignId}/extract-emails-async`, null, {
      params: { limit },
    })
    .then((response) => response.data);

export const getExtractionJob = (jobId) =>
  api.get(`/leads/extraction-job/${jobId}`).then((response) => response.data);

export const getCampaignExtractionStatus = (campaignId) =>
  api.get(`/leads/campaign/${campaignId}/extraction-status`).then((response) => response.data);
