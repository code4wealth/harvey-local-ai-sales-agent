import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowRight, Clock3, Cpu, FileSearch, ListFilter, MailPlus, RefreshCw, Search } from "lucide-react";
import { useWorkspace } from "../WorkspaceContext.jsx";
import { DataTable, EmptyState, Icon, Modal, OfflineGuardBanner, PageHeader, StatusPill } from "../ui.jsx";

const FILTERS = ["All tasks", "Queued", "Running", "Completed", "Failed"];

function TaskDetails({ task, product, prospect, onRetry, onClose }) {
  const icon = task.type?.toLowerCase().includes("scrape") ? FileSearch : task.type?.toLowerCase().includes("draft") ? MailPlus : Cpu;
  return <Modal title="Task details" description={task.title} onClose={onClose}>
    <div className="task-detail-header"><span className={`task-detail-icon task-detail-${String(task.status).toLowerCase()}`}><Icon as={icon} className="icon-lg" /></span><div><StatusPill status={task.status} /><p className="mono-number task-detail-id">{task.id}</p></div></div>
    <dl className="task-detail-list"><div><dt>Task type</dt><dd>{task.type || "Local workflow"}</dd></div><div><dt>Status</dt><dd><StatusPill status={task.status} /></dd></div><div><dt>Duration</dt><dd className="mono-number">{task.duration || "—"}</dd></div><div><dt>Product</dt><dd>{product ? <Link to={`/products?productId=${encodeURIComponent(product.id)}`}>{product.name}</Link> : "Not linked"}</dd></div><div><dt>Prospect</dt><dd>{prospect ? <Link to={`/research/${encodeURIComponent(prospect.id)}`}>{prospect.company} · {prospect.contact}</Link> : "Not linked"}</dd></div><div><dt>Last updated</dt><dd>{task.updatedAt || "Not available"}</dd></div></dl>
    <div className="task-detail-log"><span className="detail-label">LOCAL WORKFLOW DETAIL</span><p>{task.detail || "No additional task detail was recorded."}</p></div>
    {task.isPreview && <p className="preview-disclosure">Illustrative preview task · no live model or browser worker was run.</p>}
    <div className="modal-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Close</button>{task.status === "Failed" && <button type="button" className="btn btn-primary" onClick={() => { onRetry(task); onClose(); }}><Icon as={RefreshCw} className="icon-sm" />{task.isPreview ? "Retry preview" : "Retry local queue"}</button>}</div>
  </Modal>;
}

