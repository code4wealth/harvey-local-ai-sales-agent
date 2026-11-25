import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowDown, ArrowRight, ArrowUp, ArrowUpDown, Check, Clock3, Cpu, Database, Info, Plus, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { useWorkspace } from "./WorkspaceContext.jsx";

export function Icon({ as: IconComponent, className = "", ...props }) {
  return <IconComponent aria-hidden="true" className={className} strokeWidth={1.75} {...props} />;
}

export function SegmentedTickGauge({ value, score, size = 56, label, color = "emerald", className = "", showPercent = true, displayValue, suffix }) {
  const bounded = Math.max(0, Math.min(100, Number(value ?? score) || 0));
  const segments = 36;
  const center = size / 2;
  const outerRadius = size / 2 - 2;
  const innerRadius = outerRadius - (size < 48 ? 4 : 5);
  const activeSegments = Math.round((bounded / 100) * segments);
  const strokeWidth = size < 48 ? 1.7 : 2;
  return (
    <span className={`score-ring-wrap segmented-tick-gauge gauge-${color} ${label ? "has-gauge-label" : ""} ${className}`} aria-label={`${label ? `${label}: ` : ""}${displayValue ? `${displayValue}${suffix ? ` ${suffix}` : ""}` : `${bounded} percent`}`} title={`${displayValue ? `${displayValue}${suffix ? ` ${suffix}` : ""}` : `${bounded}%`}${label ? ` · ${label}` : ""}`}>
      <span className="tick-gauge-dial" style={{ width: size, height: size }}>
        <svg className="score-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" focusable="false">
          {Array.from({ length: segments }, (_, index) => {
            const angle = (index / segments) * Math.PI * 2 - Math.PI / 2;
            const x1 = center + Math.cos(angle) * innerRadius;
            const y1 = center + Math.sin(angle) * innerRadius;
            const x2 = center + Math.cos(angle) * outerRadius;
            const y2 = center + Math.sin(angle) * outerRadius;
            return <line key={index} className={`tick-gauge-mark ${index < activeSegments ? "tick-gauge-mark-active" : ""}`} x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={strokeWidth} strokeLinecap="round" />;
          })}
        </svg>
        <span className="score-ring-number mono-number"><span>{displayValue ?? Math.round(bounded)}</span>{suffix ? <small>{suffix}</small> : showPercent && <small>%</small>}</span>
      </span>
      {label && <span className="tick-gauge-label">{label}</span>}
    </span>
  );
}

export function EmeraldScoreRing({ score = 0, ...props }) {
  return <SegmentedTickGauge value={props.value ?? score} color="emerald" {...props} />;
}

export function CircularScoreRing({ score = 0, ...props }) {
  return <SegmentedTickGauge value={props.value ?? score} color={props.color || "emerald"} {...props} />;
}

const STATUS_MAP = {
  healthy: ["success", "Healthy"], online: ["success", "Online"], connected: ["success", "Connected"],
  complete: ["success", "Complete"], completed: ["success", "Complete"], interested: ["success", "Interested"],
  "high intent": ["success", "High Intent"], "high fit": ["success", "High Fit"], "meets threshold": ["success", "Meets Threshold"],
  saved: ["success", "Saved"], indexed: ["success", "Indexed"], synced: ["success", "Synced"], ready: ["success", "Ready"],
  running: ["warning", "Running"], slow: ["warning", "Slow"], checking: ["warning", "Checking"], review: ["warning", "Review"],
  "needs info": ["warning", "Needs Info"], "needs review": ["warning", "Needs Review"], "needs more information": ["warning", "Needs Info"],
  "awaiting research": ["warning", "Awaiting Research"], "medium score": ["warning", "Medium"], "medium intent": ["warning", "Medium"],
  "follow-up later": ["warning", "Follow-up Later"], "demo connected": ["warning", "Demo Only"], "demo offline": ["warning", "Demo Offline"],
  queued: ["brand", "Queued"], "draft only": ["brand", "Draft Only"], question: ["brand", "Question"], "meeting request": ["brand", "Meeting Request"],
  failed: ["danger", "Failed"], offline: ["danger", "Offline"], unavailable: ["danger", "Unavailable"], unsubscribe: ["danger", "Unsubscribe"],
  "not interested": ["danger", "Not Interested"], "out of office": ["neutral", "Out of Office"], "wrong person": ["neutral", "Wrong Person"],
  other: ["neutral", "Other"],
};

