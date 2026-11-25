import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowRight, BarChart3, Boxes, Cpu, Database, Download, FileSearch, HardDrive, MailPlus, Plus, Users } from "lucide-react";
import { ACTIVITY_SERIES } from "../data.js";
import { useWorkspace } from "../WorkspaceContext.jsx";
import { AiPriorityCard, CircularScoreRing, DataTable, Icon, KeyValueConfigPanel, KpiMetricCard, OfflineGuardBanner, PageHeader, StatusPill, SubsystemConnectionList } from "../ui.jsx";

function downloadFile(filename, content, type) {
  const url = window.URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

function ExportMenu({ prospects }) {
  const [open, setOpen] = useState(false);
  const columns = ["company", "contact", "role", "domain", "industry", "score", "status", "summary"];
  const exportAs = (format) => {
    const today = new Date().toISOString().slice(0, 10);
    if (format === "json") {
      downloadFile(`sellbird-prospects-${today}.json`, JSON.stringify(prospects, null, 2), "application/json");
    } else {
      const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
      const body = [columns.join(","), ...prospects.map((row) => columns.map((column) => escape(row[column])).join(","))].join("\r\n");
      downloadFile(`sellbird-prospects-${today}.csv`, body, "text/csv;charset=utf-8");
    }
    setOpen(false);
  };
  return (
    <div className="dropdown-wrap">
      <button type="button" className="btn btn-secondary" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <Icon as={Download} className="icon-sm" />Export CSV / JSON
      </button>
      {open && <div className="dropdown-menu"><p className="dropdown-label">EXPORT LOCAL WORKSPACE DATA</p><button type="button" onClick={() => exportAs("csv")}>Download prospects as CSV</button><button type="button" onClick={() => exportAs("json")}>Download prospects as JSON</button></div>}
    </div>
  );
}

function ActivityChart({ previewMode }) {
  const [range, setRange] = useState("Last 7 days");
  const [hovered, setHovered] = useState(null);
  const [showResearch, setShowResearch] = useState(true);
  const [showDrafts, setShowDrafts] = useState(true);
  const data = ACTIVITY_SERIES[range];
  const maximum = Math.max(...data.flatMap((point) => [showResearch ? point.researched : 0, showDrafts ? point.drafts : 0]), 10);
  if (!previewMode) return (
    <section className="panel chart-panel activity-history-unreported" aria-labelledby="activity-chart-heading">
      <div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon"><Icon as={BarChart3} className="icon-md" /></span><div><h2 id="activity-chart-heading">Activity history</h2><p>Historical analytics are not reported by the local API</p></div></div><StatusPill status="Not reported">NOT REPORTED</StatusPill></div>
      <p>The local service exposes current queue and storage health, but no daily activity time series. Sellbird does not infer historical trends from the current snapshot.</p>
    </section>
  );
  return (
    <section className="panel chart-panel" aria-labelledby="activity-chart-heading">
      <div className="panel-heading panel-heading-wrap">
        <div className="panel-title-with-icon"><span className="panel-icon"><Icon as={BarChart3} className="icon-md" /></span><div><h2 id="activity-chart-heading">Research &amp; Email Draft Velocity</h2><p>Illustrative preview series · not live analytics</p></div></div>
        <label className="range-select-label"><span className="sr-only">Activity date range</span><select className="select-compact" value={range} onChange={(event) => { setRange(event.target.value); setHovered(null); }}><option>Last 7 days</option><option>Last 30 days</option></select></label>
      </div>
      <div className="chart-toolbar">
        <span className="chart-toolbar-label">Show series</span>
        <button type="button" className={`chart-legend-toggle ${showResearch ? "chart-toggle-active" : ""}`} aria-pressed={showResearch} onClick={() => setShowResearch((value) => !value)}><span className="legend-dot legend-dot-brand" />Prospects Researched</button>
        <button type="button" className={`chart-legend-toggle ${showDrafts ? "chart-toggle-active" : ""}`} aria-pressed={showDrafts} onClick={() => setShowDrafts((value) => !value)}><span className="legend-dot legend-dot-green" />Email Drafts Generated</button>
      </div>
      <div className="grouped-chart" onMouseLeave={() => setHovered(null)} role="group" aria-label={`${range} grouped research and email draft chart`}>
        <div className="chart-y-labels" aria-hidden="true"><span>{maximum}</span><span>{Math.round(maximum * .75)}</span><span>{Math.round(maximum * .5)}</span><span>{Math.round(maximum * .25)}</span><span>0</span></div>
        <div className="chart-plot">
          {[0, 1, 2, 3, 4].map((line) => <span key={line} className="chart-gridline" style={{ top: `${line * 25}%` }} />)}
          <div className="chart-columns">
            {data.map((point, index) => {
              const isActive = hovered === index;
              return (
                <button
                  key={point.label}
                  type="button"
                  className={`chart-column ${isActive ? "chart-column-active" : ""}`}
                  onMouseEnter={() => setHovered(index)}
                  onFocus={() => setHovered(index)}
                  onClick={() => setHovered(isActive ? null : index)}
                  aria-label={`${point.label}: ${showResearch ? `Prospects Researched ${point.researched}` : "Research hidden"}, ${showDrafts ? `Email Drafts Generated ${point.drafts}` : "Email Drafts hidden"}`}
                  aria-pressed={isActive}
                >
                  <span className="chart-bar-group">
                    {showResearch && <span className="chart-bar-unit"><span className="chart-value-label mono-number">{point.researched}</span><span className="chart-bar chart-bar-brand" style={{ height: `${(point.researched / maximum) * 100}%` }} /></span>}
                    {showDrafts && <span className="chart-bar-unit"><span className="chart-value-label mono-number">{point.drafts}</span><span className="chart-bar chart-bar-green" style={{ height: `${(point.drafts / maximum) * 100}%` }} /></span>}
                  </span>
                  <span className="chart-x-label">{point.label}</span>
                  {isActive && <span className="chart-tooltip"><strong>{point.label}</strong><span>Researched <b>{point.researched}</b></span><span>Email Drafts <b>{point.drafts}</b></span></span>}
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="chart-footnote"><span><span className="legend-dot legend-dot-brand" />Research</span><span><span className="legend-dot legend-dot-green" />Email Drafts</span><span className="chart-sample-note">Illustrative sample only · hover or focus a day for details</span></div>
    </section>
  );
}

function SubsystemHealthPanel() {
  const { tasks, activeTaskCount, connected, isDemoConnection, activeModel, apiStatus, apiState, storageMetrics, previewMode } = useWorkspace();
  const vectorCount = Number(storageMetrics?.vector_rows ?? Object.values(storageMetrics?.vectors || {}).reduce((sum, value) => sum + Number(value || 0), 0));
  const bytes = Number(storageMetrics?.file_bytes || 0);
  const databaseSize = bytes > 0 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : "Not reported";
  const queue = apiStatus?.queue || {};
  const queueMetricsAvailable = queue.running != null || queue.queued != null;
  const localQueueCount = tasks.filter((task) => ["Queued", "Running"].includes(task.status)).length;
  const displayedRunning = previewMode ? activeTaskCount : queueMetricsAvailable ? Number(queue.running || 0) : "—";
  const displayedQueued = previewMode ? localQueueCount : queueMetricsAvailable ? Number(queue.queued || 0) : "—";
  const ollamaStatus = isDemoConnection ? connected ? "Demo connected" : "Demo offline" : apiState === "loading" ? "Checking" : apiStatus?.ollama?.available === true ? "Connected" : apiStatus?.ollama?.state === "slow" ? "Slow" : "Offline";
  const ollamaTone = isDemoConnection || apiState === "loading" || apiStatus?.ollama?.state === "slow" ? "warning" : apiStatus?.ollama?.available === true ? "success" : "danger";
  const items = [
    { icon: Cpu, title: "Ollama Local LLM", detail: `${(apiStatus?.ollama?.url || "http://localhost:11434").replace("http://", "").replace("https://", "")} · selected ${activeModel}${isDemoConnection ? " · UI-only override" : ""}`, status: ollamaStatus, tone: ollamaTone, ...(!connected || isDemoConnection ? { actionLabel: "+ Configure", to: "/settings/models" } : {}) },
    { icon: FileSearch, title: "Playwright Web Scraper", detail: "No live scraper health endpoint is reported; saved source text remains on-device", status: "Not reported", tone: "neutral", actionLabel: "+ Review", to: "/prospects" },
    { icon: Activity, title: "Local Vector Index", detail: vectorCount ? `${vectorCount.toLocaleString()} SQLite embedding rows` : "Optional index · no embeddings recorded", status: vectorCount ? "Indexed" : "Not indexed", tone: vectorCount ? "success" : "neutral", ...(!vectorCount ? { actionLabel: "+ Review", to: "/settings/general" } : {}) },
    { icon: Database, title: "SQLite Storage", detail: `${storageMetrics?.database_name || "harvey.db"} · ${databaseSize}${previewMode ? " · preview data separate" : ""}`, status: storageMetrics ? "Ready" : apiState === "loading" ? "Checking" : "Unavailable", tone: storageMetrics ? "success" : apiState === "loading" ? "warning" : "danger", ...(!storageMetrics ? { actionLabel: "+ Review", to: "/settings/general" } : {}) },
  ];
  return (
    <section className="panel dashboard-subsystems-panel" aria-labelledby="subsystems-heading">
      <div className="panel-heading"><div><h2 id="subsystems-heading">Local Subsystem &amp; Queue Health</h2><p>{previewMode ? "Preview task state is separate from live SQLite health" : "On-device services · no cloud APIs are used"}</p></div></div>
      <SubsystemConnectionList items={items} />
      <div className="dashboard-queue-summary flex items-center gap-2"><span className={`engine-status-light ${previewMode ? "is-checking" : queueMetricsAvailable ? "is-online" : "is-checking"}`} /><span><strong>{displayedRunning}</strong> {previewMode ? "active preview tasks" : "running in SQLite queue"}</span><span className="mono-number">{displayedQueued} {previewMode ? "preview queued" : "queued"}</span></div>
      <Link className="dashboard-queue-link text-brand-500" to="/activity">View Task Queue <Icon as={ArrowRight} className="icon-xs" /></Link>
    </section>
  );
}

function RuntimeTopologyPanels() {
  const { isDemoConnection, activeModel, apiStatus, apiState, hardware, storageMetrics, tasks, previewMode } = useWorkspace();
  const queue = apiStatus?.queue || {};
  const vectorCount = Number(storageMetrics?.vector_rows ?? Object.values(storageMetrics?.vectors || {}).reduce((sum, value) => sum + Number(value || 0), 0));
  const endpoint = String(apiStatus?.ollama?.url || "Not reported").replace("http://", "").replace("https://", "").replace("127.0.0.1", "localhost").replace("0.0.0.0", "localhost") || "Not reported";
  const ollamaAvailable = apiStatus?.ollama?.available === true;
  const ollamaSlow = apiStatus?.ollama?.state === "slow";
  const apiTone = apiState === "ready" ? "success" : apiState === "loading" ? "warning" : "danger";
  const ollamaTone = isDemoConnection || apiState === "loading" || ollamaSlow ? "warning" : ollamaAvailable ? "success" : "danger";
  const localQueueCount = tasks.filter((task) => ["Queued", "Running"].includes(task.status)).length;
  const queueMetricsAvailable = apiState === "ready" && (queue.running != null || queue.queued != null);
  const liveQueueLabel = queueMetricsAvailable
    ? `${Number(queue.running || 0)} running · ${Number(queue.queued || 0)} queued`
    : "No live queue metrics reported";
  const queueStatus = previewMode ? "Preview only" : !queueMetricsAvailable ? "Not reported" : Number(queue.running || 0) ? "Running" : Number(queue.queued || 0) ? "Queued" : "Idle";
  const queueTone = previewMode ? "warning" : !queueMetricsAvailable ? "neutral" : Number(queue.running || 0) ? "success" : Number(queue.queued || 0) ? "brand" : "neutral";
  const queueLabel = previewMode ? `${localQueueCount} illustrative active / queued tasks` : liveQueueLabel;
  const hardwareLabel = hardware?.ram_gb != null
    ? `${hardware.ram_gb} GB RAM · ${hardware.cpu_count ?? "—"} CPU cores`
    : "Not reported by the local API";
  const databaseSize = storageMetrics?.file_bytes
    ? `${(Number(storageMetrics.file_bytes) / (1024 * 1024)).toFixed(1)} MB`
    : "Size not reported";
  const topologyItems = [
    { icon: Database, title: "FastAPI workspace", detail: apiState === "ready" ? "Status endpoint responded on this machine" : apiState === "loading" ? "Checking /api/status" : "Local API status is unavailable", status: apiState === "ready" ? "Connected" : apiState === "loading" ? "Checking" : "Offline", tone: apiTone, actionLabel: apiState !== "ready" ? "+ Review" : undefined, to: "/settings/general" },
    { icon: Cpu, title: "Ollama inference", detail: isDemoConnection ? "UI demo override · no model call is made" : `${endpoint} · model availability is reported separately`, status: isDemoConnection ? "Demo connected" : apiState === "loading" ? "Checking" : ollamaSlow ? "Slow" : ollamaAvailable ? "Connected" : "Offline", tone: ollamaTone, actionLabel: !ollamaAvailable || isDemoConnection ? "+ Configure" : undefined, to: "/settings/models" },
    { icon: HardDrive, title: "SQLite workspace", detail: storageMetrics ? `${storageMetrics.database_name || "Local database"} · ${databaseSize}` : "Local storage metrics are not available", status: storageMetrics ? "Available" : apiState === "loading" ? "Checking" : "Unavailable", tone: storageMetrics ? "success" : apiState === "loading" ? "warning" : "danger", actionLabel: !storageMetrics ? "+ Review" : undefined, to: "/settings/general" },
    { icon: Activity, title: previewMode ? "Browser preview queue" : "Local worker queue", detail: previewMode ? "Illustrative task state · not submitted to a worker" : liveQueueLabel, status: queueStatus, tone: queueTone, actionLabel: "View queue", to: "/activity" },
  ];
  const modelAvailability = isDemoConnection
    ? "Demo override · inference disabled"
    : ollamaAvailable
      ? "Ollama responds · model tags not reported"
      : apiState === "loading"
        ? "Checking local service"
        : "Not checked while offline";

  return (
    <section className="dashboard-runtime-grid" aria-label="Local runtime topology and configuration">
      <section className="panel local-topology-panel">
        <div className="panel-heading"><div><span className="section-kicker">01 · LOCAL TOPOLOGY</span><h2>Service health</h2><p>Only live states reported by the local API are marked as connected.</p></div><Link className="text-link" to="/settings/models">Open diagnostics <Icon as={ArrowRight} className="icon-xs" /></Link></div>
        <SubsystemConnectionList items={topologyItems} />
        <div className="topology-flow-caption"><span className="topology-flow-node">Browser workspace</span><span className="topology-flow-line" /><span className="topology-flow-node">Local API</span><span className="topology-flow-line" /><span className="topology-flow-node">Ollama / SQLite</span></div>
      </section>
      <KeyValueConfigPanel
        sectionNumber="02"
        title="Runtime configuration"
        className="runtime-config-panel"
        rows={[
          { label: "Workspace mode", value: previewMode ? "Browser preview" : "SQLite-backed", tone: previewMode ? "warning" : "success", mono: false },
          { label: "Local API", value: apiState === "ready" ? "Responding" : apiState === "loading" ? "Checking" : "Offline", tone: apiState === "ready" ? "success" : apiState === "loading" ? "warning" : "danger", mono: false },
          { label: "Selected model", value: activeModel, tone: "brand" },
          { label: "Model availability", value: modelAvailability, tone: isDemoConnection || !ollamaAvailable ? "warning" : "neutral", mono: false },
          { label: "Hardware report", value: hardwareLabel, tone: hardware ? "neutral" : "warning", mono: false },
          { label: "Vector rows", value: vectorCount.toLocaleString(), tone: vectorCount ? "success" : "neutral" },
          { label: "Queue", value: queueLabel, tone: previewMode ? "warning" : "neutral", mono: false },
        ]}
      />
    </section>
  );
}

export default function DashboardPage() {
  const {
    products,
    prospects,
    savedDraftCount,
    productFilter,
    setProductFilter,
    previewMode,
    storageMetrics,
    fitScoreThreshold,
  } = useWorkspace();
  const scopeProduct = products.find((product) => String(product.id) === String(productFilter));
  const scopedProspects = useMemo(() => prospects.filter((prospect) => productFilter === "all" || String(prospect.productId) === String(productFilter)), [prospects, productFilter]);
  const totalProducts = scopeProduct ? 1 : products.length;
  const totalProspects = scopeProduct ? scopeProduct.prospects : products.reduce((sum, product) => sum + Number(product.prospects || 0), 0);
  const researched = scopeProduct ? scopeProduct.researched : products.reduce((sum, product) => sum + Number(product.researched || 0), 0);
  const draftTotal = scopeProduct ? scopeProduct.drafts : savedDraftCount;
  const scored = scopedProspects.filter((prospect) => Number(prospect.score) > 0);
  const averageScore = scored.length ? Math.round(scored.reduce((sum, prospect) => sum + Number(prospect.score), 0) / scored.length) : (scopeProduct?.averageScore || 0);
  const recent = scopedProspects.filter((prospect) => prospect.status === "Completed").sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt))).slice(0, 5);
  const priorityProspects = [...scopedProspects].sort((a, b) => Number(b.score || 0) - Number(a.score || 0)).slice(0, 3);

  const columns = [
    {
      key: "company",
      header: "Company & Contact",
      width: "245px",
      render: (prospect) => <div className="company-cell"><span className="company-avatar">{prospect.company.slice(0, 1).toUpperCase()}</span><span><strong>{prospect.company}</strong><small>{prospect.contact} · {prospect.role}</small>{(prospect.isSample || prospect.isImported || prospect.isPreview) && <em className="record-origin-tag">{prospect.isSample ? "Seeded sample" : prospect.isImported ? "Imported preview" : "Browser preview"}</em>}</span></div>,
    },
    { key: "industry", header: "Industry", width: "140px", render: (prospect) => <span className="industry-label">{prospect.industry || "Not specified"}</span> },
    { key: "score", header: "Fit Score", width: "100px", render: (prospect) => <CircularScoreRing score={prospect.score} size={42} /> },
    { key: "status", header: "Research Status", width: "145px", render: (prospect) => <StatusPill status={prospect.status} /> },
    {
      key: "actions",
      header: "Actions",
      width: "170px",
      render: (prospect) => <div className="table-actions"><Link className="table-action-link" to={`/research/${encodeURIComponent(prospect.id)}`}>View Dossier</Link><Link className="table-action-link table-action-brand" to={`/campaigns?prospectId=${encodeURIComponent(prospect.id)}`} aria-label={`Draft Email for ${prospect.company}`}>Draft Email</Link></div>,
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="LOCAL-FIRST WORKSPACE"
        title="Dashboard"
        subtitle="Local-first sales intelligence & offline draft workspace"
        secondaryAction={<ExportMenu prospects={scopedProspects} />}
        primaryAction={<Link className="btn btn-primary" to="/prospects?import=true"><Icon as={Plus} className="icon-sm" />Import Prospects</Link>}
        trailing={<label className="scope-filter"><span>Product</span><select value={productFilter} onChange={(event) => setProductFilter(event.target.value)}><option value="all">All products</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}{product.isPreview ? " · preview" : ""}</option>)}</select></label>}
      />
      <OfflineGuardBanner />
      <section className="metrics-grid dashboard-kpi-grid" aria-label="Workspace KPI snapshots">
        <KpiMetricCard icon={Boxes} label="Total Products" value={totalProducts} note={scopeProduct ? "Selected product" : previewMode ? "Preview snapshot" : "Local SQLite snapshot"} />
        <KpiMetricCard icon={Users} label="Total Prospects" value={totalProspects} note={scopeProduct ? scopeProduct.name : previewMode ? "Illustrative sample data" : "Persisted local records"} />
        <KpiMetricCard icon={FileSearch} label="Researched Prospects" value={researched} note={previewMode ? "Sample records · verify evidence" : "Completed local research"} />
        <KpiMetricCard icon={MailPlus} label="Saved Email Drafts" value={draftTotal} note="Drafts Only · never sent" />
        <KpiMetricCard icon={BarChart3} label="Avg. Prospect Score" score={averageScore} note={previewMode ? "Preview score · no trend history" : "Current snapshot · no history"} className="dashboard-score-kpi" />
      </section>
      <RuntimeTopologyPanels />
      {priorityProspects.length > 0 && <section className="priority-opportunities-section" aria-label="Priority prospects">
        <div className="section-heading-row priority-heading-row"><div><span className="priority-eyebrow">LOCAL FIT SCORES · REVIEW THE SOURCE BEFORE OUTREACH</span><h2>Priority prospects</h2><p>Top workspace scores; the High Fit label uses your {fitScoreThreshold}% sensitivity threshold. Preview rows are marked.</p></div><Link className="text-link" to="/prospects">View all prospects <Icon as={ArrowRight} className="icon-xs" /></Link></div>
        <div className="priority-card-grid">{priorityProspects.map((prospect) => <AiPriorityCard key={prospect.id} prospect={prospect} />)}</div>
      </section>}
      <section className="dashboard-middle-grid dashboard-table-health-grid" aria-label="Recent prospects and local subsystem health">
        <section className="panel recent-prospects-panel" aria-labelledby="recent-prospects-heading">
          <div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon"><Icon as={Users} className="icon-md" /></span><div><h2 id="recent-prospects-heading">Recent Researched Prospects</h2><p>{previewMode ? "Seeded and browser preview rows are clearly marked" : "Persisted local prospect records"}</p></div></div><Link className="text-link" to="/prospects">View all <Icon as={ArrowRight} className="icon-xs" /></Link></div>
          <DataTable
            columns={columns}
            rows={recent}
            minWidth={760}
            emptyTitle="No prospects in this product"
            emptyDescription="Import a CSV or switch the product filter to see records in this workspace."
            emptyAction={<Link className="btn btn-primary btn-sm" to="/prospects?import=true">Import a CSV</Link>}
          />
          <div className="panel-footer-row"><span>Showing {recent.length} of {scopedProspects.length} records · {previewMode ? "preview data" : "SQLite"}</span><span className="storage-note"><span className={`status-dot ${storageMetrics ? "status-dot-green" : "status-dot-amber"}`} />{storageMetrics ? "Local SQLite available" : "SQLite status unverified"}</span></div>
        </section>
        <SubsystemHealthPanel />
      </section>
      <ActivityChart previewMode={previewMode} />
      {previewMode && <p className="preview-disclosure">Preview workspace values are illustrative. Production product and prospect records are stored locally in SQLite.</p>}
    </div>
  );
}
