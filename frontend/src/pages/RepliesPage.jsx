import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, CircleAlert, MailPlus, MessageSquareText, Search, ShieldCheck, Sparkles } from "lucide-react";
import { SAMPLE_INBOUND_REPLIES } from "../data.js";
import { useWorkspace } from "../WorkspaceContext.jsx";
import { AiSynthesisBlock, EmptyState, Icon, OfflineGuardBanner, PageHeader, StatusPill } from "../ui.jsx";

const LABELS = [
  ["all", "All replies"],
  ["interested", "Interested"],
  ["not_interested", "Not Interested"],
  ["needs_more_information", "Needs More Information"],
  ["follow_up_later", "Follow-up Later"],
];

function canonicalReplyState(rawLabel) {
  const label = String(rawLabel || "other").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (["interested", "meeting_request"].includes(label)) return { id: "interested", label: "Interested" };
  if (["not_interested", "unsubscribe"].includes(label)) return { id: "not_interested", label: "Not Interested" };
  if (["out_of_office", "follow_up_later"].includes(label)) return { id: "follow_up_later", label: "Follow-up Later" };
  return { id: "needs_more_information", label: "Needs More Information" };
}

function ReplyCard({ reply, prospect, onDraft }) {
  const percent = Math.round(Math.max(0, Math.min(1, Number(reply.confidence || 0))) * 100);
  const originLabel = reply.isSample ? reply.isPreview ? "SAMPLE · DEMO" : "SAMPLE INPUT" : reply.isImported ? "IMPORTED PREVIEW" : reply.isPreview ? "DEMO RULES" : "LOCAL RESULT";
  return (
    <article className="reply-card">
      <div className="reply-card-top"><span className="reply-type-mark"><Icon as={MessageSquareText} className="icon-sm" /></span><div className="reply-company"><strong>{prospect?.company || "Unlinked reply"}</strong><small>{prospect ? `${prospect.contact} · ${prospect.role}` : "No prospect associated"}</small></div><StatusPill status={canonicalReplyState(reply.label).label} /><span className={`reply-data-tag ${reply.isPreview || reply.isImported || reply.isSample ? "reply-data-preview" : ""}`}>{originLabel}</span></div>
      <blockquote className="reply-quote">“{reply.text || "Reply text not retained in this local result."}”</blockquote>
      <div className="reply-classification-row"><div><span className="reply-result-label">Local classification</span><strong>{canonicalReplyState(reply.label).label}</strong><small>{reply.rationale || "No rationale provided."}</small>{!reply.isPreview && reply.model_name && <AiSynthesisBlock model={reply.model_name} title="Local Reply Classification" isGenerated /> }</div><div className="reply-confidence"><span>CONFIDENCE</span><strong className="mono-number">{percent}%</strong><div className="reply-confidence-track"><span style={{ width: `${percent}%` }} /></div></div></div>
      <div className="reply-card-footer"><span>{reply.model_name || (reply.isPreview ? "Illustrative sample" : "Local Ollama")} · {reply.createdAt || "Just now"}</span>{prospect ? <button type="button" className="btn btn-secondary btn-sm" onClick={() => onDraft(prospect)}><Icon as={MailPlus} className="icon-xs" />Draft follow-up</button> : <Link to="/prospects" className="text-link">Link a prospect <Icon as={ArrowRight} className="icon-xs" /></Link>}</div>
    </article>
  );
}