export function DarkStatusBadge({ status = "Not started", children, icon: StatusIcon, className = "" }) {
  const [tone, label] = STATUS_MAP[String(status).toLowerCase()] || ["neutral", status];
  const isRunning = String(status).toLowerCase() === "running";
  return (
    <span className={`status-pill dark-status-badge status-${tone} dark-status-${tone} ${className}`} aria-label={typeof children === "string" ? children : label}>
      {StatusIcon && <Icon as={StatusIcon} className="status-pill-icon" />}
      <span className={`status-dot ${isRunning ? "status-pulse" : ""}`} />
      {children || label}
    </span>
  );
}

export const StatusPill = DarkStatusBadge;

export function PrecisionSliderCard({ title, value, onChange, leftLabel = "Conservative", rightLabel = "Aggressive", footerText = "AI Suggestions", onFooterClick, description = "Adjust this workspace setting. The value is stored in this browser and does not change model behavior outside the local workflow.", min = 0, max = 100, step = 1 }) {
  const bounded = Math.max(min, Math.min(max, Number(value) || 0));
  const progress = ((bounded - min) / (max - min || 1)) * 100;
  return (
    <section className="precision-slider-card">
      <div className="precision-slider-heading"><div><h3>{title}</h3><span className="precision-slider-context">LOCAL WORKSPACE SETTING</span></div><button type="button" className="precision-info-button" title={description} aria-label={`About ${title}`}><Icon as={Info} className="icon-sm" /></button></div>
      <div className="precision-slider-value-row"><span className="precision-slider-caption">CURRENT VALUE</span><output className="precision-slider-value mono-number">{bounded}%</output></div>
      <input className="precision-range" type="range" min={min} max={max} step={step} value={bounded} onChange={(event) => onChange?.(Number(event.target.value))} aria-label={title} aria-valuetext={`${bounded} percent`} style={{ "--range-progress": `${progress}%` }} />
      <div className="precision-slider-scale"><span>{leftLabel}</span><span>{rightLabel}</span></div>
      <button className="precision-slider-footer" type="button" onClick={onFooterClick} disabled={!onFooterClick}><Icon as={Sparkles} className="icon-xs" />{footerText}<Icon as={ArrowRight} className="icon-xs" /></button>
    </section>
  );
}

function connectionTone(status, explicitTone) {
  if (explicitTone) return explicitTone;
  const normalized = String(status || "").toLowerCase();
  if (["connected", "ready", "indexed", "synced", "available", "complete", "loaded"].some((word) => normalized.includes(word))) return "success";
  if (["running", "syncing", "checking", "queued", "pending"].some((word) => normalized.includes(word))) return "warning";
  if (["offline", "failed", "unavailable", "error"].some((word) => normalized.includes(word))) return "danger";
  return "neutral";
}

export function SubsystemConnectionList({ items = [] }) {
  return (
    <div className="subsystem-connection-list">
      {items.map((item) => {
        const tone = connectionTone(item.status, item.tone);
        const ItemIcon = item.icon || Cpu;
        const action = item.actionLabel && (item.to
          ? <Link className="subsystem-config-link" to={item.to}>{item.actionLabel.startsWith("+") ? <Icon as={Plus} className="icon-xs" /> : null}{item.actionLabel.replace(/^\+\s*/, "")}</Link>
          : <button className="subsystem-config-link" type="button" onClick={item.onAction}>{item.actionLabel.startsWith("+") ? <Icon as={Plus} className="icon-xs" /> : null}{item.actionLabel.replace(/^\+\s*/, "")}</button>);
        return (
          <div className="subsystem-row" key={item.id || item.title}>
            <span className="subsystem-row-icon"><Icon as={ItemIcon} className="icon-sm" /></span>
            <span className="subsystem-row-copy"><strong>{item.title}</strong><small>{item.detail}</small></span>
            <span className={`subsystem-status subsystem-status-${tone}`}>{tone === "success" ? <Check size={13} strokeWidth={1.75} /> : tone === "warning" ? <Clock3 size={13} strokeWidth={1.75} /> : null}{item.status}</span>
            {action}
          </div>
        );
      })}
    </div>
  );
}

