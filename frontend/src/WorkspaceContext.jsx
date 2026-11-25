import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ACTIVITY_SERIES, SAMPLE_DRAFTS, SAMPLE_PRODUCTS, SAMPLE_PROSPECTS, SAMPLE_TASKS, csvEscape, parseCsv } from "./data.js";

const WorkspaceContext = createContext(null);
const STORAGE_KEY = "sellbird-local-workspace-v2";
export const MODEL_OPTIONS = ["qwen3:8b", "qwen3:4b"];

function readSavedWorkspace() {
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
    return value?.version === 2 ? value : null;
  } catch {
    return null;
  }
}

function messageFromResponse(data, text) {
  if (data && typeof data.detail === "string") return data.detail;
  if (data && typeof data.message === "string") return data.message;
  return text || "The local request failed.";
}

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (cause) {
    const error = new Error("The local API could not be reached. Keep the FastAPI workspace running.");
    error.cause = cause;
    error.status = 0;
    throw error;
  }
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const error = new Error(messageFromResponse(data, typeof data === "string" ? data : ""));
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function mapLocalProduct(row, cached = {}) {
  return {
    ...cached,
    id: String(row.id),
    name: row.name,
    company: cached.company || row.name,
    website: cached.website || "",
    pricing: cached.pricing || "Not configured",
    targetMarket: cached.targetMarket || "Define your target market",
    icpTags: cached.icpTags || [],
    description: row.description || cached.description || "",
    benefits: cached.benefits || [],
    icpCriteria: cached.icpCriteria || "Not configured",
    docsPath: row.docs_path || "",
    isSample: false,
    isImported: false,
    prospects: 0,
    researched: 0,
    drafts: Number(cached.drafts || 0),
    averageScore: 0,
    weeklyProspects: 0,
    isPreview: false,
  };
}

function mapLocalProspect(row) {
  return {
    id: String(row.id),
    productId: String(row.product_id),
    company: row.company_name || "Unnamed company",
    contact: row.contact_name || "Contact not provided",
    role: row.contact_title || "Role not provided",
    domain: row.company_domain || "",
    industry: "Not specified",
    score: Number(row.score || 0),
    updatedAt: row.updated_at || row.created_at || "Stored in SQLite",
    status: row.page_text_path ? "Awaiting Research" : "Awaiting Research",
    signals: 0,
    summary: row.page_text_path ? "Saved page text is ready for local research." : "No saved-page research has been recorded yet.",
    evidence: row.page_text_path ? `Saved local page text: ${row.page_text_path}` : "No local page text is stored for this prospect yet.",
    sourceLinks: row.page_text_path ? [`${row.page_text_path} · local file`] : [],
    pageTextPath: row.page_text_path || "",
    email: row.contact_email || "",
    employeeCount: row.employee_count ?? null,
    doNotContact: Boolean(row.do_not_contact),
    isPreview: false,
    isSample: false,
    isImported: false,
  };
}

function makePreviewProspect(record, productId, index) {
  const company = record.company_name || record.company || "Unnamed company";
  return {
    id: `P-${Date.now().toString().slice(-6)}-${index + 1}-${Math.random().toString(36).slice(2, 5).toUpperCase()}`,
    productId: String(productId),
    company,
    contact: record.contact_name || record.contact || "Contact not provided",
    role: record.contact_title || record.role || "Role not provided",
    domain: record.company_domain || record.domain || "",
    industry: record.industry || "Not specified",
    score: Number(record.score || 0),
    updatedAt: "Just imported · preview",
    status: "Queued",
    signals: 0,
    summary: "Imported to the browser preview. Use a SQLite-backed product to persist the record.",
    evidence: record.page_text_path ? `Local page path: ${record.page_text_path}` : "No saved local page text provided.",
    sourceLinks: record.page_text_path ? [`${record.page_text_path} · preview`] : [],
    email: record.contact_email || "",
    employeeCount: record.employee_count || null,
    isPreview: true,
    isSample: false,
    isImported: true,
  };
}

