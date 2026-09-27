import { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import { formatDateTimeIST } from "../utils/dateUtils";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import PageHeader from "../components/ui/PageHeader";

const KNOWLEDGE_CATEGORIES = [
  "Company Profile",
  "Product Details",
  "Pricing",
  "FAQ",
  "Case Study",
  "Demo Script",
  "Objection Handling",
  "Email Template",
  "Other",
];

const emptyForm = {
  title: "",
  category: "Product Details",
  tags: "",
  content: "",
  is_active: true,
};

const emptyUploadForm = {
  category: "Product Details",
  tags: "",
};

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

function getPreviewText(value, maxLength = 260) {
  const text = String(value || "").trim();

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength).trim()}...`;
}

function getSourceLabel(entry) {
  return String(entry?.source_type || "manual").toLowerCase() === "document" ? "Document" : "Manual";
}

function getDocumentStatusVariant(status) {
  const normalizedStatus = String(status || "").toLowerCase();

  if (normalizedStatus === "processed") {
    return "success";
  }

  if (normalizedStatus === "failed") {
    return "danger";
  }

  return "warning";
}

function Knowledge() {
  const [entries, setEntries] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [embeddingStatus, setEmbeddingStatus] = useState(null);
  const [searchMeta, setSearchMeta] = useState(null);
  const [documentDetail, setDocumentDetail] = useState(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [isLoadingDocumentDetail, setIsLoadingDocumentDetail] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isBackfillingEmbeddings, setIsBackfillingEmbeddings] = useState(false);
  const [deactivatingId, setDeactivatingId] = useState(null);
  const [deactivatingDocumentId, setDeactivatingDocumentId] = useState(null);
  const [reactivatingDocumentId, setReactivatingDocumentId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [formValues, setFormValues] = useState(emptyForm);
  const [uploadFormValues, setUploadFormValues] = useState(emptyUploadForm);
  const [uploadFile, setUploadFile] = useState(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [searchMode, setSearchMode] = useState("hybrid");
  const [activeOnly, setActiveOnly] = useState(true);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const activeCount = useMemo(
    () => entries.filter((entry) => entry.is_active).length,
    [entries]
  );
  const entriesSectionTitle = activeSearch
    ? `Search Results for ${activeSearch}`
    : "Knowledge Entries";
  const entriesSectionSummary = activeSearch
    ? `${entries.length} ${entries.length === 1 ? "result" : "results"} found`
    : `${entries.length} shown, ${activeCount} active.`;

  const loadKnowledge = async ({
    queryText = activeSearch,
    nextCategoryFilter = categoryFilter,
    nextActiveOnly = activeOnly,
    mode = searchMode,
  } = {}) => {
    setIsLoading(true);
    setErrorMessage("");

    try {
      const trimmedQuery = String(queryText || "").trim();
      const res = trimmedQuery
        ? await api.get("/knowledge/search/relevant", {
          params: {
            q: trimmedQuery,
            limit: 10,
            mode,
          },
        })
        : await api.get("/knowledge/", {
          params: {
            category: nextCategoryFilter || undefined,
            active_only: nextActiveOnly,
          },
        });

      setEntries(Array.isArray(res.data.data) ? res.data.data : []);
      setSearchMeta(trimmedQuery ? {
        mode: res.data.mode,
        retrievalMethod: res.data.retrieval_method,
        semanticAvailable: Boolean(res.data.semantic_available),
        message: res.data.message || "",
      } : null);
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Could not load company knowledge. Please try again."));
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const loadEmbeddingStatus = async () => {
    try {
      const res = await api.get("/knowledge/embeddings/status");
      setEmbeddingStatus(res.data || null);
    } catch (err) {
      setEmbeddingStatus(null);
      console.error(err);
    }
  };

  const loadDocuments = async () => {
    setIsLoadingDocuments(true);

    try {
      const res = await api.get("/knowledge/documents");
      setDocuments(Array.isArray(res.data.data) ? res.data.data : []);
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Could not load uploaded documents. Please try again."));
      console.error(err);
    } finally {
      setIsLoadingDocuments(false);
    }
  };

  const refreshKnowledgeAndDocuments = async () => {
    await Promise.all([
      loadKnowledge(),
      loadDocuments(),
      loadEmbeddingStatus(),
    ]);
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshKnowledgeAndDocuments();
    }, 0);

    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryFilter, activeOnly]);

  const handleSearchSubmit = async (e) => {
    e.preventDefault();
    const trimmedSearch = search.trim();

    if (!trimmedSearch) {
      setActiveSearch("");
      setCategoryFilter("");
      setActiveOnly(true);
      await loadKnowledge({
        queryText: "",
        nextCategoryFilter: "",
        nextActiveOnly: true,
      });
      return;
    }

    setActiveSearch(trimmedSearch);
    await loadKnowledge({ queryText: trimmedSearch, mode: searchMode });
  };

  const handleClearSearch = async () => {
    setSearch("");
    setActiveSearch("");
    setSearchMeta(null);
    setCategoryFilter("");
    setActiveOnly(true);
    await loadKnowledge({
      queryText: "",
      nextCategoryFilter: "",
      nextActiveOnly: true,
    });
  };

  const handleBackfillEmbeddings = async () => {
    setIsBackfillingEmbeddings(true);
    setStatusMessage("");
    setErrorMessage("");

    try {
      const res = await api.post("/knowledge/embeddings/backfill", null, {
        params: {
          limit: 20,
        },
      });
      const result = res.data || {};
      const message = result.message
        || `Embedding backfill processed ${result.processed ?? 0} entries. Embedded ${result.embedded ?? 0}, failed ${result.failed ?? 0}.`;

      setStatusMessage(message);
      await Promise.all([
        loadEmbeddingStatus(),
        loadKnowledge({ queryText: activeSearch, mode: searchMode }),
      ]);
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Embedding generation failed. Keyword search fallback is still available."));
      console.error(err);
    } finally {
      setIsBackfillingEmbeddings(false);
    }
  };

  const updateFormValue = (field, value) => {
    setFormValues((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const updateUploadFormValue = (field, value) => {
    setUploadFormValues((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const resetForm = () => {
    setEditingId(null);
    setFormValues(emptyForm);
  };

  const resetUploadForm = () => {
    setUploadFile(null);
    setUploadFormValues(emptyUploadForm);
    setFileInputKey((current) => current + 1);
  };

  const handleEdit = (entry) => {
    setEditingId(entry.id);
    setFormValues({
      title: entry.title || "",
      category: entry.category || "Other",
      tags: entry.tags || "",
      content: entry.content || "",
      is_active: Boolean(entry.is_active),
    });
    setStatusMessage("");
    setErrorMessage("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formValues.title.trim() || !formValues.category.trim() || !formValues.content.trim()) {
      setErrorMessage("Title, category, and content are required.");
      return;
    }

    setIsSaving(true);
    setStatusMessage("");
    setErrorMessage("");

    const payload = {
      title: formValues.title.trim(),
      category: formValues.category,
      content: formValues.content.trim(),
      tags: formValues.tags.trim() || null,
      is_active: Boolean(formValues.is_active),
    };

    try {
      if (editingId) {
        await api.patch(`/knowledge/${editingId}`, payload);
        setStatusMessage("Knowledge entry updated successfully.");
      } else {
        await api.post("/knowledge/", payload);
        setStatusMessage("Knowledge entry created successfully.");
      }

      resetForm();
      await Promise.all([
        loadKnowledge(),
        loadEmbeddingStatus(),
      ]);
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Knowledge entry could not be saved. Please try again."));
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleUploadSubmit = async (e) => {
    e.preventDefault();

    if (!uploadFile) {
      setErrorMessage("Please choose a document to upload.");
      return;
    }

    if (uploadFile.size > MAX_UPLOAD_BYTES) {
      setErrorMessage("File is too large. Max size is 5 MB.");
      return;
    }

    setIsUploading(true);
    setStatusMessage("");
    setErrorMessage("");

    const formData = new FormData();
    formData.append("file", uploadFile);
    formData.append("category", uploadFormValues.category);

    if (uploadFormValues.tags.trim()) {
      formData.append("tags", uploadFormValues.tags.trim());
    }

    try {
      const res = await api.post("/knowledge/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      const totalChunks = res.data?.data?.total_chunks ?? 0;

      setStatusMessage(`Document processed successfully. ${totalChunks} knowledge chunks created.`);
      resetUploadForm();
      await refreshKnowledgeAndDocuments();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Upload failed. Please try again.", "knowledge-upload"));
      console.error(err);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeactivate = async (entryId) => {
    setDeactivatingId(entryId);
    setStatusMessage("");
    setErrorMessage("");

    try {
      await api.delete(`/knowledge/${entryId}`);
      setStatusMessage("Knowledge entry deactivated.");
      await loadKnowledge();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Knowledge entry could not be deactivated."));
      console.error(err);
    } finally {
      setDeactivatingId(null);
    }
  };

  const handleViewDocumentChunks = async (documentId) => {
    if (selectedDocumentId === documentId) {
      setSelectedDocumentId(null);
      setDocumentDetail(null);
      return;
    }

    setSelectedDocumentId(documentId);
    setDocumentDetail(null);
    setIsLoadingDocumentDetail(true);
    setErrorMessage("");

    try {
      const res = await api.get(`/knowledge/documents/${documentId}`);
      setDocumentDetail(res.data.data || null);
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Could not load document chunks. Please try again."));
      console.error(err);
    } finally {
      setIsLoadingDocumentDetail(false);
    }
  };

  const handleDeactivateDocument = async (documentId) => {
    setDeactivatingDocumentId(documentId);
    setStatusMessage("");
    setErrorMessage("");

    try {
      await api.delete(`/knowledge/documents/${documentId}`);
      setStatusMessage("Document knowledge deactivated successfully.");
      setDocumentDetail(null);
      setSelectedDocumentId(null);
      await refreshKnowledgeAndDocuments();
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Document knowledge could not be deactivated."));
      console.error(err);
    } finally {
      setDeactivatingDocumentId(null);
    }
  };

  const handleReactivateDocument = async (documentId) => {
    setReactivatingDocumentId(documentId);
    setStatusMessage("");
    setErrorMessage("");

    try {
      await api.post(`/knowledge/documents/${documentId}/reactivate`);
      setStatusMessage("Document knowledge reactivated successfully.");
      await refreshKnowledgeAndDocuments();

      if (selectedDocumentId === documentId) {
        const res = await api.get(`/knowledge/documents/${documentId}`);
        setDocumentDetail(res.data.data || null);
      }
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err, "Document knowledge could not be reactivated."));
      console.error(err);
    } finally {
      setReactivatingDocumentId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Knowledge"
        description="Store company facts, product notes, pricing guidance, FAQs, demo scripts, and uploaded documents for AI drafts to use when relevant."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(320px,420px)_1fr]">
        <div className="space-y-6">
          <Card>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold tracking-tight text-ink">
                  {editingId ? "Edit Knowledge" : "Add Knowledge"}
                </h3>
                <p className="mt-1 text-sm leading-6 text-muted">
                  Keep entries specific and factual. AI uses these as context, not as automatic send instructions.
                </p>
              </div>
              {editingId && (
                <Button type="button" variant="secondary" size="sm" onClick={resetForm}>
                  Cancel
                </Button>
              )}
            </div>

            <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
              <div>
                <label className="text-xs font-semibold uppercase text-muted" htmlFor="knowledge-title">
                  Title
                </label>
                <input
                  id="knowledge-title"
                  type="text"
                  value={formValues.title}
                  onChange={(e) => updateFormValue("title", e.target.value)}
                  className="field mt-2"
                  placeholder="Pricing Overview"
                />
              </div>

              <div>
                <label className="text-xs font-semibold uppercase text-muted" htmlFor="knowledge-category">
                  Category
                </label>
                <select
                  id="knowledge-category"
                  value={formValues.category}
                  onChange={(e) => updateFormValue("category", e.target.value)}
                  className="field mt-2"
                >
                  {KNOWLEDGE_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold uppercase text-muted" htmlFor="knowledge-tags">
                  Tags
                </label>
                <input
                  id="knowledge-tags"
                  type="text"
                  value={formValues.tags}
                  onChange={(e) => updateFormValue("tags", e.target.value)}
                  className="field mt-2"
                  placeholder="pricing, pilot, demo"
                />
              </div>

              <div>
                <label className="text-xs font-semibold uppercase text-muted" htmlFor="knowledge-content">
                  Content
                </label>
                <textarea
                  id="knowledge-content"
                  value={formValues.content}
                  onChange={(e) => updateFormValue("content", e.target.value)}
                  className="field mt-2 min-h-56"
                  placeholder="Add concise, verified company information."
                />
                <p className="mt-2 text-xs text-muted">
                  Max 10,000 characters. Shorter entries are easier for AI to use cleanly.
                </p>
              </div>

              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input
                  type="checkbox"
                  checked={formValues.is_active}
                  onChange={(e) => updateFormValue("is_active", e.target.checked)}
                  className="h-4 w-4 rounded line-2"
                />
                Active
              </label>

              <Button type="submit" className="w-full" disabled={isSaving}>
                {isSaving ? "Saving..." : editingId ? "Save Changes" : "Add Knowledge"}
              </Button>
            </form>
          </Card>

          <Card>
            <div>
              <h3 className="text-xl font-semibold tracking-tight text-ink">
                Upload Knowledge Document
              </h3>
              <p className="mt-1 text-sm leading-6 text-muted">
                Supported: PDF, DOCX, TXT, MD. Max 5 MB.
              </p>
            </div>

            <form className="mt-5 space-y-4" onSubmit={handleUploadSubmit}>
              <div>
                <label className="text-xs font-semibold uppercase text-muted" htmlFor="knowledge-document-file">
                  File
                </label>
                <input
                  key={fileInputKey}
                  id="knowledge-document-file"
                  type="file"
                  accept=".pdf,.docx,.txt,.md"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="field mt-2 border-dashed file:mr-3 file:rounded-lg file:border-0 file:bg-accent file:px-3 file:py-2 file:text-xs file:font-semibold file:text-white"
                />
              </div>

              <div>
                <label className="text-xs font-semibold uppercase text-muted" htmlFor="knowledge-upload-category">
                  Category
                </label>
                <select
                  id="knowledge-upload-category"
                  value={uploadFormValues.category}
                  onChange={(e) => updateUploadFormValue("category", e.target.value)}
                  className="field mt-2"
                >
                  {KNOWLEDGE_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold uppercase text-muted" htmlFor="knowledge-upload-tags">
                  Tags
                </label>
                <input
                  id="knowledge-upload-tags"
                  type="text"
                  value={uploadFormValues.tags}
                  onChange={(e) => updateUploadFormValue("tags", e.target.value)}
                  className="field mt-2"
                  placeholder="pricing, demo, onboarding"
                />
              </div>

              <Button type="submit" className="w-full" disabled={isUploading}>
                {isUploading ? "Uploading..." : "Upload Document"}
              </Button>
            </form>
          </Card>

          <Card>
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="text-xl font-semibold tracking-tight text-ink">
                    Semantic RAG
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-muted">
                    Hybrid search uses embeddings when available and falls back to keyword search.
                  </p>
                </div>
                <Badge variant={embeddingStatus?.semantic_available ? "success" : "warning"}>
                  {embeddingStatus?.semantic_available ? "Enabled" : "Fallback"}
                </Badge>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-xl border line-1 surface-sunk p-3">
                  <p className="text-xs font-semibold uppercase text-muted">Active</p>
                  <p className="mt-1 font-semibold text-ink">{embeddingStatus?.total_active ?? 0}</p>
                </div>
                <div className="rounded-xl border line-1 surface-sunk p-3">
                  <p className="text-xs font-semibold uppercase text-muted">Embedded</p>
                  <p className="mt-1 font-semibold text-ink">{embeddingStatus?.with_embeddings ?? 0}</p>
                </div>
                <div className="rounded-xl border line-1 surface-sunk p-3">
                  <p className="text-xs font-semibold uppercase text-muted">Missing</p>
                  <p className="mt-1 font-semibold text-ink">{embeddingStatus?.missing_embeddings ?? 0}</p>
                </div>
                <div className="rounded-xl border line-1 surface-sunk p-3">
                  <p className="text-xs font-semibold uppercase text-muted">Errors</p>
                  <p className="mt-1 font-semibold text-ink">{embeddingStatus?.embedding_errors ?? 0}</p>
                </div>
              </div>

              <p className="break-words text-xs text-muted">
                Model: {embeddingStatus?.embedding_model || "Not configured"}
              </p>

              <Button
                type="button"
                variant="secondary"
                className="w-full"
                disabled={isBackfillingEmbeddings}
                onClick={handleBackfillEmbeddings}
              >
                {isBackfillingEmbeddings ? "Generating..." : "Generate Missing Embeddings"}
              </Button>
            </div>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card className="order-1">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h3 className="text-xl font-semibold tracking-tight text-ink">Company Knowledge Base</h3>
                <p className="mt-1 text-sm text-muted">
                  Search manual entries and uploaded document chunks.
                </p>
              </div>

              <form className="grid gap-3 sm:grid-cols-2 lg:min-w-[820px] lg:grid-cols-[1fr_150px_150px_auto_auto]" onSubmit={handleSearchSubmit}>
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="field"
                  placeholder="Search knowledge"
                />
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="field"
                >
                  <option value="">All categories</option>
                  {KNOWLEDGE_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
                <select
                  value={searchMode}
                  onChange={(e) => setSearchMode(e.target.value)}
                  className="field"
                >
                  <option value="hybrid">Hybrid</option>
                  <option value="semantic">Semantic</option>
                  <option value="keyword">Keyword</option>
                </select>
                <Button type="submit" variant="secondary">
                  Search
                </Button>
                {(search || activeSearch) && (
                  <Button type="button" variant="ghost" onClick={handleClearSearch}>
                    Clear Search
                  </Button>
                )}
              </form>
            </div>

            <label className="mt-4 flex items-center gap-2 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)}
                className="h-4 w-4 rounded line-2"
              />
              Show active entries only
            </label>

            {(statusMessage || errorMessage) && (
              <div className="mt-4 space-y-2">
                {statusMessage && (
                  <p className="rounded-lg border border-success-soft bg-success-soft p-3 text-sm text-success">
                    {statusMessage}
                  </p>
                )}
                {errorMessage && (
                  <p className="rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
                    {errorMessage}
                  </p>
                )}
              </div>
            )}

            {activeSearch && searchMeta?.message && searchMode !== "keyword" && (
              <p className="mt-4 rounded-lg border border-warn-soft bg-warn-soft p-3 text-sm text-warn">
                {searchMeta.message}
              </p>
            )}
          </Card>

          <Card className="order-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-xl font-semibold tracking-tight text-ink">Uploaded Documents</h3>
                <p className="mt-1 text-sm text-muted">
                  {documents.length} documents uploaded.
                </p>
              </div>
            </div>

            {isLoadingDocuments ? (
              <p className="mt-4 text-sm text-ink-2">Loading uploaded documents...</p>
            ) : documents.length === 0 ? (
              <div className="mt-4 border border-dashed line-1 p-6 text-center">
                <h3 className="font-medium text-ink">No uploaded documents yet.</h3>
                <p className="mt-1 text-sm text-muted">
                  Upload TXT, Markdown, PDF, or DOCX files to turn them into searchable knowledge chunks.
                </p>
              </div>
            ) : (
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {documents.map((document) => {
                  const activeChunks = Number(document.active_chunks ?? document.total_chunks ?? 0);
                  const totalChunks = Number(document.total_chunks ?? 0);
                  const isDocumentActive = activeChunks > 0;
                  const isSelected = selectedDocumentId === document.id;

                  return (
                    <article key={document.id} className="rounded-2xl border line-1 surface-sunk p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap gap-2">
                            <Badge variant={getDocumentStatusVariant(document.status)}>
                              {document.status || "processed"}
                            </Badge>
                            <Badge variant="neutral">
                              {String(document.file_type || "").toUpperCase()}
                            </Badge>
                            {document.category && <Badge variant="neutral">{document.category}</Badge>}
                          </div>
                          <h4 className="mt-3 break-words text-base font-semibold text-ink">
                            {document.original_filename || document.filename}
                          </h4>
                          {document.tags && (
                            <p className="mt-1 break-words text-xs font-medium text-muted">
                              {document.tags}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="mt-4 space-y-1 text-xs text-ink-2">
                        <p>Chunks: {activeChunks} active / {totalChunks} total</p>
                        <p>Uploaded: {formatDateTimeIST(document.uploaded_at)}</p>
                        {document.error_message && (
                          <p className="text-danger">{document.error_message}</p>
                        )}
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          onClick={() => handleViewDocumentChunks(document.id)}
                        >
                          {isSelected ? "Hide Chunks" : "View Chunks"}
                        </Button>
                        {isDocumentActive ? (
                          <Button
                            type="button"
                            variant="danger"
                            size="sm"
                            disabled={deactivatingDocumentId === document.id}
                            onClick={() => handleDeactivateDocument(document.id)}
                          >
                            {deactivatingDocumentId === document.id ? "Deactivating..." : "Deactivate"}
                          </Button>
                        ) : totalChunks > 0 && (
                          <Button
                            type="button"
                            variant="success"
                            size="sm"
                            disabled={reactivatingDocumentId === document.id}
                            onClick={() => handleReactivateDocument(document.id)}
                          >
                            {reactivatingDocumentId === document.id ? "Reactivating..." : "Reactivate"}
                          </Button>
                        )}
                      </div>

                      {isSelected && (
                        <div className="mt-4 rounded-xl border line-1 surface-2 p-3">
                          {isLoadingDocumentDetail ? (
                            <p className="text-sm text-ink-2">Loading chunks...</p>
                          ) : documentDetail?.chunks?.length ? (
                            <div className="space-y-3">
                              {documentDetail.chunks.map((chunk) => (
                                <div key={chunk.id} className="border-b line-1 pb-3 last:border-b-0 last:pb-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge variant={chunk.is_active ? "success" : "neutral"}>
                                      {chunk.is_active ? "Active" : "Inactive"}
                                    </Badge>
                                    <Badge variant="neutral">Chunk {chunk.chunk_index || chunk.id}</Badge>
                                  </div>
                                  <p className="mt-2 break-words text-sm font-medium text-ink">
                                    {chunk.title}
                                  </p>
                                  <p className="mt-1 whitespace-pre-line break-words text-xs leading-5 text-ink-2">
                                    {getPreviewText(chunk.content_preview || chunk.content, 220)}
                                  </p>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-sm text-ink-2">No chunks found for this document.</p>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </Card>

          <div className="order-2 space-y-4">
            <Card>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="text-xl font-semibold tracking-tight text-ink">
                    {entriesSectionTitle}
                  </h3>
                  <p className="mt-1 text-sm text-muted">
                    {entriesSectionSummary}
                  </p>
                </div>
              </div>
            </Card>

          {isLoading ? (
            <Card>
              <p className="text-sm text-ink-2">Loading knowledge entries...</p>
            </Card>
          ) : entries.length === 0 ? (
            <Card>
              <div className="border border-dashed line-1 p-6 text-center">
                <h3 className="font-medium text-ink">
                  {activeSearch ? "No knowledge found for this search." : "No knowledge entries found."}
                </h3>
                <p className="mt-1 text-sm text-muted">
                  {activeSearch
                    ? "Try another term or clear the search to browse all active knowledge."
                    : "Add product details, pricing notes, FAQs, demo scripts, or uploaded documents to make AI drafts more specific."}
                </p>
              </div>
            </Card>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {entries.map((entry) => {
                const sourceLabel = getSourceLabel(entry);

                return (
                  <article key={entry.id} className="rounded-3xl border line-1 surface-2 p-5 elev-1">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={entry.is_active ? "success" : "neutral"}>
                            {entry.is_active ? "Active" : "Inactive"}
                          </Badge>
                          <Badge variant="neutral">{entry.category}</Badge>
                          <Badge variant={sourceLabel === "Document" ? "sent" : "neutral"}>
                            {sourceLabel}
                          </Badge>
                          {entry.retrieval_method && (
                            <Badge variant={entry.retrieval_method === "semantic" || entry.retrieval_method === "hybrid" ? "success" : "neutral"}>
                              {entry.retrieval_method}
                            </Badge>
                          )}
                        </div>
                        <h4 className="mt-3 break-words text-lg font-semibold text-ink">
                          {entry.title}
                        </h4>
                        {entry.tags && (
                          <p className="mt-1 break-words text-xs font-medium text-muted">
                            {entry.tags}
                          </p>
                        )}
                        {sourceLabel === "Document" && (
                          <p className="mt-2 break-words text-xs text-muted">
                            Source: Document - {entry.document_filename || `Document ID ${entry.document_id || "unknown"}`}
                            {entry.chunk_index ? ` - Chunk ${entry.chunk_index}` : ""}
                          </p>
                        )}
                        {entry.similarity_score !== null && entry.similarity_score !== undefined && (
                          <p className="mt-2 text-xs font-medium text-success">
                            Similarity: {Number(entry.similarity_score).toFixed(2)}
                          </p>
                        )}
                        {entry.keyword_score !== null && entry.keyword_score !== undefined && (
                          <p className="mt-1 text-xs font-medium text-ink-2">
                            Keyword score: {entry.keyword_score}
                          </p>
                        )}
                        {entry.match_reason && (
                          <p className="mt-1 break-words text-xs text-muted">
                            Match: {entry.match_reason}
                          </p>
                        )}
                      </div>
                    </div>

                    <p className="mt-4 whitespace-pre-line break-words text-sm leading-6 text-ink-2">
                      {getPreviewText(entry.content_preview || entry.content)}
                    </p>

                    <div className="mt-4 space-y-1 text-xs text-muted">
                      <p>Created: {formatDateTimeIST(entry.created_at)}</p>
                      {entry.updated_at && <p>Updated: {formatDateTimeIST(entry.updated_at)}</p>}
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button type="button" variant="secondary" size="sm" onClick={() => handleEdit(entry)}>
                        Edit
                      </Button>
                      {entry.is_active && (
                        <Button
                          type="button"
                          variant="danger"
                          size="sm"
                          disabled={deactivatingId === entry.id}
                          onClick={() => handleDeactivate(entry.id)}
                        >
                          {deactivatingId === entry.id ? "Deactivating..." : "Deactivate"}
                        </Button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Knowledge;