export function SettingsSubnav({ active = "models" }) {
  return (
    <nav className="settings-subnav" aria-label="Settings sections">
      <Link to="/settings/models" className={`settings-subnav-link ${active === "models" ? "settings-subnav-active" : ""}`} aria-current={active === "models" ? "page" : undefined}><Icon as={Sparkles} className="icon-sm" />Local AI &amp; Models</Link>
      <Link to="/settings/general" className={`settings-subnav-link ${active === "general" ? "settings-subnav-active" : ""}`} aria-current={active === "general" ? "page" : undefined}><Icon as={Database} className="icon-sm" />General &amp; Storage</Link>
    </nav>
  );
}

export function KpiMetricCard({ icon: MetricIcon, label, value, score, delta, note, className = "" }) {
  const formattedValue = typeof value === "number" ? value.toLocaleString() : value;
  return (
    <article className={`metric-card kpi-metric-card ${score !== undefined ? "metric-card-score" : ""} ${className}`}>
      <div className="metric-card-head"><span className={`metric-icon ${score !== undefined ? "metric-icon-brand" : ""}`}><Icon as={MetricIcon} className="icon-md" /></span><span className="metric-label">{label}</span></div>
      <div className="metric-card-value-row">
        {score !== undefined ? <EmeraldScoreRing score={score} size={52} label="FIT SCORE" /> : <strong className="metric-value mono-number">{formattedValue}</strong>}
        <span className="metric-note">{delta ? <><Icon as={TrendingUp} className="icon-xs" /> {delta}</> : note}</span>
      </div>
    </article>
  );
}

export function SparklineKpiCard({ icon: MetricIcon, label, value, suffix, delta, deltaPositive = true, barColor = "#3B82F6", bars = [28, 48, 37, 65, 52, 78, 91], note }) {
  const displayValue = typeof value === "number" ? value.toLocaleString() : value;
  return (
    <article className="sparkline-kpi-card" style={{ "--sparkline-color": barColor }}>
      <div className="sparkline-kpi-heading"><span className="sparkline-kpi-icon"><Icon as={MetricIcon || Activity} className="icon-sm" /></span><span>{label}</span></div>
      <div className="sparkline-kpi-main"><div className="sparkline-kpi-value"><strong className="mono-number">{displayValue}</strong>{suffix && <span className="mono-number">{suffix}</span>}</div><div className="sparkline-bars" aria-hidden="true">{bars.slice(-7).map((height, index) => <i key={index} style={{ height: `${Math.max(8, Math.min(100, Number(height) || 0))}%` }} />)}</div></div>
      <div className="sparkline-kpi-footer">{delta && <span className={`sparkline-kpi-delta ${deltaPositive ? "delta-positive" : "delta-negative"}`}><Icon as={deltaPositive ? TrendingUp : ArrowDown} className="icon-xs" />{delta}</span>}{note && <span className="sparkline-kpi-note">{note}</span>}</div>
    </article>
  );
}

export function KeyValueConfigPanel({ sectionNumber, title, rows = [], className = "" }) {
  const number = String(sectionNumber ?? "").padStart(1, "0");
  return (
    <section className={`key-value-config-panel ${className}`}>
      <header className="key-value-config-header"><span className="mono-number">{number}.</span><h3>{title}</h3></header>
      <dl className="key-value-config-rows">{rows.map((row, index) => {
        const label = row.label ?? row.key ?? `Parameter ${index + 1}`;
        const value = row.value ?? "—";
        const tone = row.tone || "neutral";
        return <div className="key-value-config-row" key={row.id || label}><dt>{label}</dt><dd className={`key-value-value key-value-${tone} ${row.mono === false ? "" : "mono-number"}`}>{value}</dd></div>;
      })}</dl>
    </section>
  );
}

export function AiPriorityCard({ prospect, intent }) {
  const { fitScoreThreshold } = useWorkspace();
  if (!prospect) return null;
  const meetsThreshold = Number(prospect.score || 0) >= fitScoreThreshold;
  const priority = intent || (meetsThreshold ? "High Fit" : "Review");
  const origin = prospect.isSample ? "Seeded example" : prospect.isImported ? "Imported preview" : prospect.isPreview ? "Browser preview" : "SQLite record";
  return (
    <article className="ai-priority-card">
      <div className="ai-priority-card-main">
        <div className="ai-priority-company-block">
          <h3>{prospect.company}</h3>
          <span>{prospect.contact} · {prospect.role}</span>
          <div className="ai-priority-badges"><StatusPill status={priority}>{priority}</StatusPill><span className="ai-priority-origin">{origin}</span></div>
        </div>
        <CircularScoreRing score={prospect.score} color={meetsThreshold ? "emerald" : "amber"} size={54} />
      </div>
      <p className="ai-priority-signal">{prospect.summary || "Review saved prospect evidence for a relevant local buying signal."}</p>
      <Link className="priority-view-button" to={`/research/${encodeURIComponent(prospect.id)}`}>View Dossier <Icon as={ArrowRight} className="icon-xs" /></Link>
    </article>
  );
}