function classifyForPreview(text) {
  const content = text.toLowerCase();
  let label = "other";
  let rationale = "The preview text does not clearly match another reply category.";
  if (/unsubscribe|stop (?:email|contact|message)|remove me/.test(content)) {
    label = "unsubscribe";
    rationale = "The preview text asks to stop contact.";
  } else if (/out of office|out-of-office|away until|on leave/.test(content)) {
    label = "out_of_office";
    rationale = "The preview text indicates a temporary absence.";
  } else if (/not the right person|wrong person|contact .* instead|speak to .* instead/.test(content)) {
    label = "wrong_person";
    rationale = "The preview text points to a different contact.";
  } else if (/not interested|no thanks|not a fit|please don't/.test(content)) {
    label = "not_interested";
    rationale = "The preview text declines further contact.";
  } else if (/meet|meeting|calendar|schedule|available (?:on|at)/.test(content)) {
    label = "meeting_request";
    rationale = "The preview text suggests scheduling a conversation.";
  } else if (/question|how does|does your|can it|could you explain|\?/.test(content)) {
    label = "question";
    rationale = "The preview text asks for product or workflow details.";
  } else if (/interested|sounds good|send .* overview|would like to see|yes,? please/.test(content)) {
    label = "interested";
    rationale = "The preview text signals openness to learning more.";
  }
  return { label, confidence: 0.82, rationale, model_name: "Preview rules · not an Ollama run", isPreview: true };
}

