import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, ExternalLink, FileSearch, Globe2, MailPlus, RefreshCw, ShieldCheck, Sparkles, Users, X } from "lucide-react";
import { apiRequest, useWorkspace } from "../WorkspaceContext.jsx";
import { AiSynthesisBlock, CircularScoreRing, EmptyState, Icon, OfflineGuardBanner, PageHeader, StatusPill } from "../ui.jsx";

function safePublicUrl(value) {
  if (!value) return "";
  const raw = String(value).trim();
  if (!/^https?:\/\//i.test(raw) && !/^[a-z0-9.-]+(?::\d+)?(?:\/[\w./#?=&%-]*)?$/i.test(raw)) return "";
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function SignalCard({ signal, index, confidenceThreshold = 50 }) {
  const rawConfidence = Number(signal.confidence || 0);
  const confidence = Math.round(rawConfidence <= 1 ? rawConfidence * 100 : rawConfidence);
  const meetsThreshold = confidence >= confidenceThreshold;
  return <article className="signal-card"><div className="signal-card-top"><span className="signal-index mono-number">{String(index + 1).padStart(2, "0")}</span><StatusPill status="Question">{String(signal.type || "Signal").replaceAll("_", " ")}</StatusPill><span className="signal-confidence mono-number">{confidence}% confidence</span><StatusPill status={meetsThreshold ? "Meets threshold" : "Needs review"} /></div><blockquote>“{signal.evidence || "No quoted evidence was returned."}”</blockquote><div className="signal-validation"><Icon as={ShieldCheck} className="icon-xs" />{meetsThreshold ? "Meets your display threshold; still verify the source before use." : `Below your ${confidenceThreshold}% display threshold; kept visible for manual review.`}</div></article>;
}

export default function ResearchPage() {
  const { prospectId: routeProspectId } = useParams();
  const { products, prospects, connected, isDemoConnection, runResearch, activeModel, previewMode, notify, signalConfidenceThreshold, fitScoreThreshold } = useWorkspace();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState(routeProspectId || searchParams.get("prospectId") || "");
  const [signalRun, setSignalRun] = useState(null);
  const [problemStatement, setProblemStatement] = useState(null);
  const [pageText, setPageText] = useState("");
  const [expandedSource, setExpandedSource] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problemBusy, setProblemBusy] = useState(false);
  const [error, setError] = useState("");
  const [problemError, setProblemError] = useState("");
  const selected = prospects.find((prospect) => String(prospect.id) === String(routeProspectId || selectedId));
  const product = products.find((item) => String(item.id) === String(selected?.productId));
  const signals = signalRun?.signals || [];
  const productFilter = searchParams.get("productId") || "all";
  const visibleProspects = useMemo(() => prospects.filter((prospect) => productFilter === "all" || String(prospect.productId) === String(productFilter)), [prospects, productFilter]);
  const companyName = selected?.company || "Select a prospect";
  const publicUrl = safePublicUrl(selected?.domain);

  useEffect(() => {
    if (routeProspectId) setSelectedId(routeProspectId);
    else if (searchParams.get("prospectId")) setSelectedId(searchParams.get("prospectId"));
  }, [routeProspectId, searchParams]);
  useEffect(() => {
    if (!selected) { setSignalRun(null); setProblemStatement(null); setPageText(""); setLoading(false); return; }
    if (selected.isPreview) {
      setSignalRun({ status: selected.status === "Completed" ? "succeeded" : String(selected.status).toLowerCase(), signals: null, model_name: "Preview sample · no inference" });
      setProblemStatement(null);
      setPageText(selected.evidence || "");
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setSignalRun(null);
    setProblemStatement(null);
    setPageText("");
    Promise.allSettled([
      apiRequest(`/api/prospects/${encodeURIComponent(selected.id)}/signals`),
      selected.pageTextPath ? apiRequest(`/api/prospects/${encodeURIComponent(selected.id)}/page`) : Promise.reject(new Error("No saved page text is linked to this prospect.")),
      apiRequest(`/api/products/${encodeURIComponent(selected.productId)}/prospects/${encodeURIComponent(selected.id)}/problem-statement`),
    ]).then((results) => {
      if (!alive) return;
      if (results[0].status === "fulfilled") setSignalRun(results[0].value);
      if (results[1].status === "fulfilled") setPageText(typeof results[1].value === "string" ? results[1].value : "");
      if (results[2].status === "fulfilled") setProblemStatement(results[2].value);
      setLoading(false);
    });
    return () => { alive = false; };
  }, [selected?.id, selected?.productId, selected?.isPreview, selected?.pageTextPath]);

  const chooseProspect = (id) => {
    setSelectedId(id);
    setExpandedSource(false);
    setError("");
    navigate(id ? `/research/${encodeURIComponent(id)}` : `/research${productFilter !== "all" ? `?productId=${encodeURIComponent(productFilter)}` : ""}`);
  };
  const rerun = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const result = await runResearch(selected);
      setSignalRun(result?.signals ? result : { status: result?.status || "queued", signals: null, model_name: result?.model_name || activeModel });
      notify(result?.status === "queued" ? "Research is queued in the local workflow." : "Local research task started.");
    } catch (cause) {
      setError(cause.message || "Local research could not be started.");
    } finally {
      setBusy(false);
    }
  };
  const generateProblemStatement = async () => {
    if (!selected) return;
    setProblemBusy(true);
    setProblemError("");
    try {
      if (selected.isPreview || isDemoConnection) throw new Error("Problem statements require a SQLite-backed prospect and live local Ollama; demo and preview data do not run inference.");
      if (!connected) throw new Error("Local Ollama is disconnected. No cloud fallback is used.");
      const result = await apiRequest(`/api/products/${encodeURIComponent(selected.productId)}/prospects/${encodeURIComponent(selected.id)}/problem-statement?model=${encodeURIComponent(activeModel)}`, { method: "POST" });
      setProblemStatement(result);
      notify(result.status === "queued" ? "Problem statement queued in the local worker. Check Activity Queue for progress." : result.status === "succeeded" ? "Local problem statement generated from verified signals." : result.reason || result.error || "No supported problem statement was generated.");
    } catch (cause) {
      setProblemError(cause.message || "Local problem statement could not be generated.");
    } finally {
      setProblemBusy(false);
    }
  };
  const evidenceLabel = selected?.isSample ? "Illustrative preview evidence" : selected?.isImported ? "Imported preview context" : selected?.isPreview ? "Browser preview context" : "Stored local source text";
  const evidenceContent = pageText || selected?.evidence || "No local source text is stored yet. Import a local page-text path before running research.";
  const sourceContent = expandedSource || evidenceContent.length < 900 ? evidenceContent : `${evidenceContent.slice(0, 900)}…`;
  const previewSignals = selected?.isSample && selected.signals
    ? Array.from({ length: Math.min(Number(selected.signals), 3) }, (_, index) => ({
        type: ["team growth", "workflow initiative", "product expansion"][index],
        evidence: [selected.evidence, "Illustrative context derived from sample data. Verify a company-owned page before use.", "Sample signal; no primary source was read by this preview."][index],
        confidence: Math.max(0.58, Number(selected.score || 0) / 100 - index * .08),
      }))
    : [];

  return (
    <div className="page-stack">
      <PageHeader eyebrow="WORKSPACE · EVIDENCE FIRST" title="Prospect Research" subtitle="Review saved source text separately from local AI synthesis. Confirm every cited passage before use." primaryAction={selected && <Link className="btn btn-ai" to={`/campaigns?productId=${encodeURIComponent(selected.productId)}&prospectId=${encodeURIComponent(selected.id)}`}><Icon as={MailPlus} className="icon-sm" />Generate Email Draft <Icon as={ArrowRight} className="icon-xs" /></Link>} secondaryAction={selected && <button type="button" className="btn btn-ai" onClick={rerun} disabled={busy || !connected}><Icon as={RefreshCw} className="icon-sm" />{busy ? "Starting…" : "Re-run Research"}</button>} />
      <OfflineGuardBanner compact />
      <section className="research-selector-panel panel"><div className="research-selector-copy"><span className="research-selector-icon"><Icon as={FileSearch} className="icon-md" /></span><div><strong>Research dossier</strong><small>{visibleProspects.length} prospect{visibleProspects.length === 1 ? "" : "s"} available · choose a local record to review</small></div></div><div className="research-selector-controls"><label className="form-field"><span>Filter by product</span><select value={productFilter} onChange={(event) => navigate(event.target.value === "all" ? "/research" : `/research?productId=${encodeURIComponent(event.target.value)}`)}><option value="all">All products</option>{products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="form-field"><span>Prospect</span><select value={selected?.id || ""} onChange={(event) => chooseProspect(event.target.value)}><option value="">Select a prospect</option>{visibleProspects.map((prospect) => <option key={prospect.id} value={prospect.id}>{prospect.company} · {prospect.contact}{prospect.isSample ? " · sample" : prospect.isImported ? " · imported preview" : prospect.isPreview ? " · preview" : ""}</option>)}</select></label></div></section>
      {!selected ? <section className="panel"><EmptyState icon={FileSearch} title="Choose a prospect to review" description={prospects.length ? "Select a prospect from the list above to inspect its score, stored evidence, and local AI summary." : "Import prospect records and add saved page text to begin a local research dossier."} action={prospects.length ? <Link className="btn btn-primary" to="/prospects">Browse prospects</Link> : <Link className="btn btn-primary" to="/prospects?import=true">Import prospects</Link>} /></section> : <>
        <section className="research-profile-heading"><div className="research-profile-identity"><span className="research-company-mark">{companyName.slice(0, 1).toUpperCase()}</span><div><div className="research-company-title-row"><h2>{companyName}</h2><StatusPill status={selected.status} /></div><p>{selected.contact} · {selected.role} {selected.domain && <><span>·</span><a href={`https://${selected.domain.replace(/^https?:\/\//, "")}`} target="_blank" rel="noreferrer">{selected.domain}<Icon as={ExternalLink} className="icon-xs" /></a></>}</p></div></div><div className="research-profile-score"><span className="score-caption">{selected.isPreview ? "PREVIEW FIT SCORE" : "LOCAL FIT SCORE"}</span><CircularScoreRing score={selected.score} size={64} strokeWidth={5} label={`${selected.isPreview ? "Preview" : "Local"} fit score ${selected.score} of 100`} /><span className="score-caption">0–100 · review evidence</span></div></section>
        <div className="research-dossier-grid">
          <div className="research-primary-column">
            <AiSynthesisBlock model={signalRun?.model_name} title="Local AI Synthesis" label="Research Context · not model output" isGenerated={!selected.isPreview && signalRun?.status === "succeeded"} className="research-ai-block">
              {loading ? <div className="skeleton-lines"><span /><span /><span /></div> : selected.isPreview ? <><p>{selected.summary || "No preview synthesis is available for this record yet."}</p><div className="preview-synthesis-note"><StatusPill status={selected.isSample ? "Queued" : "Needs Info"}>{selected.isSample ? "SEEDED SAMPLE" : selected.isImported ? "IMPORTED PREVIEW" : "BROWSER PREVIEW"}</StatusPill><span>{selected.isSample ? "Illustrative sample content; it was not generated by the local model." : "Imported preview context; no local model synthesis has been generated."}</span></div></> : signalRun?.status === "succeeded" ? <><p>{signals.length ? `Local model extracted ${signals.length} evidence-backed buying signal${signals.length === 1 ? "" : "s"}.` : "No qualifying buying signals were found in the stored source text."}</p><p className="ai-generated-context-note">This synthesis is produced from saved local source text and may be incomplete. Verify each evidence quote.</p></> : <><p>{signalRun?.error || selected.summary || "No completed local research run is stored for this prospect."}</p><div className="ai-generated-context-note">{signalRun?.status ? `Run status: ${signalRun.status}.` : "Source text remains distinct from any AI-generated content."}</div></>}
            </AiSynthesisBlock>
            <section className="panel source-panel"><div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon"><Icon as={FileSearch} className="icon-md" /></span><div><h2>Company Overview &amp; Evidence</h2><p>{evidenceLabel} · {selected.isSample ? "Seeded sample content" : selected.isImported ? "Imported browser preview · not a stored page" : selected.isPreview ? "Browser preview content" : selected.pageTextPath ? `Local path · ${selected.pageTextPath}` : "No page-text path linked"}</p></div></div>{pageText && <span className="source-word-count mono-number">{pageText.trim().split(/\s+/).length.toLocaleString()} WORDS</span>}</div><div className="source-links-list" aria-label="Public source links">{publicUrl && <a href={publicUrl} target="_blank" rel="noreferrer"><Icon as={ExternalLink} className="icon-xs" />Company website · {selected.domain}</a>}{(selected.sourceLinks || []).map((source, index) => { const url = safePublicUrl(source); return url ? <a key={`${source}-${index}`} href={url} target="_blank" rel="noreferrer"><Icon as={ExternalLink} className="icon-xs" />{source}</a> : <span key={`${source}-${index}`}><Icon as={FileSearch} className="icon-xs" />{source}</span>; })}{!publicUrl && !(selected.sourceLinks || []).length && <span>No source URL is stored for this prospect.</span>}</div><div className="source-text-content">{sourceContent}</div>{evidenceContent.length > 900 && <button type="button" className="text-button" onClick={() => setExpandedSource((value) => !value)}>{expandedSource ? "Show less" : "Read full saved text"}<Icon as={ArrowRight} className="icon-xs" /></button>}<div className="source-provenance"><Icon as={ShieldCheck} className="icon-xs" />Source text is local and separate from model output. Validate source quality and recency.</div></section>
            <section className="signals-section"><div className="section-heading-row"><div><h2>Buying signals</h2><p>{selected.isSample ? "Illustrative sample signals · confirm from a primary source" : selected.isPreview ? "Preview record · no local model signals have been run" : "Evidence returned by the local signal extraction workflow"} · confidence threshold {signalConfidenceThreshold}% is a local review label only.</p></div><span className="signal-count-badge mono-number">{selected.isSample ? `${selected.signals || 0} SAMPLE` : selected.isPreview ? "0 PREVIEW" : `${signals.length} FOUND`}</span></div>{selected.isSample ? <div className="preview-signal-grid">{previewSignals.map((signal, index) => <SignalCard key={`${signal.type}-${index}`} signal={signal} index={index} confidenceThreshold={signalConfidenceThreshold} />)}{!previewSignals.length && <div className="no-signal-card"><span><Icon as={Sparkles} className="icon-md" /></span><p>No sample signals are attached to this prospect.</p></div>}</div> : selected.isPreview ? <div className="no-signal-card"><span><Icon as={Sparkles} className="icon-md" /></span><p>This imported preview record has no locally generated evidence signals.</p></div> : loading ? <div className="skeleton-lines"><span /><span /></div> : signals.length ? <div className="preview-signal-grid">{signals.map((signal, index) => <SignalCard key={`${signal.type}-${index}`} signal={signal} index={index} confidenceThreshold={signalConfidenceThreshold} />)}</div> : <div className="no-signal-card"><span><Icon as={Sparkles} className="icon-md" /></span><p>{signalRun?.status === "succeeded" ? "No qualifying evidence-backed signals were returned." : "No completed signal extraction is available."}</p>{!selected.pageTextPath && <span>Import a local page-text path to provide evidence.</span>}</div>}</section>
            <AiSynthesisBlock model={problemStatement?.model_name} title="AI-Generated Problem Statement" label="Potential Business Problem · not model output" isGenerated={problemStatement?.status === "succeeded" && Boolean(problemStatement?.statement)} className="research-problem-block">
              {problemStatement?.status === "succeeded" && problemStatement?.statement ? <><p>{problemStatement.statement}</p><div className="problem-evidence-list"><span className="detail-label">VERIFIED EVIDENCE SPANS</span>{(problemStatement.evidence || []).map((quote, index) => <blockquote key={`${quote}-${index}`}>“{quote}”</blockquote>)}</div><div className="ai-generated-context-note">Generated by the selected local model from stored profile, ICP, and verified signal evidence.</div></> : selected.isPreview ? <p>Preview records do not run problem-statement inference. Review the saved source and signal examples before drafting.</p> : problemStatement?.status === "queued" || problemStatement?.status === "running" ? <p>Problem-statement generation is {problemStatement.status} in the local worker. Check Activity Queue for progress.</p> : problemStatement?.status === "skipped" ? <p>{problemStatement.reason || "No verified signal evidence is available for a supported problem statement."}</p> : <p>{problemStatement?.error || "Generate a conservative problem statement from this prospect’s verified local signals. The result is saved in SQLite."}</p>}
              {!selected.isPreview && <button type="button" className="btn btn-ai btn-sm research-problem-action" onClick={generateProblemStatement} disabled={problemBusy || !connected || isDemoConnection}>{problemBusy ? "Generating locally…" : problemStatement?.status === "succeeded" ? "Regenerate Problem Statement" : "Generate Problem Statement"}</button>}
              {problemError && <p className="form-error" role="alert">{problemError}</p>}
            </AiSynthesisBlock>
            <section className="panel product-relevance-panel"><div className="panel-heading"><div><h2>Product Relevance</h2><p>Stored score and ICP context · not an AI synthesis claim</p></div></div><div className="product-relevance-summary"><CircularScoreRing score={selected.score} size={58} color={Number(selected.score || 0) >= fitScoreThreshold ? "emerald" : "amber"} label={`Product fit ${selected.score} of 100`} /><div><span className="detail-label">LOCAL FIT SCORE</span><strong className="mono-number">{Number(selected.score || 0)} / 100</strong><StatusPill status={Number(selected.score || 0) >= fitScoreThreshold ? "High Fit" : "Needs Review"}>{Number(selected.score || 0) >= fitScoreThreshold ? `MEETS ${fitScoreThreshold}% THRESHOLD` : `BELOW ${fitScoreThreshold}% THRESHOLD`}</StatusPill></div></div><dl className="product-relevance-list"><div><dt>Product / ICP</dt><dd>{product?.name || "Not linked"}</dd></div><div><dt>Target market</dt><dd>{product?.targetMarket || "Not configured"}</dd></div><div><dt>ICP criteria</dt><dd>{product?.icpCriteria || "Not configured"}</dd></div></dl></section>
            <section className="panel recommended-approach-panel"><div className="panel-heading"><div><h2>Recommended Sales Approach</h2><p>Review-first guidance · not generated model copy</p></div></div><ol><li>Verify the source passage and its recency.</li><li>Choose one supported buying signal; avoid adding unverified claims.</li><li>Generate, edit, and save a draft for human review.</li></ol><Link to={`/campaigns?productId=${encodeURIComponent(selected.productId)}&prospectId=${encodeURIComponent(selected.id)}`} className="btn btn-ai btn-full"><Icon as={MailPlus} className="icon-sm" />Generate Email Draft <Icon as={ArrowRight} className="icon-xs" /></Link></section>
          </div>
          <aside className="research-side-column"><section className="panel firmographics-panel"><div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon"><Icon as={Globe2} className="icon-md" /></span><div><h2>Firmographics</h2><p>Record details from the local prospect list</p></div></div></div><dl className="firmographic-list"><div><dt>Industry</dt><dd>{selected.industry || "Not specified"}</dd></div><div><dt>Employee count</dt><dd>{selected.employeeCount ? Number(selected.employeeCount).toLocaleString() : "Not provided"}</dd></div><div><dt>Company domain</dt><dd>{selected.domain || "Not provided"}</dd></div><div><dt>Contact</dt><dd>{selected.contact || "Not provided"}</dd></div><div><dt>Title</dt><dd>{selected.role || "Not provided"}</dd></div><div><dt>Email</dt><dd>{selected.email || "Not provided"}</dd></div><div><dt>Product / ICP</dt><dd>{product?.name || "Not linked"}</dd></div><div><dt>Do not contact</dt><dd>{selected.doNotContact ? <StatusPill status="Failed">Yes · suppressed</StatusPill> : "No"}</dd></div></dl><div className="firmographic-footer"><span className="storage-note"><span className="status-dot status-dot-green" />{selected.isSample ? "Seeded sample" : selected.isImported ? "Imported preview" : selected.isPreview ? "Browser preview" : "SQLite record"}</span><span className="firmographic-updated">Updated {selected.updatedAt}</span></div></section>
            <section className="panel dossier-actions-panel"><div className="panel-heading"><div><h2>Research controls</h2><p>Refresh local signals when source text changes.</p></div></div><button type="button" onClick={rerun} className="btn btn-ai btn-full" disabled={busy || !connected}>{busy ? <Icon as={RefreshCw} className="icon-sm icon-spin" /> : <Icon as={RefreshCw} className="icon-sm" />}{busy ? "Starting local task…" : "Re-run Research"}</button>{error && <p className="form-error" role="alert">{error}</p>}<p className="no-send-footnote"><Icon as={ShieldCheck} className="icon-xs" />Email is draft-only · never auto-sent.</p></section>
            <Link to="/prospects" className="research-back-link"><Icon as={ArrowLeft} className="icon-xs" />Back to prospects</Link>
          </aside>
        </div>
      </>}
    </div>
  );
}