export function AiSynthesisBlock({ model, title = "Local AI Synthesis", children, className = "", isGenerated = false, label }) {
  const workspace = useWorkspace();
  const reportedModel = typeof model === "string" ? model.trim() : "";
  const isQwen3Generated = isGenerated && Boolean(reportedModel) && /^qwen3(?:[:/._-]|$)/i.test(reportedModel);
  return (
    <section className={`ai-synthesis-block ${isGenerated ? "ai-synthesis-generated" : "ai-synthesis-preview"} ${isQwen3Generated ? "ai-synthesis-qwen3" : ""} ${className}`} aria-label={isGenerated ? title : label || "Workspace context"}>
      <div className="ai-generated-heading">
        <span className="ai-generated-mark"><Icon as={Sparkles} className="icon-sm" /></span>
        <div className="ai-generated-labels">
          <span className="ai-generated-title">{isGenerated ? `${title.toUpperCase()}${reportedModel ? ` · ${reportedModel.toUpperCase()}` : ""}` : label || "Workspace Context"}</span>
          <span className="ai-generated-meta">{isGenerated ? <>{reportedModel ? "LOCAL MODEL OUTPUT" : "LOCAL MODEL OUTPUT · MODEL NOT REPORTED"} · REVIEW BEFORE USE</> : <>SOURCE / PREVIEW CONTEXT · <code>{workspace.isDemoConnection ? "DEMO RULES" : "NOT MODEL-GENERATED"}</code></>}</span>
        </div>
        <span className="ai-generated-pill">{isGenerated ? "LOCAL" : "CONTEXT"}</span>
      </div>
      <div className="ai-generated-content">{children}</div>
    </section>
  );
}

export const AiGeneratedBlock = AiSynthesisBlock;