export function WorkspaceProvider({ children }) {
  const [saved] = useState(readSavedWorkspace);
  const [products, setProducts] = useState(() => saved?.products?.length ? saved.products : SAMPLE_PRODUCTS);
  const [prospects, setProspects] = useState(() => saved?.prospects?.length ? saved.prospects : SAMPLE_PROSPECTS);
  const [tasks, setTasks] = useState(() => saved?.tasks?.length ? saved.tasks : SAMPLE_TASKS);
  const [drafts, setDrafts] = useState(() => saved?.drafts?.length ? saved.drafts : SAMPLE_DRAFTS);
  const [replyResults, setReplyResults] = useState(() => saved?.replyResults || []);
  const [activeModel, setActiveModelState] = useState(() => MODEL_OPTIONS.includes(saved?.activeModel) ? saved.activeModel : "qwen3:8b");
  const setActiveModel = useCallback((model) => {
    if (!MODEL_OPTIONS.includes(model)) return;
    setActiveModelState(model);
  }, []);
  const [demoOverride, setDemoOverride] = useState(() => typeof saved?.demoOverride === "boolean" ? saved.demoOverride : null);
  const [workspaceMode, setWorkspaceMode] = useState(() => saved?.workspaceMode || "preview");
  const [productFilter, setProductFilter] = useState(() => saved?.productFilter || "all");
  const [fitScoreThreshold, setFitScoreThreshold] = useState(() => Number.isFinite(saved?.fitScoreThreshold) ? Math.max(0, Math.min(100, saved.fitScoreThreshold)) : 75);
  const [signalConfidenceThreshold, setSignalConfidenceThreshold] = useState(() => Number.isFinite(saved?.signalConfidenceThreshold) ? Math.max(0, Math.min(100, saved.signalConfidenceThreshold)) : 50);
  const [apiStatus, setApiStatus] = useState(null);
  const [hardware, setHardware] = useState(null);
  const [storageMetrics, setStorageMetrics] = useState(null);
  const [apiState, setApiState] = useState("loading");
  const [liveConnected, setLiveConnected] = useState(false);
  const [toast, setToast] = useState("");
  const toastTimer = useRef(null);
  const taskTimers = useRef(new Map());

  const connected = demoOverride ?? liveConnected;
  const isDemoConnection = demoOverride !== null;
  const previewMode = workspaceMode === "preview";
  const activeTaskCount = tasks.filter((task) => ["Queued", "Running"].includes(task.status)).length;
  const savedDraftCount = products.reduce((total, product) => total + Number(product.drafts || 0), 0);

  const notify = useCallback((message) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 3200);
  }, []);

  const loadSystemStatus = useCallback(async () => {
    const [statusResult, hardwareResult, storageResult] = await Promise.allSettled([
      apiRequest("/api/status"),
      apiRequest("/api/hardware"),
      apiRequest("/api/storage"),
    ]);
    if (statusResult.status === "fulfilled") {
      setApiStatus(statusResult.value);
      setLiveConnected(statusResult.value?.ollama?.available === true);
      setApiState("ready");
    } else {
      setApiStatus(null);
      setApiState("offline");
      setLiveConnected(false);
    }
    if (hardwareResult.status === "fulfilled") setHardware(hardwareResult.value);
    else setHardware(null);
    if (storageResult.status === "fulfilled") setStorageMetrics(storageResult.value);
    else setStorageMetrics(null);
    return statusResult.status === "fulfilled" ? statusResult.value : null;
  }, []);

  const loadWorkspace = useCallback(async () => {
    const cachedMeta = Object.fromEntries((saved?.products || []).map((product) => [String(product.id), product]));
    try {
      const rows = await apiRequest("/api/products");
      if (Array.isArray(rows) && rows.length) {
        const mappedProducts = rows.map((row) => mapLocalProduct(row, cachedMeta[String(row.id)]));
        const perProduct = await Promise.all(mappedProducts.map(async (product) => {
          try {
            const records = await apiRequest(`/api/products/${encodeURIComponent(product.id)}/prospects`);
            const mappedProspects = records.map(mapLocalProspect);
            return {
              product: {
                ...product,
                prospects: mappedProspects.length,
                researched: mappedProspects.filter((prospect) => prospect.status === "Completed").length,
              },
              prospects: mappedProspects,
            };
          } catch {
            return { product, prospects: [] };
          }
        }));
        const localIds = new Set(mappedProducts.map((product) => String(product.id)));
        const localProducts = perProduct.map((entry) => entry.product);
        const localProspects = perProduct.flatMap((entry) => entry.prospects);
        const localProspectIds = new Set(localProspects.map((prospect) => String(prospect.id)));
        const cachedPreviewProducts = (saved?.products || []).filter((product) => product.isPreview && !localIds.has(String(product.id)));
        const cachedPreviewProspects = (saved?.prospects || []).filter((prospect) => prospect.isPreview && !localProspectIds.has(String(prospect.id)));
        const allProductIds = new Set([...localIds, ...cachedPreviewProducts.map((product) => String(product.id))]);
        setProducts([...localProducts, ...cachedPreviewProducts]);
        setProspects([...localProspects, ...cachedPreviewProspects]);
        setDrafts((current) => current.filter((draft) => allProductIds.has(String(draft.productId))));
        const hasBrowserPreview = cachedPreviewProducts.length > 0 || cachedPreviewProspects.length > 0;
        setWorkspaceMode(hasBrowserPreview ? "preview" : "local");
        if (!hasBrowserPreview) setTasks((current) => current.filter((task) => !task.isPreview));
      } else {
        const cachedPreviewProducts = saved?.products?.filter((product) => product.isPreview) || [];
        const cachedPreviewProspects = saved?.prospects?.filter((prospect) => prospect.isPreview) || [];
        setProducts(cachedPreviewProducts.length ? cachedPreviewProducts : SAMPLE_PRODUCTS);
        setProspects(cachedPreviewProspects.length ? cachedPreviewProspects : SAMPLE_PROSPECTS);
        setWorkspaceMode("preview");
      }
    } catch {
      const cachedPreviewProducts = saved?.products?.filter((product) => product.isPreview) || [];
      const cachedPreviewProspects = saved?.prospects?.filter((prospect) => prospect.isPreview) || [];
      setProducts(cachedPreviewProducts.length ? cachedPreviewProducts : SAMPLE_PRODUCTS);
      setProspects(cachedPreviewProspects.length ? cachedPreviewProspects : SAMPLE_PROSPECTS);
      setWorkspaceMode("preview");
    }
  }, [saved]);

  useEffect(() => {
    loadSystemStatus();
    loadWorkspace();
    return () => {
      window.clearTimeout(toastTimer.current);
      taskTimers.current.forEach((timer) => window.clearTimeout(timer));
      taskTimers.current.clear();
    };
  }, [loadSystemStatus, loadWorkspace]);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
        version: 2,
        products,
        prospects,
        tasks,
        drafts,
        replyResults,
        activeModel,
        demoOverride,
        workspaceMode,
        productFilter,
        fitScoreThreshold,
        signalConfidenceThreshold,
      }));
    } catch {
      // The workspace remains usable if browser storage is unavailable or full.
    }
  }, [products, prospects, tasks, drafts, replyResults, activeModel, demoOverride, workspaceMode, productFilter, fitScoreThreshold, signalConfidenceThreshold]);

  const toggleDemoConnection = useCallback(() => {
    const next = !connected;
    setDemoOverride(next);
    notify(next ? "Demo Ollama state: connected · no live inference was started." : "Demo Ollama state: offline · queued work remains local.");
  }, [connected, notify]);

  const setDemoConnection = useCallback((next) => {
    setDemoOverride(Boolean(next));
    notify(next ? "Demo Ollama state: connected · no live inference was started." : "Demo Ollama state: offline · queued work remains local.");
  }, [notify]);

  const resetDemoConnection = useCallback(() => {
    setDemoOverride(null);
    notify("Demo override reset · showing the current local Ollama health check.");
  }, [notify]);

  const testConnection = useCallback(async () => {
    setApiState("loading");
    setDemoOverride(null);
    const result = await loadSystemStatus();
    if (result?.ollama?.available === true) notify(`Ollama responded at localhost:11434 · ${result.ollama.model || activeModel}`);
    else notify("Local Ollama is unavailable right now. No cloud fallback is used.");
    return result;
  }, [activeModel, loadSystemStatus, notify]);

  const createProduct = useCallback(async (details) => {
    const normalized = {
      name: String(details.name || "").trim(),
      company: String(details.company || details.name || "").trim(),
      website: String(details.website || "").trim(),
      pricing: String(details.pricing || "Not configured").trim(),
      targetMarket: String(details.targetMarket || "Not configured").trim(),
      icpTags: Array.isArray(details.icpTags) ? details.icpTags : String(details.icpTags || "").split(",").map((tag) => tag.trim()).filter(Boolean),
      description: String(details.description || "").trim(),
      benefits: Array.isArray(details.benefits) ? details.benefits : String(details.benefits || "").split("\n").map((item) => item.trim()).filter(Boolean),
      icpCriteria: String(details.icpCriteria || "").trim(),
      docsPath: String(details.docsPath || "").trim(),
      prospects: 0,
      researched: 0,
      drafts: 0,
      averageScore: 0,
      weeklyProspects: 0,
    };
    if (!normalized.name) throw new Error("Product name is required.");
    try {
      const row = await apiRequest("/api/products", {
        method: "POST",
        body: JSON.stringify({ name: normalized.name, description: normalized.description, docs_path: normalized.docsPath }),
      });
      const product = { ...normalized, id: String(row.id), name: row.name, isPreview: false, isSample: false, isImported: false };
      setProducts((current) => [...current, product]);
      notify("Product created in local SQLite.");
      return product;
    } catch (error) {
      if (error.status) throw error;
      const product = { ...normalized, id: `preview-${Date.now()}`, isPreview: true, isSample: false, isImported: false };
      setProducts((current) => [...current, product]);
      notify("Product added to the browser preview; connect the local API to persist it in SQLite.");
      return product;
    }
  }, [notify]);

  const updateProduct = useCallback(async (productId, changes) => {
    const current = products.find((product) => String(product.id) === String(productId));
    if (!current) throw new Error("Product not found in this workspace.");
    const updated = { ...current, ...changes };
    if (!current.isPreview) {
      try {
        const row = await apiRequest(`/api/products/${encodeURIComponent(productId)}`, {
          method: "PUT",
          body: JSON.stringify({ name: updated.name, description: updated.description || "", docs_path: updated.docsPath || "" }),
        });
        updated.name = row.name;
        updated.description = row.description;
        updated.docsPath = row.docs_path;
      } catch (error) {
        if (error.status) throw error;
      }
    }
    setProducts((items) => items.map((product) => String(product.id) === String(productId) ? updated : product));
    notify(current.isPreview ? "Preview product details saved in this browser." : "Product record updated in local SQLite.");
    return updated;
  }, [products, notify]);

  const deleteProduct = useCallback(async (productId) => {
    const product = products.find((item) => String(item.id) === String(productId));
    if (!product) return;
    if (!product.isPreview) await apiRequest(`/api/products/${encodeURIComponent(productId)}`, { method: "DELETE" });
    setProducts((items) => items.filter((item) => String(item.id) !== String(productId)));
    setProspects((items) => items.filter((prospect) => String(prospect.productId) !== String(productId)));
    setDrafts((items) => items.filter((draft) => String(draft.productId) !== String(productId)));
    notify(product.isPreview ? "Preview product removed from this browser." : "Product and its local records were removed.");
  }, [products, notify]);

  const importProspectsCsv = useCallback(async (productId, csvText, parsed = null) => {
    const product = products.find((item) => String(item.id) === String(productId));
    if (!product) throw new Error("Choose a product before importing prospects.");
    const normalized = parsed || parseCsv(csvText);
    if (!normalized.rows.length) throw new Error("CSV has a header row but no prospect records.");
    if (product.isPreview) {
      const additions = normalized.rows.map((row, index) => makePreviewProspect(row, productId, index));
      setProspects((current) => [...additions, ...current]);
      setProducts((current) => current.map((item) => String(item.id) === String(productId) ? { ...item, prospects: item.prospects + additions.length } : item));
      notify(`${additions.length} prospect${additions.length === 1 ? "" : "s"} added to preview data only.`);
      return { imported: additions.length, skipped: 0, preview: true };
    }
    const result = await apiRequest(`/api/products/${encodeURIComponent(productId)}/prospects/import`, {
      method: "POST",
      headers: { "Content-Type": "text/csv; charset=utf-8" },
      body: csvText,
    });
    const rows = await apiRequest(`/api/products/${encodeURIComponent(productId)}/prospects`);
    const mapped = rows.map(mapLocalProspect);
    setProspects((current) => [...current.filter((prospect) => String(prospect.productId) !== String(productId)), ...mapped]);
    setProducts((current) => current.map((item) => String(item.id) === String(productId) ? { ...item, prospects: mapped.length } : item));
    notify(`${result.imported} imported · ${result.skipped} duplicate${result.skipped === 1 ? "" : "s"} skipped in SQLite.`);
    return result;
  }, [products, notify]);

  const addProspect = useCallback(async (productId, details) => {
    const fields = ["company_name", "contact_name", "contact_title", "company_domain", "employee_count", "contact_email", "page_text_path", "do_not_contact"];
    const values = {
      company_name: details.company || "",
      contact_name: details.contact || "",
      contact_title: details.role || "",
      company_domain: details.domain || "",
      employee_count: details.employeeCount || "",
      contact_email: details.email || "",
      page_text_path: details.pageTextPath || "",
      do_not_contact: details.doNotContact ? "true" : "false",
    };
    const csv = `${fields.join(",")}\r\n${fields.map((field) => csvEscape(values[field])).join(",")}`;
    return importProspectsCsv(productId, csv, { headers: fields, rows: [values] });
  }, [importProspectsCsv]);

  const saveDraft = useCallback((draft) => {
    const isExistingDraft = Boolean(draft.id && drafts.some((item) => String(item.id) === String(draft.id)));
    const isPersisted = Boolean(draft.isPersisted && draft.backendDraftId);
    const savedDraft = {
      ...draft,
      isPersisted,
      backendDraftId: isPersisted ? draft.backendDraftId : null,
      id: draft.id || `D-${Date.now().toString().slice(-6)}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
      savedAt: new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" }),
    };
    setDrafts((current) => [savedDraft, ...current.filter((item) => item.id !== savedDraft.id)]);
    if (!isExistingDraft && !isPersisted) {
      setProducts((current) => current.map((product) => String(product.id) === String(savedDraft.productId) ? { ...product, drafts: Number(product.drafts || 0) + 1 } : product));
    }
    notify(savedDraft.isPreview ? "Preview Email Draft saved in this browser · never sent." : isPersisted ? "Email Draft is stored in local SQLite · never sent." : "Email Draft saved in this browser · never sent.");
    return savedDraft;
  }, [drafts, notify]);

  const runPreviewTask = useCallback(({ title, type, productId, prospectId, detail, isSample = false, isImported = false }) => {
    const task = {
      id: `TASK-${Date.now().toString().slice(-6)}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
      title,
      type,
      productId: String(productId || ""),
      prospectId: String(prospectId || ""),
      status: "Running",
      duration: "00:00",
      detail: detail || "Local preview task is running.",
      updatedAt: "Running now",
      isPreview: true,
      isSample,
      isImported,
    };
    setTasks((current) => [task, ...current]);
    const timer = window.setTimeout(() => {
      setTasks((current) => current.map((item) => item.id === task.id ? { ...item, status: "Completed", duration: "00:02", updatedAt: "Just now", detail: "Preview task completed locally; no inference was performed." } : item));
      if (prospectId) {
        setProspects((current) => current.map((prospect) => String(prospect.id) === String(prospectId) ? { ...prospect, status: "Completed", updatedAt: "Just now · preview" } : prospect));
      }
      taskTimers.current.delete(task.id);
      notify("Preview task completed · no live inference was performed.");
    }, 1400);
    taskTimers.current.set(task.id, timer);
    return task;
  }, [notify]);

  const retryTask = useCallback(async (taskId) => {
    const failed = tasks.filter((task) => (!taskId || task.id === taskId) && task.status === "Failed");
    const simulatedFailures = failed.filter((task) => isDemoConnection || task.isPreview);
    const liveFailures = failed.filter((task) => !isDemoConnection && !task.isPreview);

    if (simulatedFailures.length) {
      setTasks((current) => current.map((task) => simulatedFailures.some((item) => item.id === task.id)
        ? { ...task, status: "Running", isPreview: true, isSample: false, updatedAt: "Preview simulation", detail: "Demo-only retry simulation; no worker or model was invoked." }
        : task));
      simulatedFailures.forEach((task) => {
        const timer = window.setTimeout(() => {
          setTasks((current) => current.map((item) => item.id === task.id
            ? { ...item, status: "Completed", duration: "00:02", isPreview: true, updatedAt: "Just now · preview", detail: "Preview retry simulation completed; no inference or live worker was run." }
            : item));
          taskTimers.current.delete(task.id);
          notify("Preview retry simulation completed · no live task was run.");
        }, 1400);
        taskTimers.current.set(task.id, timer);
      });
    }

    if (isDemoConnection) {
      if (!simulatedFailures.length) notify("Demo override is UI-only · the live task queue was not retried.");
      return;
    }

    const liveFailedCount = Number(apiStatus?.queue?.failed || 0);
    const hasLiveQueueFailures = apiState === "ready" && !taskId && liveFailedCount > 0;
    if (!liveFailures.length && !hasLiveQueueFailures) {
      if (failed.length && !simulatedFailures.length) notify("No failed live queue item is currently reported.");
      return;
    }
    if (!liveConnected) {
      notify("Local Ollama is offline · no live retry was submitted. Start Ollama, then retry the queue.");
      return;
    }
    try {
      await apiRequest("/api/queue/retry", { method: "POST" });
      setTasks((current) => current.map((task) => liveFailures.some((item) => item.id === task.id)
        ? { ...task, status: "Queued", updatedAt: "Retry requested", detail: "Retry request submitted to the local SQLite queue; completion is reflected by live queue counts." }
        : task));
      await loadSystemStatus();
      notify("Retry request submitted to the local SQLite queue · check live queue counts for progress.");
    } catch (error) {
      notify(`Local queue retry failed: ${error.message}`);
    }
  }, [apiState, apiStatus, isDemoConnection, liveConnected, loadSystemStatus, tasks, notify]);

  const runResearch = useCallback(async (prospect) => {
    if (!connected) throw new Error("Ollama is offline. Start the local service or use the demo toggle in Model Settings.");
    const product = products.find((item) => String(item.id) === String(prospect.productId));
    if (!isDemoConnection && liveConnected && !prospect.isPreview && !product?.isPreview) {
      const result = await apiRequest(`/api/prospects/${encodeURIComponent(prospect.id)}/signals?model=${encodeURIComponent(activeModel)}`, { method: "POST" });
      setTasks((current) => [{ id: `TASK-${result.queue_task_id || Date.now()}`, title: `Local research · ${prospect.company}`, type: "Qwen3 research", productId: prospect.productId, prospectId: prospect.id, status: result.status === "queued" ? "Queued" : "Running", duration: "—", detail: result.error || "Research submitted to the local workflow.", updatedAt: "Just now", isPreview: false }, ...current]);
      notify(result.status === "queued" ? "Research is queued in local SQLite." : "Research sent to the local workflow.");
      return result;
    }
    const task = runPreviewTask({ title: `Prospect research · ${prospect.company}`, type: "Qwen3 research", productId: prospect.productId, prospectId: prospect.id, detail: "Preview research is processing saved-page context.", isSample: prospect.isSample, isImported: prospect.isImported });
    notify(isDemoConnection ? "Demo research started · no local model call was made." : "Preview research started.");
    return task;
  }, [activeModel, connected, isDemoConnection, liveConnected, products, runPreviewTask, notify]);

  const classifyReply = useCallback(async (text, prospectId, metadata = {}) => {
    if (!String(text || "").trim()) throw new Error("Enter a customer reply to classify.");
    if (!connected) throw new Error("Ollama is offline. Connect the local service or turn on the demo toggle.");
    if (!isDemoConnection && liveConnected) {
      const result = await apiRequest("/api/replies/classify-text", {
        method: "POST",
        body: JSON.stringify({ text, model: activeModel }),
      });
      const classification = { ...result, text: String(text), prospectId: String(prospectId || ""), createdAt: new Date().toISOString(), isPreview: false, isSample: Boolean(metadata.isSample), isImported: Boolean(metadata.isImported) };
      setReplyResults((current) => [classification, ...current]);
      return classification;
    }
    const classification = { ...classifyForPreview(text), text: String(text), prospectId: String(prospectId || ""), createdAt: new Date().toISOString(), isSample: Boolean(metadata.isSample), isImported: Boolean(metadata.isImported) };
    setReplyResults((current) => [classification, ...current]);
    return classification;
  }, [activeModel, connected, isDemoConnection, liveConnected]);

  const createEmailDraft = useCallback(async (prospect) => {
    if (!connected) throw new Error("Ollama is offline. Start local Ollama or use the demo toggle in Model Settings.");
    const product = products.find((item) => String(item.id) === String(prospect.productId));
    if (!isDemoConnection && liveConnected && !prospect.isPreview && !product?.isPreview) {
      return apiRequest(`/api/products/${encodeURIComponent(prospect.productId)}/prospects/${encodeURIComponent(prospect.id)}/draft?model=${encodeURIComponent(activeModel)}`, { method: "POST" });
    }
    return {
      subject: `A question about ${prospect.company}'s workflow`,
      body: `Hi ${prospect.contact?.split(" ")[0] || "there"},\n\nI noticed ${prospect.summary || "your recent team priorities"}. I have a concise overview of how a local-first research workflow can help your team keep evidence close and drafts reviewable.\n\nWould it be useful to take a look?\n\nBest,\nYour name`,
      evidence_used: prospect.summary || "Preview sample context · verify before use.",
      isPreview: true,
    };
  }, [activeModel, connected, isDemoConnection, liveConnected, products]);

  const importBackup = useCallback((backup) => {
    const isRecordList = (value) => Array.isArray(value) && value.every((item) => item && typeof item === "object" && !Array.isArray(item));
    if (!backup || backup.format !== "sellbird-workspace" || !isRecordList(backup.products) || !isRecordList(backup.prospects)) {
      throw new Error("This file is not a valid Sellbird workspace backup.");
    }
    for (const key of ["tasks", "drafts", "replyResults"]) {
      if (backup[key] !== undefined && !isRecordList(backup[key])) throw new Error(`Backup field ${key} must be a list of records.`);
    }
    const productIdMap = new Map(backup.products.map((product, index) => [String(product.id ?? index), `backup-product-${index + 1}`]));
    const prospectIdMap = new Map(backup.prospects.map((prospect, index) => [String(prospect.id ?? index), `backup-prospect-${index + 1}`]));
    const importedProducts = backup.products.map((product, index) => ({
      ...product,
      id: `backup-product-${index + 1}`,
      name: String(product.name || `Imported product ${index + 1}`),
      icpTags: Array.isArray(product.icpTags) ? product.icpTags : [],
      benefits: Array.isArray(product.benefits) ? product.benefits : [],
      isPreview: true,
      isSample: false,
      isImported: true,
    }));
    const importedProspects = backup.prospects.map((prospect, index) => ({
      ...prospect,
      id: `backup-prospect-${index + 1}`,
      productId: productIdMap.get(String(prospect.productId ?? "")) || String(prospect.productId ?? ""),
      company: String(prospect.company || "Unnamed imported company"),
      contact: String(prospect.contact || "Contact not provided"),
      role: String(prospect.role || "Role not provided"),
      industry: String(prospect.industry || "Not specified"),
      summary: String(prospect.summary || "Imported record; no local synthesis is available."),
      evidence: String(prospect.evidence || "No source evidence was included in this backup."),
      sourceLinks: Array.isArray(prospect.sourceLinks) ? prospect.sourceLinks : [],
      score: Number(prospect.score || 0),
      isPreview: true,
      isSample: false,
      isImported: true,
    }));
    const importedTasks = (backup.tasks || []).map((task, index) => ({
      ...task,
      id: `backup-task-${index + 1}`,
      productId: productIdMap.get(String(task.productId ?? "")) || String(task.productId ?? ""),
      prospectId: prospectIdMap.get(String(task.prospectId ?? "")) || String(task.prospectId ?? ""),
      title: String(task.title || "Imported local task"),
      type: String(task.type || "Local workflow"),
      status: String(task.status || "Queued"),
      detail: String(task.detail || "No task detail in this backup."),
      isPreview: true,
      isSample: false,
      isImported: true,
    }));
    const importedDrafts = (backup.drafts || []).map((draft, index) => ({
      ...draft,
      id: `backup-draft-${index + 1}`,
      productId: productIdMap.get(String(draft.productId ?? "")) || String(draft.productId ?? ""),
      prospectId: prospectIdMap.get(String(draft.prospectId ?? "")) || String(draft.prospectId ?? ""),
      subject: String(draft.subject || "Imported Email Draft"),
      body: String(draft.body || ""),
      isPersisted: false,
      backendDraftId: null,
      isPreview: true,
      isSample: false,
      isImported: true,
    }));
    const importedReplies = (backup.replyResults || []).map((reply, index) => ({
      ...reply,
      id: `backup-reply-${index + 1}`,
      prospectId: prospectIdMap.get(String(reply.prospectId ?? "")) || String(reply.prospectId ?? ""),
      text: String(reply.text || ""),
      isPreview: true,
      isSample: false,
      isImported: true,
    }));
    setProducts((current) => [...current.filter((product) => !product.isPreview), ...importedProducts]);
    setProspects((current) => [...current.filter((prospect) => !prospect.isPreview), ...importedProspects]);
    setTasks((current) => [...current.filter((task) => !task.isPreview), ...importedTasks]);
    setDrafts((current) => [...current.filter((draft) => !draft.isPreview), ...importedDrafts]);
    setReplyResults((current) => [...current.filter((reply) => !reply.isPreview), ...importedReplies]);
    if (MODEL_OPTIONS.includes(backup.activeModel)) setActiveModel(backup.activeModel);
    if (Number.isFinite(backup.fitScoreThreshold)) setFitScoreThreshold(Math.max(0, Math.min(100, backup.fitScoreThreshold)));
    if (Number.isFinite(backup.signalConfidenceThreshold)) setSignalConfidenceThreshold(Math.max(0, Math.min(100, backup.signalConfidenceThreshold)));
    setProductFilter("all");
    setWorkspaceMode("preview");
    notify("Backup imported as browser preview records. Existing SQLite records were not changed.");
  }, [notify, setActiveModel]);

  const exportBackup = useCallback(() => ({
    format: "sellbird-workspace",
    version: 2,
    exportedAt: new Date().toISOString(),
    storage: "browser-local-workspace",
    products,
    prospects,
    tasks,
    drafts,
    replyResults,
    activeModel,
    fitScoreThreshold,
    signalConfidenceThreshold,
  }), [products, prospects, tasks, drafts, replyResults, activeModel, fitScoreThreshold, signalConfidenceThreshold]);

  const value = useMemo(() => ({
    products,
    prospects,
    tasks,
    drafts,
    replyResults,
    activeModel,
    setActiveModel,
    connected,
    liveConnected,
    isDemoConnection,
    demoOverride,
    toggleDemoConnection,
    setDemoConnection,
    resetDemoConnection,
    testConnection,
    apiStatus,
    apiState,
    hardware,
    storageMetrics,
    workspaceMode,
    previewMode,
    productFilter,
    setProductFilter,
    fitScoreThreshold,
    setFitScoreThreshold,
    signalConfidenceThreshold,
    setSignalConfidenceThreshold,
    activeTaskCount,
    savedDraftCount,
    toast,
    notify,
    createProduct,
    updateProduct,
    deleteProduct,
    importProspectsCsv,
    addProspect,
    saveDraft,
    retryTask,
    runResearch,
    classifyReply,
    createEmailDraft,
    importBackup,
    exportBackup,
    refreshWorkspace: loadWorkspace,
    refreshStatus: loadSystemStatus,
  }), [
    products, prospects, tasks, drafts, replyResults, activeModel, connected, liveConnected, isDemoConnection, demoOverride,
    toggleDemoConnection, setDemoConnection, resetDemoConnection, testConnection, apiStatus, apiState, hardware, storageMetrics, workspaceMode, previewMode, productFilter, fitScoreThreshold, signalConfidenceThreshold,
    activeTaskCount, savedDraftCount, toast, notify, createProduct, updateProduct, deleteProduct, importProspectsCsv, addProspect,
    saveDraft, retryTask, runResearch, classifyReply, createEmailDraft, importBackup, exportBackup, loadWorkspace, loadSystemStatus,
  ]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("useWorkspace must be used inside WorkspaceProvider.");
  return context;
}