export default function ActivityPage() {
  const { tasks, prospects, products, retryTask, connected, isDemoConnection, apiState, apiStatus, previewMode } = useWorkspace();
  const [filter, setFilter] = useState("All tasks");
  const [query, setQuery] = useState("");
  const [selectedTask, setSelectedTask] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const visibleTasks = previewMode ? tasks : tasks.filter((task) => !task.isPreview);
  const localQueue = apiStatus?.queue || {};
  const hasLiveQueueMetrics = apiState === "ready" && ["queued", "running", "failed"].some((key) => localQueue[key] != null);
  const failedCount = previewMode || !hasLiveQueueMetrics ? visibleTasks.filter((task) => task.status === "Failed").length : Number(localQueue.failed || 0);
  const runningCount = previewMode || !hasLiveQueueMetrics ? visibleTasks.filter((task) => task.status === "Running").length : Number(localQueue.running || 0);
  const queuedCount = previewMode || !hasLiveQueueMetrics ? visibleTasks.filter((task) => task.status === "Queued").length : Number(localQueue.queued || 0);
  const activeCount = runningCount + queuedCount;
  const displayActiveCount = previewMode || hasLiveQueueMetrics ? activeCount : "—";
  const displayQueuedCount = previewMode || hasLiveQueueMetrics ? queuedCount : "—";
  const displayFailedCount = previewMode || hasLiveQueueMetrics ? failedCount : "—";
  const queueSourceLabel = previewMode
    ? "Illustrative browser task records · no worker was invoked"
    : hasLiveQueueMetrics
      ? "Live SQLite queue counts from the local API · task details are browser-session history"
      : apiState === "loading"
        ? "Checking local API queue metrics"
        : "Live queue metrics unavailable · task history is kept separate";
  const filtered = useMemo(() => visibleTasks.filter((task) => {
    const filterMatch = filter === "All tasks" || task.status === filter;
    const prospect = prospects.find((row) => String(row.id) === String(task.prospectId));
    const product = products.find((row) => String(row.id) === String(task.productId));
    const queryMatch = !query.trim() || `${task.id} ${task.title} ${task.type} ${task.detail} ${prospect?.company || ""} ${product?.name || ""}`.toLowerCase().includes(query.trim().toLowerCase());
    return filterMatch && queryMatch;
  }).sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt))), [visibleTasks, filter, query, prospects, products]);
  const retryFailed = async (task) => {
    setRetrying(true);
    try {
      await retryTask(task?.id);
    } finally {
      setRetrying(false);
    }
  };
  const columns = [
    { key: "task", header: "Task", width: "300px", render: (task) => <div className="activity-task-cell"><span className="activity-task-icon"><Icon as={task.type?.toLowerCase().includes("scrape") ? FileSearch : task.type?.toLowerCase().includes("draft") ? MailPlus : Cpu} className="icon-sm" /></span><span><strong>{task.title}</strong><small>{task.type} · <code>{task.id}</code></small>{(task.isSample || task.isImported || task.isPreview) && <em className="record-origin-tag">{task.isSample ? "Seeded sample" : task.isImported ? "Imported preview" : "Demo task"}</em>}</span></div> },
    { key: "product", header: "Product / Prospect", width: "220px", render: (task) => { const prospect = prospects.find((item) => String(item.id) === String(task.prospectId)); const product = products.find((item) => String(item.id) === String(task.productId)); return <div className="activity-related-cell"><strong>{prospect?.company || "—"}</strong><small>{product?.name || "Unlinked product"}</small></div>; } },
    { key: "status", header: "Status", width: "130px", render: (task) => <StatusPill status={task.status} /> },
    { key: "duration", header: "Duration", width: "95px", render: (task) => <span className="mono-number duration-label">{task.duration || "—"}</span> },
    { key: "updatedAt", header: "Last updated", width: "145px", render: (task) => <span className="updated-label">{task.updatedAt || "—"}</span> },
    { key: "actions", header: "Actions", width: "125px", render: (task) => <div className="table-actions"><button type="button" className="table-action-link" onClick={() => setSelectedTask(task)}>Details</button>{task.status === "Failed" && <button type="button" className="table-action-link table-action-brand" onClick={() => retryFailed(task)} disabled={retrying}>{task.isPreview ? "Retry preview" : "Retry queue"}</button>}</div> },
  ];
  const localEngineLabel = isDemoConnection ? "Demo only" : apiState === "loading" ? "Checking" : apiStatus?.ollama?.state === "slow" ? "Slow" : connected ? "Connected" : "Offline";
  const queueSourceClass = previewMode ? "is-checking" : hasLiveQueueMetrics ? "is-online" : "is-checking";
  return (
    <div className="page-stack">
      <PageHeader eyebrow="WORKSPACE · TASK MONITOR" title="Activity Queue" subtitle="Inspect local research, drafting, and workflow tasks. Retry failed work when the local engine is available." primaryAction={failedCount > 0 && <button type="button" className="btn btn-secondary" onClick={() => retryFailed()} disabled={retrying}><Icon as={RefreshCw} className="icon-sm" />{retrying ? "Retrying…" : `Retry All Failed (${failedCount})`}</button>} />
      <OfflineGuardBanner compact />
      <section className="activity-stats-grid"><article><span className="activity-stat-icon activity-stat-running"><Icon as={Activity} className="icon-md" /></span><div><span>Active tasks</span><strong className="mono-number">{displayActiveCount}</strong></div></article><article><span className="activity-stat-icon activity-stat-queued"><Icon as={Clock3} className="icon-md" /></span><div><span>Queued</span><strong className="mono-number">{displayQueuedCount}</strong></div></article><article><span className="activity-stat-icon activity-stat-failed"><Icon as={RefreshCw} className="icon-md" /></span><div><span>Failed</span><strong className="mono-number">{displayFailedCount}</strong></div></article><article><span className="activity-stat-icon activity-stat-engine"><Icon as={Cpu} className="icon-md" /></span><div><span>Ollama API</span><strong className="activity-engine-value">{localEngineLabel}</strong></div></article></section>
      <section className="panel queue-state-panel"><div className="queue-state-copy"><span className={`engine-status-light ${queueSourceClass}`} /><div><strong>{previewMode ? "Browser preview queue" : "SQLite task queue"}</strong><small>{queueSourceLabel}{!previewMode && isDemoConnection ? " · demo toggle changes UI only" : !previewMode && apiStatus?.ollama?.state === "slow" ? " · Ollama is responding slowly" : ""}</small></div></div><div className="queue-db-counters"><span><strong className="mono-number">{displayQueuedCount}</strong> queued</span><span><strong className="mono-number">{previewMode || hasLiveQueueMetrics ? runningCount : "—"}</strong> running</span><span><strong className="mono-number">{displayFailedCount}</strong> failed</span></div><span className={`queue-data-badge ${previewMode ? "queue-data-preview" : ""}`}>{previewMode ? "PREVIEW TASKS" : hasLiveQueueMetrics ? "LIVE API COUNTS" : "UNVERIFIED"}</span></section>
      <section className="panel activity-table-panel"><div className="panel-heading"><div><h2>Task event details</h2><p>{previewMode ? "Illustrative sample tasks are not queued in SQLite." : "Live queue counts are separate from this browser-session activity history."}</p></div></div><div className="activity-filter-toolbar"><div className="activity-filter-tabs" role="tablist" aria-label="Filter activity tasks">{FILTERS.map((option) => <button type="button" role="tab" aria-selected={filter === option} className={filter === option ? "activity-filter-active" : ""} key={option} onClick={() => setFilter(option)}>{option}{option === "Failed" && failedCount > 0 && <span>{failedCount}</span>}</button>)}</div><label className="table-search"><Icon as={Search} className="icon-sm" /><input placeholder="Search tasks or prospects…" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search tasks" /></label></div>
        <DataTable columns={columns} rows={filtered} rowKey={(task) => task.id} minWidth={1050} emptyTitle="No tasks in this view" emptyDescription="Try another status filter, or run a local workflow from a prospect dossier." emptyAction={<Link to="/prospects" className="btn btn-secondary btn-sm">Browse prospects <Icon as={ArrowRight} className="icon-xs" /></Link>} />
        <div className="panel-footer-row"><span>Showing {filtered.length} of {visibleTasks.length} task{visibleTasks.length === 1 ? "" : "s"}</span><span className="storage-note"><span className={`status-dot ${hasLiveQueueMetrics || previewMode ? "status-dot-green" : "status-dot-amber"}`} />{previewMode ? "Browser preview history" : hasLiveQueueMetrics ? "Live queue counts verified" : "Queue metrics unverified"}</span></div></section>
      {selectedTask && <TaskDetails task={selectedTask} product={products.find((item) => String(item.id) === String(selectedTask.productId))} prospect={prospects.find((item) => String(item.id) === String(selectedTask.prospectId))} onRetry={retryFailed} onClose={() => setSelectedTask(null)} />}
    </div>
  );
}