export function EmptyState({ icon: EmptyIcon = Sparkles, title, description, action, compact = false }) {
  return (
    <div className={`empty-state ${compact ? "empty-state-compact" : ""}`}>
      <span className="empty-state-icon"><Icon as={EmptyIcon} className="icon-lg" /></span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}

export function OllamaOfflineBanner({ compact = false }) {
  const { connected, isDemoConnection, apiState, apiStatus } = useWorkspace();
  if (connected && !isDemoConnection) return null;
  const checking = !isDemoConnection && apiState === "loading";
  const slow = !isDemoConnection && apiStatus?.ollama?.state === "slow";
  const heading = isDemoConnection
    ? `Demo override ${connected ? "enabled" : "offline"} · no inference is running`
    : checking
      ? "Checking local Ollama status"
      : slow
        ? "Local Ollama is responding slowly"
        : "Local Ollama is offline";
  const message = isDemoConnection
    ? "This preview status changes the interface only. It does not connect to Ollama or generate model output."
    : checking
      ? "The workspace is checking the local API. No cloud fallback is used while health is unknown."
      : slow
        ? `${apiStatus?.ollama?.message || "The local server is responding slowly."} No cloud fallback is used.`
        : "Drafting and inference stay on this machine. Start Ollama to run local workflows; there is no cloud fallback.";
  return (
    <div className={`offline-banner ${isDemoConnection ? "offline-banner-demo" : ""} ${checking ? "offline-banner-checking" : ""} ${compact ? "offline-banner-compact" : ""}`} role="status">
      <span className="offline-banner-icon"><Icon as={Cpu} className="icon-md" /></span>
      <div>
        <strong>{heading}</strong>
        <p>{message}</p>
      </div>
      <Link className="text-link offline-banner-link" to="/settings/models">Manage local AI</Link>
    </div>
  );
}

export const OfflineGuardBanner = OllamaOfflineBanner;

export function PageHeader({ title, subtitle, eyebrow, primaryAction, secondaryAction, trailing }) {
  const { previewMode } = useWorkspace();
  return (
    <header className="page-header">
      <div className="page-heading-copy">
        {eyebrow && <p className="page-eyebrow">{eyebrow}</p>}
        <div className="page-title-row">
          <h1>{title}</h1>
          {previewMode && <span className="preview-badge">PREVIEW DATA</span>}
        </div>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      <div className="page-header-actions">
        {trailing}
        {secondaryAction}
        {primaryAction}
      </div>
    </header>
  );
}

export function DataTable({
  columns,
  rows,
  rowKey = (row) => row.id,
  onRowClick,
  emptyTitle = "Nothing to show yet",
  emptyDescription = "Records will appear here when they are available in the local workspace.",
  emptyAction,
  selectedIds,
  onSelectionChange,
  sort,
  onSort,
  minWidth = 760,
}) {
  const selected = selectedIds ? new Set(selectedIds) : null;
  const allSelected = Boolean(selected && rows.length && rows.every((row) => selected.has(String(rowKey(row)))));
  const toggleAll = (checked) => {
    if (!onSelectionChange) return;
    const visibleIds = rows.map((row) => String(rowKey(row)));
    const next = checked
      ? [...new Set([...(selectedIds || []).map(String), ...visibleIds])]
      : (selectedIds || []).filter((id) => !visibleIds.includes(String(id)));
    onSelectionChange(next);
  };
  const toggleRow = (id, checked) => {
    if (!onSelectionChange) return;
    const next = new Set((selectedIds || []).map(String));
    if (checked) next.add(String(id));
    else next.delete(String(id));
    onSelectionChange([...next]);
  };
  if (!rows.length) {
    return (
      <div className="data-table-empty-card">
        <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} compact />
      </div>
    );
  }
  return (
    <div className="data-table-card">
      <div className="table-scroll">
        <table className="data-table" style={{ minWidth }}>
          <thead>
            <tr>
              {selected && (
                <th className="selection-column" scope="col">
                  <input aria-label="Select all visible rows" type="checkbox" checked={allSelected} onChange={(event) => toggleAll(event.target.checked)} />
                </th>
              )}
              {columns.map((column) => {
                const active = sort?.key === column.sortKey;
                return (
                  <th key={column.key || column.header} scope="col" className={column.headerClassName || ""} style={column.width ? { width: column.width } : undefined}>
                    {column.sortKey && onSort ? (
                      <button type="button" className="sort-header" onClick={() => onSort(column.sortKey)}>
                        {column.header}
                        <Icon as={!active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown} className="sort-indicator" />
                      </button>
                    ) : column.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const id = String(rowKey(row));
              return (
                <tr
                  key={id}
                  className={`${onRowClick ? "data-row-clickable" : ""} ${selected?.has(id) ? "data-row-selected" : ""}`}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={onRowClick ? (event) => { if (event.key === "Enter") onRowClick(row); } : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                >
                  {selected && (
                    <td className="selection-column" onClick={(event) => event.stopPropagation()}>
                      <input aria-label={`Select ${row.company || row.title || id}`} type="checkbox" checked={selected.has(id)} onChange={(event) => toggleRow(id, event.target.checked)} />
                    </td>
                  )}
                  {columns.map((column) => (
                    <td key={column.key || column.header} className={column.cellClassName || ""}>
                      {column.render ? column.render(row) : row[column.key] ?? "—"}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Modal({ title, description, children, onClose, size = "normal" }) {
  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className={`modal-panel modal-${size}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-heading">
          <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog">×</button>
        </header>
        <div className="modal-content">{children}</div>
      </section>
    </div>
  );
}

export function Drawer({ title, description, children, onClose }) {
  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="drawer-panel" role="dialog" aria-modal="true" aria-label={title}>
        <header className="drawer-heading">
          <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close drawer">×</button>
        </header>
        <div className="drawer-content">{children}</div>
      </aside>
    </div>
  );
}

export function Toggle({ checked, onChange, label, id }) {
  return (
    <label className="toggle-control" htmlFor={id}>
      <span>{label}</span>
      <input id={id} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} role="switch" />
      <span className="toggle-track" aria-hidden="true"><span /></span>
    </label>
  );
}

export function SimpleInput({ label, className = "", ...props }) {
  return <label className={`form-field ${className}`}><span>{label}</span><input {...props} /></label>;
}