export default function RepliesPage() {
  const { prospects, replyResults, classifyReply, connected, isDemoConnection, previewMode, apiStatus, notify } = useWorkspace();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [text, setText] = useState("");
  const [sampleInput, setSampleInput] = useState(false);
  const [prospectId, setProspectId] = useState(searchParams.get("prospectId") || "");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    setProspectId(searchParams.get("prospectId") || "");
  }, [searchParams]);
  const inbox = useMemo(() => {
    const local = replyResults.map((reply, index) => ({ ...reply, id: reply.id || `LOCAL-${reply.createdAt || index}` }));
    const ids = new Set(local.map((reply) => `${reply.label}-${reply.text}`));
    const preview = previewMode ? SAMPLE_INBOUND_REPLIES.filter((reply) => !ids.has(`${reply.label}-${reply.text}`)) : [];
    return [...local, ...preview].filter((reply) => {
      const filterMatch = filter === "all" || canonicalReplyState(reply.label).id === filter;
      const rowProspect = prospects.find((prospect) => String(prospect.id) === String(reply.prospectId));
      const queryMatch = !query.trim() || `${reply.text} ${reply.rationale} ${rowProspect?.company || ""} ${reply.label}`.toLowerCase().includes(query.trim().toLowerCase());
      return filterMatch && queryMatch;
    });
  }, [replyResults, previewMode, filter, query, prospects]);
  const selectProspect = (value) => {
    setProspectId(value);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set("prospectId", String(value));
      else next.delete("prospectId");
      return next;
    });
  };
  const loadSample = (reply) => {
    setText(reply.text);
    setSampleInput(true);
    selectProspect(String(reply.prospectId || ""));
    setError("");
    setNotice(reply.isPreview ? "Illustrative sample loaded. Classification will use demo rules only when Demo is enabled." : "");
  };
  const classify = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const result = await classifyReply(text.trim(), prospectId, { isSample: sampleInput });
      setNotice(result.isPreview ? "Preview classification complete using browser rules. It was not an Ollama run." : result.isPersisted === false ? `Classification complete on this machine with ${result.model_name || "the backend-resolved local model"}. SQLite persistence was not confirmed.` : `Classification complete on this machine with ${result.model_name || "the backend-resolved local model"}. Reply text was not stored in SQLite.`);
      setText("");
      setSampleInput(false);
      notify(result.isPreview ? "Demo classification saved in this browser · no model call was made." : "Reply classified by local Ollama · text remains local.");
      if (prospectId) navigate(`/replies?prospectId=${encodeURIComponent(prospectId)}`, { replace: true });
    } catch (cause) {
      setError(cause.message || "Reply could not be classified.");
    } finally {
      setBusy(false);
    }
  };
  const openFollowup = (prospect) => {
    if (prospect) navigate(`/campaigns?productId=${encodeURIComponent(prospect.productId)}&prospectId=${encodeURIComponent(prospect.id)}&mode=followup`);
  };
  const clearForm = () => { setText(""); setSampleInput(false); selectProspect(""); setError(""); setNotice(""); };
  const classifierModelNote = isDemoConnection
    ? "Demo mode is active: rules-based preview only."
    : apiStatus?.ollama?.model_installed === true
      ? `Ollama responds locally; ${apiStatus.ollama.model} is verified as installed.`
      : apiStatus?.ollama?.model_installed === false
        ? apiStatus.ollama.model_error || "The backend model preference is not installed."
        : connected
          ? "Ollama responds locally, but installed model tags are not verified."
          : "Start local Ollama or enable the labeled demo preview in Local AI & Models.";

  return (
    <div className="page-stack">
      <PageHeader eyebrow="WORKSPACE · INBOUND TRIAGE" title="Reply Classifier" subtitle="Classify inbound reply text locally, review the rationale, then create a human-reviewed follow-up draft." />
      <OfflineGuardBanner compact />
      <div className="reply-privacy-note"><Icon as={ShieldCheck} className="icon-sm" /><span><strong>Local-only classification.</strong> {isDemoConnection ? "Demo mode uses browser rules only; no Ollama inference runs." : "When Ollama is available, reply text is sent only to this machine and is not stored in SQLite by this flow."} The browser keeps classification history locally; drafts are never sent.</span>{isDemoConnection && <StatusPill status="Queued">DEMO RULES</StatusPill>}</div>
      <div className="replies-workspace-grid">
        <section className="panel reply-classifier-panel"><div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon panel-icon-brand"><Icon as={Sparkles} className="icon-md" /></span><div><h2>Classify a reply</h2><p>Paste text or try an illustrative sample scenario.</p></div></div><span className="reply-step-tag">LOCAL AI</span></div>
          <form onSubmit={classify}><label className="form-field"><span>Associate with a prospect <em>Optional</em></span><select value={prospectId} onChange={(event) => selectProspect(event.target.value)}><option value="">No prospect linked</option>{prospects.map((prospect) => <option key={prospect.id} value={prospect.id}>{prospect.company} · {prospect.contact}</option>)}</select></label><div className="sample-reply-controls"><span>Try an illustrative example</span>{SAMPLE_INBOUND_REPLIES.map((sample) => <button key={sample.id} type="button" onClick={() => loadSample(sample)}>{canonicalReplyState(sample.label).label}</button>)}</div><label className="form-field"><span>Inbound reply text</span><textarea value={text} onChange={(event) => { setText(event.target.value); setSampleInput(false); }} rows={7} maxLength={10000} placeholder="Paste an inbound reply here. Live classification uses only local Ollama; demo mode uses browser rules. Reply text is not saved to SQLite." required /></label><div className="reply-input-footer"><span className="mono-number">{text.length.toLocaleString()} / 10,000 characters</span><span><Icon as={ShieldCheck} className="icon-xs" />Not an email integration</span></div>{error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="form-success" role="status">{notice}</p>}<div className="reply-form-actions"><button type="button" className="btn btn-secondary" onClick={clearForm} disabled={!text && !prospectId}>Clear</button><button type="submit" className="btn btn-ai" disabled={!connected || (!isDemoConnection && apiStatus?.ollama?.model_installed === false) || !text.trim() || busy}><Icon as={Sparkles} className="icon-sm" />{busy ? "Classifying locally…" : "Classify reply"}</button></div><p className="classifier-model-note"><span className={`status-dot ${isDemoConnection ? "status-dot-amber" : connected ? "status-dot-green" : "status-dot-rose"}`} />{classifierModelNote}</p></form>
        </section>
        <aside className="reply-label-guide"><div className="reply-guide-header"><span className="reply-guide-icon"><Icon as={MessageSquareText} className="icon-md" /></span><div><h2>Classification labels</h2><p>One local label with a confidence and brief rationale.</p></div></div><div className="reply-label-list">{LABELS.filter(([id]) => id !== "all").map(([id, label]) => <div key={id}><span className={`reply-label-swatch reply-label-${id}`} />{label}</div>)}</div><div className="reply-classification-summary"><p>Most recent local results by label</p>{LABELS.filter(([id]) => id !== "all").map(([id, label]) => { const count = replyResults.filter((reply) => canonicalReplyState(reply.label).id === id).length; return <div key={id}><span>{label}</span><strong>{count}</strong></div>; })}</div><div className="reply-guide-footnote"><Icon as={CircleAlert} className="icon-xs" />A model label is a suggestion, not a decision. Review original text.</div></aside>
      </div>
      <section className="panel reply-inbox-panel"><div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon"><Icon as={MessageSquareText} className="icon-md" /></span><div><h2>Classification triage</h2><p>{replyResults.length ? `${replyResults.length} local result${replyResults.length === 1 ? "" : "s"} saved in this browser` : "No locally classified replies yet"}{previewMode ? " · sample examples are marked" : ""}</p></div></div><span className="reply-inbox-count mono-number">{inbox.length} VISIBLE</span></div>
        <div className="reply-inbox-filters"><label className="table-search"><Icon as={Search} className="icon-sm" /><input placeholder="Search reply text or company…" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search reply triage" /></label><label className="filter-select"><span className="sr-only">Filter by reply category</span><select value={filter} onChange={(event) => setFilter(event.target.value)}>{LABELS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>
        {inbox.length ? <div className="reply-cards-list">{inbox.map((reply) => <ReplyCard key={reply.id} reply={reply} prospect={prospects.find((prospect) => String(prospect.id) === String(reply.prospectId))} onDraft={openFollowup} />)}</div> : <EmptyState icon={MessageSquareText} title="No replies in this view" description={filter !== "all" || query ? "Try a different category or search query." : "Paste reply text above to create your first local classification."} compact />}
        {previewMode && !replyResults.length && inbox.length > 0 && <p className="preview-disclosure reply-preview-disclosure">Illustrative sample replies · not real inbox records. Classify pasted text to create a local result.</p>}
      </section>
      <div className="no-send-footnote"><Icon as={ShieldCheck} className="icon-sm" />Sellbird does not connect to an email account, send email, or automatically reply.</div>
    </div>
  );
}
