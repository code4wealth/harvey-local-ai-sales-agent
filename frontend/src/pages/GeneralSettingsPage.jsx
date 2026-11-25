import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, Database, Download, FileJson, FileSpreadsheet, HardDrive, Import, LockKeyhole, RefreshCw, ShieldCheck, Upload, Workflow } from "lucide-react";
import { csvEscape } from "../data.js";
import { useWorkspace } from "../WorkspaceContext.jsx";
import { Icon, OfflineGuardBanner, PageHeader, SettingsSubnav, StatusPill } from "../ui.jsx";

const WORKSPACE_VERSION = "1.0.0";

function downloadFile(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Metric({ icon, label, value, note }) {
  return <article className="storage-metric-card"><span className="storage-metric-icon"><Icon as={icon} className="icon-md" /></span><div><span>{label}</span><strong className="mono-number">{value}</strong><small>{note}</small></div></article>;
}

export default function GeneralSettingsPage() {
  const { products, prospects, drafts, tasks, storageMetrics, apiState, apiStatus, previewMode, exportBackup, importBackup, notify } = useWorkspace();
  const [importError, setImportError] = useState("");
  const [importSuccess, setImportSuccess] = useState("");
  const [importing, setImporting] = useState(false);
  const inputRef = useRef(null);
  const counts = storageMetrics?.counts || {};
  const vectors = storageMetrics?.vectors || {};
  const totalVectors = storageMetrics?.vector_rows ?? Object.values(vectors).reduce((sum, value) => sum + Number(value || 0), 0);
  const exportJson = () => {
    const payload = exportBackup();
    downloadFile(`sellbird-workspace-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(payload, null, 2), "application/json");
    notify("Workspace JSON backup exported from local browser state.");
  };
  const exportCsv = () => {
    const columns = ["company_name", "contact_name", "contact_title", "company_domain", "employee_count", "contact_email", "score", "status", "industry", "summary", "product_id"];
    const rows = prospects.map((prospect) => ({ ...prospect, company_name: prospect.company, contact_name: prospect.contact, contact_title: prospect.role, company_domain: prospect.domain, employee_count: prospect.employeeCount, contact_email: prospect.email, product_id: prospect.productId }));
    const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => csvEscape(row[column])).join(","))].join("\r\n");
    downloadFile(`sellbird-prospects-${new Date().toISOString().slice(0, 10)}.csv`, csv, "text/csv;charset=utf-8");
    notify("Prospect CSV exported locally.");
  };
  const importJson = async (file) => {
    if (!file) return;
    setImporting(true);
    setImportError("");
    setImportSuccess("");
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("Backup is larger than 20 MB.");
      const backup = JSON.parse(await file.text());
      importBackup(backup);
      setImportSuccess("Backup loaded into this browser workspace as preview data. Existing SQLite records were not overwritten.");
    } catch (error) {
      setImportError(error.message || "This file could not be imported as a Sellbird workspace backup.");
    } finally {
      setImporting(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };
  const dbSize = storageMetrics?.file_bytes != null ? `${(Number(storageMetrics.file_bytes) / (1024 * 1024)).toFixed(1)} MB` : storageMetrics ? "Size not reported" : "Not connected";
  const localProductCount = counts.products ?? 0;
  const localProspectCount = counts.prospects ?? 0;
  const localQueueCount = previewMode ? tasks.filter((task) => task.isPreview).length : (counts.task_queue ?? tasks.length);
  const previewProductCount = products.filter((product) => product.isPreview).length;
  const previewProspectCount = prospects.filter((prospect) => prospect.isPreview).length;
  const gitCommit = apiStatus?.git_commit && apiStatus.git_commit !== "unknown" ? apiStatus.git_commit.slice(0, 8) : "Not reported";
  const localApiLabel = apiState === "ready" ? "LOCAL API CONNECTED" : apiState === "loading" ? "CHECKING LOCAL API" : "LOCAL API OFFLINE";
  const localApiStatus = apiState === "ready" ? "Connected" : apiState === "loading" ? "Running" : "Offline";
  const localReadiness = apiStatus?.local_readiness;
  const readinessPillStatus = apiState === "loading"
    ? "Running"
    : localReadiness?.ready
      ? "Ready"
      : localReadiness
        ? "Review"
        : apiState === "offline" ? "Offline" : "Not reported";
  const readinessPillLabel = apiState === "loading"
    ? "CHECKING READINESS"
    : localReadiness?.ready
      ? "LOCAL READY"
      : localReadiness
        ? "NOT READY"
        : "READINESS NOT REPORTED";
  return (
    <div className="page-stack">
      <PageHeader eyebrow="WORKSPACE SETTINGS · DATA BOUNDARIES" title="General Settings" subtitle="Manage local privacy, SQLite storage, and portable workspace backups." />
      <SettingsSubnav active="general" />
      <OfflineGuardBanner compact />
      <section className="privacy-hero-card" id="privacy-data"><span className="privacy-hero-icon"><Icon as={LockKeyhole} className="icon-lg" /></span><div><p className="page-eyebrow">LOCAL-FIRST BY DEFAULT</p><h2>Your sales workspace stays on this machine.</h2><p>Sellbird uses the local FastAPI service, SQLite, and Ollama. No cloud AI API is configured. Reply text and prospect source pages are not sent to a hosted model.</p><div className="privacy-check-list"><span><Icon as={Check} className="icon-xs" />Local SQLite storage</span><span><Icon as={Check} className="icon-xs" />Ollama at localhost:11434</span><span><Icon as={Check} className="icon-xs" />Draft-only email workflow</span></div></div><StatusPill status={localApiStatus}>{localApiLabel}</StatusPill></section>
      <section className="storage-overview-section"><div className="section-heading-row"><div><h2>Local storage overview</h2><p>Metrics are read from the local API. File paths are not exposed here.</p></div><Link to="/activity" className="text-link">View Activity Queue <Icon as={ArrowRight} className="icon-xs" /></Link></div><div className="storage-metrics-grid"><Metric icon={Database} label="Database engine" value={storageMetrics?.engine || "SQLite"} note={storageMetrics?.database_name || "Local database"} /><Metric icon={HardDrive} label="SQLite file size" value={dbSize} note="Database + WAL + SHM" /><Metric icon={FileSpreadsheet} label="SQLite products / prospects" value={`${Number(localProductCount).toLocaleString()} / ${Number(localProspectCount).toLocaleString()}`} note={previewMode ? `${previewProductCount} preview products · ${previewProspectCount} preview prospects` : "Persisted local records"} /><Metric icon={Workflow} label={previewMode ? "Preview task records" : "SQLite task queue rows"} value={Number(localQueueCount).toLocaleString()} note={previewMode ? "Illustrative records in this browser" : "Stored locally in SQLite"} /><Metric icon={ShieldCheck} label="Vector embeddings" value={Number(totalVectors).toLocaleString()} note="SQLite BLOB columns · no hosted vector service" /></div><div className="vector-detail-list"><span>Profile embeddings <strong className="mono-number">{vectors.business_profiles ?? 0}</strong></span><span>ICP embeddings <strong className="mono-number">{vectors.icps ?? 0}</strong></span><span>Prospect page embeddings <strong className="mono-number">{vectors.prospects ?? 0}</strong></span><span>Research embeddings <strong className="mono-number">{vectors.prospect_research ?? 0}</strong></span></div>{!storageMetrics && <p className="storage-api-note"><Icon as={RefreshCw} className="icon-xs" />Storage metrics unavailable until the local API is running. Preview counts are labeled and kept separate.</p>}</section>
      <div className="settings-data-grid"><section className="panel data-transfer-panel"><div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon panel-icon-brand"><Icon as={Download} className="icon-md" /></span><div><h2>Export workspace data</h2><p>Create a portable local backup or spreadsheet.</p></div></div></div><div className="transfer-option"><span className="transfer-file-icon"><Icon as={FileJson} className="icon-md" /></span><div><strong>Full workspace JSON</strong><small>Products, prospects, drafts, task state, and reply classifications from this browser.</small></div><button type="button" className="btn btn-secondary btn-sm" onClick={exportJson}>Export JSON</button></div><div className="transfer-option"><span className="transfer-file-icon transfer-file-green"><Icon as={FileSpreadsheet} className="icon-md" /></span><div><strong>Prospect CSV</strong><small>Company, contact, fit, status, and summary fields for the current workspace.</small></div><button type="button" className="btn btn-secondary btn-sm" onClick={exportCsv}>Export CSV</button></div><div className="transfer-safety-note"><Icon as={ShieldCheck} className="icon-xs" />Exports are generated in your browser and saved to your device.</div></section>
        <section className="panel data-import-panel"><div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon"><Icon as={Import} className="icon-md" /></span><div><h2>Import a workspace backup</h2><p>Select a backup to restore browser-local preview records.</p></div></div></div><div className="json-import-dropzone"><input ref={inputRef} className="sr-only" type="file" accept="application/json,.json" onChange={(event) => importJson(event.target.files?.[0])} /><span className="json-import-icon"><Icon as={Upload} className="icon-lg" /></span><strong>Choose a Sellbird JSON backup</strong><small>Maximum 20 MB · data is read in this browser</small><button type="button" className="btn btn-secondary btn-sm" onClick={() => inputRef.current?.click()} disabled={importing}>{importing ? "Reading backup…" : "Browse for JSON"}</button></div>{importError && <p className="form-error" role="alert">{importError}</p>}{importSuccess && <p className="form-success" role="status">{importSuccess}</p>}<div className="import-safety-note"><Icon as={ShieldCheck} className="icon-xs" /><span>JSON imports become browser preview records. They never overwrite local SQLite. For SQLite prospect imports, choose a locally stored product in the mapped CSV flow.</span></div><Link to="/prospects?import=true" className="text-link csv-import-link">Map and import a prospect CSV <Icon as={ArrowRight} className="icon-xs" /></Link></section></div>
      <section className="panel app-version-panel"><span className="version-logo"><span>SB</span></span><div className="version-main"><strong>Sellbird AI · Local Sales Workspace</strong><small>Workspace v{WORKSPACE_VERSION} · API v{apiStatus ? "0.1.0" : "not connected"}</small></div><div className="version-commit"><span>Build commit</span><code>{gitCommit}</code></div><StatusPill status={readinessPillStatus}>{readinessPillLabel}</StatusPill></section>
      <div className="settings-disclaimer"><Icon as={ShieldCheck} className="icon-sm" /><p><strong>Privacy boundaries.</strong> Local mode means requests go to the local FastAPI service. Browser-local preview data is illustrative, may be exported, and is distinct from persisted SQLite records. Email drafts are never sent.</p></div>
    </div>
  );
}
