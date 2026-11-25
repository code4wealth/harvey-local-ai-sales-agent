import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, Cpu, Database, Gauge, Globe2, HardDrive, RefreshCw, ShieldCheck, Sparkles, Wifi, WifiOff } from "lucide-react";
import { useWorkspace } from "../WorkspaceContext.jsx";
import { Icon, OfflineGuardBanner, PageHeader, PrecisionSliderCard, SegmentedTickGauge, SettingsSubnav, StatusPill, SubsystemConnectionList, Toggle } from "../ui.jsx";

function formatSize(bytes) {
  if (!Number.isFinite(Number(bytes)) || Number(bytes) <= 0) return "Not reported";
  const value = Number(bytes);
  return value >= 1024 * 1024 ? `${(value / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`;
}

function estimateModelMemoryGb(name) {
  const match = String(name || "").match(/(?:^|:)(\d+(?:\.\d+)?)b(?:$|[:_-])/i);
  return match ? Number(match[1]) * 0.65 : 0;
}

function estimateHardwareFit(ramGb, memory) {
  const totalRam = Number(ramGb);
  if (!Number.isFinite(totalRam) || totalRam <= 0 || !memory) return 0;
  const estimatedModelBudget = Math.max(0, totalRam - Math.max(1, totalRam * 0.25));
  return Math.max(0, Math.min(100, Math.round((estimatedModelBudget / memory) * 100)));
}

