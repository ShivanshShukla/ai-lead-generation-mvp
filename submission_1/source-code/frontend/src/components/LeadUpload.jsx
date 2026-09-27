import { useState } from "react";
import api from "../services/api";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Button from "./ui/Button";
import Card from "./ui/Card";

function LeadUpload({ campaignId, onUploadComplete }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [inputKey, setInputKey] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleFileChange = (e) => {
    setSelectedFile(e.target.files?.[0] || null);
    setMessage("");
    setError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!campaignId) {
      setError("Please select a campaign before uploading leads.");
      return;
    }

    if (!selectedFile) {
      setError("Please choose a CSV file to upload.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);
    setIsUploading(true);

    try {
      const res = await api.post(`/leads/upload-csv/${campaignId}`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      setMessage(`${res.data.inserted_count} leads uploaded successfully.`);
      setSelectedFile(null);
      setInputKey((currentKey) => currentKey + 1);
      onUploadComplete?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(err.response ? detail || "Failed to upload CSV. Please check the file and try again." : getFriendlyErrorMessage(err));
      console.error(err);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Card>
      <div className="mb-4">
        <h2 className="text-xl font-semibold tracking-tight text-ink">Upload Leads CSV</h2>
        <p className="mt-1 text-sm text-muted">
          Upload leads for the selected campaign.
        </p>
      </div>

      {message && (
        <p className="mb-4 rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">
          {message}
        </p>
      )}

      {error && (
        <p className="mb-4 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="flex-1">
          <label className="mb-2 block text-sm font-medium text-ink-2">
            CSV File
          </label>
          <input
            key={inputKey}
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            className="min-h-12 w-full rounded-2xl border line-1 surface-2 p-3 text-sm elev-1 file:mr-3 file:rounded-xl file:border-0 file:surface-sunk file:px-3 file:py-2 file:text-sm file:font-semibold file:text-ink-2"
            disabled={!campaignId || isUploading}
          />
        </div>

        <Button
          type="submit"
          className="w-full lg:w-auto"
          disabled={!campaignId || !selectedFile || isUploading}
        >
          {isUploading ? "Uploading..." : "Upload CSV"}
        </Button>
      </form>

      {!campaignId && (
        <p className="mt-3 text-sm text-muted">
          Select a campaign above to enable CSV upload.
        </p>
      )}
    </Card>
  );
}

export default LeadUpload;