export default function ModelsSettingsPage() {
  const {
    connected,
    isDemoConnection,
    setDemoConnection,
    resetDemoConnection,
    testConnection,
    refreshStatus,
    apiStatus,
    apiState,
    hardware,
    storageMetrics,
    fitScoreThreshold,
    setFitScoreThreshold,
    signalConfidenceThreshold,
    setSignalConfidenceThreshold,
    notify,
  } = useWorkspace();
  const [testing, setTesting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [testResult, setTestResult] = useState("");
  const hardwareRecommendation = hardware?.recommended_model || apiStatus?.hardware?.recommended_model || "";
  const hardwareTier = hardware?.tier || apiStatus?.hardware?.tier || "Detecting hardware";
  const recommended = hardwareRecommendation || "Not detected";
  const installedModelsReported = Array.isArray(apiStatus?.ollama?.installed_models);
  const installedModels = installedModelsReported ? apiStatus.ollama.installed_models : [];
  const selectedModel = apiStatus?.ollama?.model || "";
  const modelError = apiStatus?.ollama?.model_error || "";
  const embeddingCache = apiStatus?.embedding_cache;
  const localReadiness = apiStatus?.local_readiness;
  const readinessLabel = apiState === "loading"
    ? "CHECKING READINESS"
    : localReadiness?.ready
      ? "LOCAL READY"
      : localReadiness
        ? "NEEDS ATTENTION"
        : "READINESS NOT REPORTED";
  const readinessStatus = apiState === "loading"
    ? "Running"
    : localReadiness?.ready
      ? "Ready"
      : localReadiness
        ? "Review"
        : apiState === "offline" ? "Offline" : "Not reported";
  const serverAvailable = apiState === "ready" && apiStatus?.ollama?.available === true && !isDemoConnection;
  const ollamaLabel = isDemoConnection
    ? connected ? "Demo only" : "Demo offline (simulated)"
    : apiState === "loading"
      ? "Checking"
      : apiStatus?.ollama?.state === "slow"
        ? "Slow"
        : apiStatus?.ollama?.state === "error"
          ? "Error"
          : connected ? "Connected" : "Offline";
  const ollamaPillStatus = isDemoConnection || apiState === "loading" || apiStatus?.ollama?.state === "slow"
    ? "Running"
    : apiStatus?.ollama?.state === "error" ? "Review" : connected ? "Connected" : "Offline";
  const vectorCount = Number(storageMetrics?.vector_rows ?? Object.values(storageMetrics?.vectors || {}).reduce((sum, value) => sum + Number(value || 0), 0));
  const reportedEndpoint = apiStatus?.ollama?.url;
  const endpoint = reportedEndpoint
    ? (/^https?:\/\//i.test(reportedEndpoint) ? reportedEndpoint : `http://${reportedEndpoint}`).replace(/^https?:\/\/(127\.0\.0\.1|0\.0\.0\.0|localhost)/i, "http://localhost")
    : "http://localhost:11434";
  const models = useMemo(() => installedModels.map((name) => {
    const memory = estimateModelMemoryGb(name);
    const totalRam = Number(hardware?.ram_gb ?? apiStatus?.hardware?.ram_gb) || 0;
    return { name, memory, fit: estimateHardwareFit(totalRam, memory), ramUse: totalRam > 0 ? Math.min(100, Math.round((memory / totalRam) * 100)) : 0 };
  }), [installedModels, hardware?.ram_gb, apiStatus?.hardware?.ram_gb]);

  const runTest = async () => {
    setTesting(true);
    setTestResult("");
    try {
      const status = await testConnection();
      if (status?.ollama?.available) {
        const message = status.ollama.model_error
          || (status.ollama.model_installed
            ? `Ollama responded at ${status.ollama.url || "localhost:11434"} · ${status.ollama.model} is installed.`
            : `Ollama responded at ${status.ollama.url || "localhost:11434"}, but no model is verified.`);
        setTestResult(message);
        notify(message);
      } else {
        const message = status?.ollama?.message
          || "No Ollama response. The workspace remains local-only; no cloud fallback will be used.";
        setTestResult(message);
        notify(message);
      }
    } catch (error) {
      setTestResult(error.message || "Connection test failed.");
    } finally {
      setTesting(false);
    }
  };
  const refreshHardware = async () => {
    setRefreshing(true);
    try {
      await refreshStatus();
      notify("Local hardware and storage details refreshed.");
    } finally {
      setRefreshing(false);
    }
  };
  return (
    <div className="page-stack">
      <PageHeader eyebrow="WORKSPACE SETTINGS · LOCAL INFERENCE" title="Local AI & Models" subtitle="Configure local Ollama inference, scoring thresholds, and offline storage." primaryAction={<button type="button" className="btn btn-primary" onClick={runTest} disabled={testing}><Icon as={RefreshCw} className={`icon-sm ${testing ? "icon-spin" : ""}`} />{testing ? "Testing local Ollama…" : "Test Connection"}</button>} />
      <SettingsSubnav active="models" />
      <OfflineGuardBanner compact />

      <section className="settings-section" aria-labelledby="scoring-settings-heading">
        <div className="settings-section-heading"><div><span className="section-kicker">01 · WORKSPACE CONTROLS</span><h2 id="scoring-settings-heading">Inference &amp; Scoring Sensitivity</h2><p>Local-only thresholds for prioritization and evidence review. These preferences are stored in this browser.</p></div><StatusPill status="Saved">BROWSER SETTINGS</StatusPill></div>
        <div className="precision-slider-grid">
          <PrecisionSliderCard
            title="ICP Fit Score Threshold"
            value={fitScoreThreshold}
            onChange={setFitScoreThreshold}
            leftLabel="CONSERVATIVE"
            rightLabel="AGGRESSIVE"
            footerText="RESET TO SUGGESTION"
            description="High-fit labels on prospect cards use this threshold. This preference changes browser presentation, not the local model prompt."
            onFooterClick={() => { setFitScoreThreshold(75); notify("Fit threshold set to the local workspace suggestion: 75%."); }}
          />
          <PrecisionSliderCard
            title="Signal Confidence Requirement"
            value={signalConfidenceThreshold}
            onChange={setSignalConfidenceThreshold}
            leftLabel="CONSERVATIVE"
            rightLabel="AGGRESSIVE"
            footerText="RESET REVIEW THRESHOLD"
            description="Use this threshold to review confidence labels on extracted evidence. It is a local display preference; the API prompt is unchanged."
            onFooterClick={() => { setSignalConfidenceThreshold(50); notify("Signal confidence threshold set to 50%."); }}
          />
        </div>
      </section>

      <section className="panel installed-models-panel" aria-labelledby="installed-models-heading">
        <div className="panel-heading installed-models-heading">
          <div><span className="section-kicker">02 · LOCAL MODEL INVENTORY</span><h2 id="installed-models-heading">Installed Ollama Models</h2><p>Models reported by local Ollama. The backend resolves its configured preference against these installed tags; there is no browser-side model selector.</p></div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={runTest} disabled={testing}><Icon as={RefreshCw} className={`icon-xs ${testing ? "icon-spin" : ""}`} />Test connection</button>
        </div>
        <div className="model-server-strip"><span className={`engine-status-light ${connected && !isDemoConnection ? "is-online" : apiState === "loading" || isDemoConnection || apiStatus?.ollama?.state === "slow" ? "is-checking" : "is-offline"}`} /><span><strong>Ollama Server</strong><small><code>{endpoint}</code> · {isDemoConnection ? (connected ? "demo override · no inference" : "simulated offline · UI-only; no inference") : apiState === "loading" ? "checking local health" : apiStatus?.ollama?.state === "slow" ? "responding slowly · no cloud fallback" : connected ? "connected on this machine" : "offline · no cloud fallback"}</small></span><StatusPill status={ollamaPillStatus}>{ollamaLabel.toUpperCase()}</StatusPill></div>
        <div className="installed-model-list" aria-label="Installed local language models">
          {models.map(({ name, memory, fit, ramUse }) => (
            <div className={`installed-model-row ${selectedModel === name ? "installed-model-active" : ""}`} key={name}>
              <span className="model-radio-custom" aria-hidden="true" />
              <span className="installed-model-copy"><strong><code>{name}</code>{selectedModel === name && <span className="model-selected-tag">ACTIVE MODEL</span>}</strong><small>{name === recommended ? "Hardware recommendation" : "Installed locally"} · verified from Ollama /api/tags</small></span>
              <div className="installed-model-gauges">
                <SegmentedTickGauge value={fit} size={54} label="EST. FIT" color={fit >= 80 ? "emerald" : "amber"} />
                <SegmentedTickGauge value={ramUse} size={54} label="RAM NEED" displayValue={memory ? memory.toFixed(1) : "—"} suffix={memory ? "GB" : ""} showPercent={false} color={ramUse > 80 ? "amber" : "blue"} />
              </div>
              <span className="model-offline-ready"><Icon as={selectedModel === name ? Check : ShieldCheck} className="icon-xs" />{selectedModel === name ? "Resolved by local API" : "Installed · not selected"}</span>
            </div>
          ))}
          {!models.length && <p className="empty-state-compact">{apiState === "loading" ? "Checking local Ollama model tags…" : installedModelsReported ? "Ollama reports no installed models." : apiStatus?.ollama?.state === "error" ? apiStatus.ollama.message || "Ollama could not return its installed model tags." : serverAvailable ? "Ollama is reachable, but its installed model tags were not reported." : "Installed model tags are unavailable while Ollama is offline."}</p>}
          <div className="installed-model-row embedding-model-row">
            <span className="embedding-model-icon"><Icon as={Sparkles} className="icon-sm" /></span>
            <span className="installed-model-copy"><strong><code>{embeddingCache?.model || "sentence-transformers/all-MiniLM-L6-v2"}</code><span className="model-selected-tag">EMBEDDING</span></strong><small>{embeddingCache?.loaded ? "Loaded in the local process" : embeddingCache?.cached ? "Model files found in the local cache" : embeddingCache ? "Model files are not present in the detected local cache" : "Local embedding cache has not been reported"}{vectorCount ? ` · ${vectorCount.toLocaleString()} SQLite vector rows` : " · no vector rows recorded"}</small></span>
            <span className={`embedding-model-state ${embeddingCache?.available ? "is-ready" : ""}`}>{embeddingCache?.available ? "Cache available" : embeddingCache ? "Cache missing" : "Not reported"}</span>
          </div>
        </div>
        <p className="hardware-estimate-note">Resolved model: <code>{selectedModel || "none"}</code>. {apiStatus?.ollama?.requested_model && `Requested by ${apiStatus.ollama.model_source || "local API"}: ${apiStatus.ollama.requested_model}.`} {modelError && <strong className="form-error" role="alert">{modelError}</strong>} Hardware fit and RAM needs are estimates based on reported system RAM and model size, not a download claim. {hardware?.ram_gb != null ? `${hardware.ram_gb} GB RAM · ${hardware.cpu_count ?? "—"} CPU cores · ${hardware.gpu_vram_gb != null ? `${hardware.gpu_vram_gb} GB GPU VRAM` : "no GPU VRAM reported"}.` : "Hardware details have not been reported by the local API."} The backend checks an explicit API request first, then DEFAULT_MODEL, then the hardware recommendation; every target must exactly match an installed local Ollama tag.</p>
      </section>

      <section className="settings-section" aria-labelledby="local-pipeline-heading">
        <div className="settings-section-heading"><div><span className="section-kicker">03 · LOCAL PIPELINE</span><h2 id="local-pipeline-heading">Local Pipeline &amp; Engine Status</h2><p>Review hardware diagnostics and local service state. No hosted AI or vector API is configured.</p>{localReadiness?.reasons?.length > 0 && <p className="hardware-note" role="status">Readiness checks: {localReadiness.reasons.join(" · ")}</p>}</div><div className="flex items-center gap-2"><StatusPill status={readinessStatus}>{readinessLabel}</StatusPill><button className="btn btn-secondary btn-sm" type="button" onClick={refreshHardware} disabled={refreshing}><Icon as={RefreshCw} className={`icon-xs ${refreshing ? "icon-spin" : ""}`} />{refreshing ? "Refreshing…" : "Refresh Hardware Specs"}</button></div></div>
        <div className="model-runtime-grid settings-runtime-grid">
          <article className="panel runtime-info-card diagnostics-card">
            <div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon"><Icon as={Gauge} className="icon-md" /></span><div><h2>Local Engine Diagnostics</h2><p>Values reported by the local service</p></div></div><StatusPill status={hardware ? "Connected" : apiState === "offline" ? "Offline" : "Running"}>{hardware ? "DETECTED" : apiState === "offline" ? "UNAVAILABLE" : "CHECKING"}</StatusPill></div>
            <div className="hardware-stat-grid"><div><span>System RAM</span><strong className="mono-number">{hardware?.ram_gb != null ? `${hardware.ram_gb} GB` : "—"}</strong></div><div><span>CPU cores</span><strong className="mono-number">{hardware?.cpu_count ?? "—"}</strong></div><div><span>GPU VRAM</span><strong className="mono-number">{hardware?.gpu_vram_gb != null ? `${hardware.gpu_vram_gb} GB` : "Not detected"}</strong></div><div><span>Recommended model</span><strong className="mono-number">{recommended}</strong></div></div>
            <div className="hardware-recommendation"><span className="recommendation-icon"><Icon as={Sparkles} className="icon-sm" /></span><div><span>LOCAL RESOURCE PROFILE · <span className="mono-number">{hardwareTier}</span></span><strong>{recommended}</strong></div><span className="model-offline-ready">{selectedModel ? `Resolved model: ${selectedModel}` : "No installed model resolved"}</span></div>
            <p className="hardware-note">Recommendations use reported local resources. Download the model with Ollama before running inference.</p>
          </article>
          <article className="panel subsystem-settings-card">
            <div className="panel-heading"><div><h2>Subsystem Connections</h2><p>Live state from the local API where available</p></div></div>
            <SubsystemConnectionList items={[
              { icon: Cpu, title: "Ollama Server", detail: `${endpoint} · resolved ${selectedModel || "no model"}`, status: isDemoConnection ? (connected ? "Demo connected" : "Demo offline (simulated)") : connected ? "Connected" : apiState === "loading" ? "Checking" : "Offline", tone: isDemoConnection ? "warning" : connected ? "success" : apiState === "loading" ? "warning" : "danger", ...(!connected || isDemoConnection ? { actionLabel: "+ Configure", to: "/settings/models" } : {}) },
              { icon: Globe2, title: "Playwright Web Scraper", detail: "No live health endpoint is reported; saved page text is used locally", status: "Not reported", tone: "neutral", actionLabel: "+ Review", to: "/prospects" },
              { icon: HardDrive, title: "SentenceTransformers", detail: `${embeddingCache?.model || "all-MiniLM-L6-v2"} cache · ${vectorCount.toLocaleString()} SQLite vector rows`, status: embeddingCache?.available ? "Ready" : embeddingCache ? "Unavailable" : "Not reported", tone: embeddingCache?.available ? "success" : embeddingCache ? "warning" : "neutral", ...(!embeddingCache?.available ? { actionLabel: "+ Review", to: "/settings/general" } : {}) },
              { icon: Database, title: "SQLite Database", detail: `${storageMetrics?.database_name || "harvey.db"} · ${formatSize(storageMetrics?.file_bytes)}`, status: storageMetrics ? "Synced" : "Unavailable", tone: storageMetrics ? "success" : "warning", ...(!storageMetrics ? { actionLabel: "+ Review", to: "/settings/general" } : {}) },
            ]} />
            <div className="runtime-footer"><Icon as={ShieldCheck} className="icon-xs" />All integration calls stay on-device. The demo switch changes UI state only and never triggers model inference.</div>
          </article>
        </div>
      </section>

      <section className="model-connection-card model-connection-status-card">
        <div className="model-connection-icon"><Icon as={connected && !isDemoConnection ? Wifi : WifiOff} className="icon-lg" /></div>
        <div className="model-connection-main"><div className="model-connection-title-row"><h2>{isDemoConnection ? (connected ? "Demo connection preview" : "Demo offline preview") : apiState === "loading" ? "Checking local Ollama" : apiStatus?.ollama?.state === "slow" ? "Ollama is responding slowly" : apiStatus?.ollama?.state === "error" ? "Ollama model tags could not be read" : connected ? "Ollama is connected" : "Ollama is offline"}</h2><StatusPill status={ollamaPillStatus}>{isDemoConnection ? "DEMO MODE · NO INFERENCE" : ollamaLabel.toUpperCase()}</StatusPill></div><p>Endpoint <code>{endpoint}</code> · the local API resolves inference to {selectedModel ? <code>{selectedModel}</code> : "no installed model"}; model selection is controlled by backend configuration and installed tags.</p>{testResult && <span className={`connection-test-result ${serverAvailable ? "test-result-success" : "test-result-warning"}`} role="status"><Icon as={serverAvailable ? Check : WifiOff} className="icon-xs" />{testResult}</span>}</div>
        <div className="model-connection-actions"><button type="button" className="btn btn-secondary btn-sm" onClick={runTest} disabled={testing}>Test again</button><Toggle id="demo-connection-toggle" checked={isDemoConnection && !connected} onChange={(value) => value ? setDemoConnection(false) : resetDemoConnection()} label="Simulate offline" /></div>
      </section>

      <div className="settings-disclaimer"><Icon as={ShieldCheck} className="icon-sm" /><p><strong>Local-only by design.</strong> If Ollama or a required local model is unavailable, Sellbird does not fall back to a cloud model. Readiness above reflects the current Ollama tags and local embedding cache checks.</p></div>
      <Link to="/settings/general" className="model-settings-general-link">General &amp; Storage <Icon as={ArrowRight} className="icon-xs" /></Link>
    </div>
  );
}
