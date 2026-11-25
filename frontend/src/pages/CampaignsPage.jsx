import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, Clipboard, FileText, MailPlus, RefreshCw, Save, ShieldCheck, Sparkles, WandSparkles } from "lucide-react";
import { apiRequest, useWorkspace } from "../WorkspaceContext.jsx";
import { AiSynthesisBlock, Icon, OfflineGuardBanner, PageHeader, StatusPill } from "../ui.jsx";

export default function CampaignsPage() {
  const {
    products,
    prospects,
    drafts,
    activeModel,
    connected,
    isDemoConnection,
    apiStatus,
    createEmailDraft,
    saveDraft,
    notify,
  } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();
  const [productId, setProductId] = useState(searchParams.get("productId") || "");
  const [prospectId, setProspectId] = useState(searchParams.get("prospectId") || "");
  const [draftId, setDraftId] = useState(searchParams.get("draftId") || "");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [context, setContext] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draftStatus, setDraftStatus] = useState("");
  const [copied, setCopied] = useState(false);
  const [sqliteDraftSnapshot, setSqliteDraftSnapshot] = useState(null);
  const queriedSqliteDrafts = useRef(new Set());
  const productProspects = useMemo(() => prospects.filter((prospect) => productId === "" || String(prospect.productId) === String(productId)), [prospects, productId]);
  const selectedProspect = prospects.find((prospect) => String(prospect.id) === String(prospectId));
  const selectedProduct = products.find((product) => String(product.id) === String(productId)) || products.find((product) => String(product.id) === String(selectedProspect?.productId));
  const savedDraft = drafts.find((draft) => String(draft.id) === String(draftId));
  const modelPreference = apiStatus?.ollama?.requested_model || activeModel;
  const resolvedModel = apiStatus?.ollama?.model;
  const modelStatusLabel = apiStatus?.ollama?.model_installed === true
    ? "Resolved local model"
    : apiStatus?.ollama?.model_installed === false
      ? "Backend preference · not installed"
      : "Backend model preference · not verified";
  const isFollowUpMode = searchParams.get("mode") === "followup";
  const isNewComposition = searchParams.get("new") === "true";
  const batchIds = (searchParams.get("prospectIds") || "").split(",").filter(Boolean);
  const batchProspects = batchIds.map((id) => prospects.find((prospect) => String(prospect.id) === id)).filter(Boolean);
  const matchesSqliteDraft = Boolean(
    sqliteDraftSnapshot?.id != null
    && subject.trim() === sqliteDraftSnapshot.subject
    && body.trim() === sqliteDraftSnapshot.body,
  ) || Boolean(savedDraft?.isPersisted && savedDraft.backendDraftId != null && subject === savedDraft.subject && body === savedDraft.body);
  const isBrowserPreviewDraft = Boolean(selectedProspect?.isPreview || selectedProspect?.isSample || selectedProspect?.isImported || isDemoConnection || savedDraft?.isPreview);
  const hasDraftContent = Boolean(savedDraft || sqliteDraftSnapshot || subject.trim() || body.trim());
  const draftStorageLabel = !hasDraftContent
    ? "Draft-Only · No draft saved yet"
    : matchesSqliteDraft
      ? "Draft-Only · Stored in Local SQLite"
      : isBrowserPreviewDraft
        ? "Draft-Only · Browser Preview"
        : savedDraft?.isPersisted
          ? "Draft-Only · Unsaved Browser Edits"
          : draftId && savedDraft
            ? "Draft-Only · Saved in this browser"
            : "Draft-Only · Unsaved composition";

  useEffect(() => {
    const queryProduct = searchParams.get("productId") || "";
    const queryProspect = searchParams.get("prospectId") || "";
    const queryDraft = searchParams.get("draftId") || "";
    const queryBatch = searchParams.get("prospectIds") || "";
    setProductId(queryProduct);
    setProspectId(queryProspect || queryBatch.split(",").filter(Boolean)[0] || "");
    setDraftId(queryDraft);
  }, [searchParams]);

  useEffect(() => {
    if (savedDraft) {
      setSubject(savedDraft.subject || "");
      setBody(savedDraft.body || "");
      setEvidence(savedDraft.evidence || "");
      setProductId(String(savedDraft.productId || ""));
      setProspectId(String(savedDraft.prospectId || ""));
      setSqliteDraftSnapshot(savedDraft.isPersisted ? { id: savedDraft.backendDraftId, subject: savedDraft.subject || "", body: savedDraft.body || "" } : null);
      setDraftStatus(savedDraft.isPersisted ? "Draft loaded from local SQLite · never sent." : "Saved browser Email Draft loaded · never sent.");
      return;
    }
    if (selectedProspect) {
      const existing = isNewComposition ? null : drafts.find((draft) => String(draft.prospectId) === String(selectedProspect.id));
      setSubject(existing?.subject || "");
      setBody(existing?.body || "");
      setEvidence(existing?.evidence || "");
      setProductId(String(selectedProspect.productId));
      setDraftId(existing ? String(existing.id) : "");
      setSqliteDraftSnapshot(existing?.isPersisted ? { id: existing.backendDraftId, subject: existing.subject || "", body: existing.body || "" } : null);
      setContext(selectedProspect.summary || "");
      setDraftStatus(existing ? existing.isPersisted ? "Most recent draft is stored in local SQLite." : "Most recent saved browser draft loaded." : "Choose Generate draft to start an editable composition.");
    } else if (!searchParams.get("prospectIds")) {
      setSubject("");
      setBody("");
      setEvidence("");
      setContext("");
      setDraftId("");
      setSqliteDraftSnapshot(null);
      setDraftStatus("Select a product and prospect to begin.");
    }
  }, [savedDraft, selectedProspect, drafts, searchParams]);

  useEffect(() => {
    if (!selectedProspect || selectedProspect.isPreview || isDemoConnection || isNewComposition) return;
    const existing = drafts.find((draft) => String(draft.prospectId) === String(selectedProspect.id));
    if (existing) return;
    const key = `${selectedProspect.productId}:${selectedProspect.id}`;
    if (queriedSqliteDrafts.current.has(key)) return;
    queriedSqliteDrafts.current.add(key);
    let active = true;
    apiRequest(`/api/products/${encodeURIComponent(selectedProspect.productId)}/prospects/${encodeURIComponent(selectedProspect.id)}/draft`)
      .then((result) => {
        if (!active || result?.status !== "succeeded" || result.id == null || !result.subject || !result.body) return;
        setSubject(result.subject);
        setBody(result.body);
        const evidenceText = Array.isArray(result.evidence_used) ? result.evidence_used.join(" · ") : String(result.evidence_used || "");
        setEvidence(evidenceText);
        setSqliteDraftSnapshot({ id: result.id, subject: result.subject, body: result.body });
        const hydrated = saveDraft({ productId: selectedProspect.productId, prospectId: selectedProspect.id, subject: result.subject, body: result.body, evidence: evidenceText, isPersisted: true, backendDraftId: result.id, isPreview: false });
        setDraftId(hydrated.id);
        setDraftStatus("Draft loaded from local SQLite · review before use.");
      })
      .catch(() => {});
    return () => { active = false; };
  }, [selectedProspect?.id, selectedProspect?.productId, selectedProspect?.isPreview, isDemoConnection, isNewComposition, drafts, saveDraft]);

  useEffect(() => {
    if (prospectId && selectedProspect && productId !== String(selectedProspect.productId)) setProductId(String(selectedProspect.productId));
  }, [prospectId, selectedProspect, productId]);

  const updateQuery = (next) => setSearchParams((current) => {
    const params = new URLSearchParams(current);
    params.delete("prospectIds");
    params.delete("draftId");
    params.delete("new");
    for (const [key, value] of Object.entries(next)) {
      if (value) params.set(key, String(value));
      else params.delete(key);
    }
    return params;
  });
  const handleProductChange = (value) => {
    setProductId(value);
    const nextProspects = prospects.filter((prospect) => value === "" || String(prospect.productId) === String(value));
    const nextProspectId = nextProspects[0] ? String(nextProspects[0].id) : "";
    setProspectId(nextProspectId);
    setDraftId("");
    setSearchParams((current) => {
      const params = new URLSearchParams();
      if (value) params.set("productId", String(value));
      if (nextProspectId) params.set("prospectId", nextProspectId);
      if (current.get("mode")) params.set("mode", current.get("mode"));
      return params;
    });
  };
  const handleProspectChange = (value) => {
    setProspectId(value);
    setDraftId("");
    const nextProspect = prospects.find((prospect) => String(prospect.id) === String(value));
    const nextProductId = nextProspect ? String(nextProspect.productId) : productId;
    setProductId(nextProductId);
    setSearchParams((current) => {
      const params = new URLSearchParams();
      if (nextProductId) params.set("productId", String(nextProductId));
      if (nextProspect) params.set("prospectId", String(nextProspect.id));
      if (current.get("mode")) params.set("mode", current.get("mode"));
      return params;
    });
  };
  const generate = async () => {
    if (!selectedProspect) { setError("Select a prospect before generating an Email Draft."); return; }
    setBusy(true);
    setError("");
    setDraftStatus("Preparing a local draft…");
    try {
      const result = await createEmailDraft({ ...selectedProspect, summary: context || selectedProspect.summary });
      if (!result?.subject || !result?.body) {
        const message = result?.error || result?.detail || "The local workflow was queued. Check Activity Queue for its status.";
        setDraftStatus(message);
        setError(message);
        return;
      }
      const evidenceText = Array.isArray(result.evidence_used) ? result.evidence_used.join(" · ") : result.evidence_used || result.evidence || selectedProspect.summary || "";
      const isSqliteDraft = !result.isPreview && !isDemoConnection && result.status === "succeeded" && result.id != null;
      setSubject(result.subject);
      setBody(result.body);
      setEvidence(evidenceText);
      setSqliteDraftSnapshot(isSqliteDraft ? { id: result.id, subject: result.subject, body: result.body } : null);
      setDraftStatus(isSqliteDraft ? `Generated by ${result.model_name || activeModel} · stored in local SQLite · review before use.` : "Generated in clearly marked browser preview mode · review every detail.");
      setDraftId("");
      notify(isSqliteDraft ? "Editable Email Draft generated and stored in local SQLite · never sent." : "Editable preview Email Draft generated in this browser · never sent.");
    } catch (cause) {
      setError(cause.message || "Could not generate an Email Draft.");
      setDraftStatus("Draft generation needs attention.");
    } finally {
      setBusy(false);
    }
  };
  const save = () => {
    if (!selectedProspect) { setError("Choose a prospect before saving this Email Draft."); return; }
    if (!subject.trim() || !body.trim()) { setError("A subject and draft body are required before saving."); return; }
    const isPersisted = Boolean(sqliteDraftSnapshot?.id != null && !selectedProspect.isPreview && !isDemoConnection && subject.trim() === sqliteDraftSnapshot.subject && body.trim() === sqliteDraftSnapshot.body);
    const saved = saveDraft({ id: draftId || undefined, productId: selectedProspect.productId, prospectId: selectedProspect.id, subject: subject.trim(), body: body.trim(), evidence, isPersisted, backendDraftId: isPersisted ? sqliteDraftSnapshot.id : null, isPreview: selectedProspect.isPreview || isDemoConnection, isSample: selectedProspect.isSample, isImported: selectedProspect.isImported });
    setDraftId(saved.id);
    setDraftStatus(isPersisted ? "Draft-Only · Stored in Local SQLite" : saved.isPreview ? "Draft-Only · Saved as browser preview data" : "Draft-Only · Saved in this browser");
    if (!isPersisted) setSqliteDraftSnapshot(null);
    updateQuery({ productId: selectedProspect.productId, prospectId: selectedProspect.id, draftId: saved.id });
  };
  const copy = async () => {
    if (!subject.trim() && !body.trim()) return;
    const content = `Subject: ${subject}\n\n${body}`;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
      notify("Draft copied to clipboard · not sent.");
    } catch {
      setError("Clipboard access was blocked by this browser. Select and copy the draft manually.");
    }
  };
  const generateBatch = async () => {
    if (!batchProspects.length) return;
    setBusy(true);
    setError("");
    let savedCount = 0;
    let sqliteCount = 0;
    try {
      for (const prospect of batchProspects) {
        const generated = await createEmailDraft(prospect);
        if (generated?.subject && generated?.body) {
          const isPreview = generated.isPreview || prospect.isPreview || isDemoConnection;
          const isPersisted = !isPreview && generated.status === "succeeded" && generated.id != null;
          const evidenceText = Array.isArray(generated.evidence_used) ? generated.evidence_used.join(" · ") : generated.evidence_used || generated.evidence || prospect.summary;
          saveDraft({ productId: prospect.productId, prospectId: prospect.id, subject: generated.subject, body: generated.body, evidence: evidenceText, isPreview, isPersisted, backendDraftId: isPersisted ? generated.id : null, isSample: prospect.isSample, isImported: prospect.isImported });
          savedCount += 1;
          if (isPersisted) sqliteCount += 1;
        }
      }
      setDraftStatus(`${savedCount} of ${batchProspects.length} editable Email Drafts saved; ${sqliteCount} stored in local SQLite and the remainder in browser preview. None were sent.`);
      notify(`${savedCount} draft${savedCount === 1 ? "" : "s"} saved locally · never sent.`);
    } catch (cause) {
      setError(cause.message || "Batch generation did not complete.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader eyebrow={isFollowUpMode ? "WORKSPACE · FOLLOW-UP DRAFT" : "WORKSPACE · DRAFTS ONLY"} title="Email Draft Studio" subtitle={isFollowUpMode ? "Prepare a human-reviewed follow-up draft from local prospect context. Nothing is sent." : "Generate and edit contextual Email Drafts locally. Every message remains a draft for human review."} primaryAction={drafts.length > 0 && <label className="saved-draft-select"><span>Open saved draft</span><select value={draftId} onChange={(event) => { const nextDraftId = event.target.value; setDraftId(nextDraftId); updateQuery(nextDraftId ? { draftId: nextDraftId } : { productId, prospectId, new: "true" }); }}><option value="">New composition</option>{drafts.map((draft) => { const person = prospects.find((prospect) => String(prospect.id) === String(draft.prospectId)); return <option key={draft.id} value={draft.id}>{person?.company || "Prospect"} · {draft.subject}</option>; })}</select></label>} />
      <OfflineGuardBanner compact />
      <div className="draft-safety-banner"><span className="draft-safety-icon"><Icon as={ShieldCheck} className="icon-md" /></span><div><strong>Draft-Only Workspace · Never auto-sent</strong><p>Generated copy is editable, stays local, and must be reviewed by a person before use.</p><span className={`draft-storage-indicator ${matchesSqliteDraft ? "is-persisted" : hasDraftContent && isBrowserPreviewDraft ? "is-preview" : "is-browser"}`} role="status">{draftStorageLabel}</span></div><span className="draft-safety-tag">NO SEND ACTION</span></div>
      {batchProspects.length > 1 && <section className="panel batch-draft-panel"><div className="panel-heading"><div className="panel-title-with-icon"><span className="panel-icon panel-icon-brand"><Icon as={MailPlus} className="icon-md" /></span><div><h2>Batch draft selected prospects</h2><p>{batchProspects.length} selected from your prospect list · each draft is saved for review only.</p></div></div><button type="button" className="btn btn-ai" onClick={generateBatch} disabled={busy || !connected}><Icon as={WandSparkles} className="icon-sm" />{busy ? "Generating…" : "Generate selected drafts"}</button></div><div className="batch-prospect-list">{batchProspects.map((prospect) => <span className="batch-prospect-chip" key={prospect.id}>{prospect.company}<small>{prospect.contact}</small></span>)}</div></section>}
      <div className="campaign-composer-grid">
        <aside className="campaign-context-column">
          <section className="panel context-panel"><div className="panel-heading"><div><h2>Draft context</h2><p>Product, prospect, and optional focus notes.</p></div><span className="context-step-label">01</span></div>
            <label className="form-field"><span>Product / ICP</span><select value={productId} onChange={(event) => handleProductChange(event.target.value)}><option value="">Select a product</option>{products.map((product) => <option value={product.id} key={product.id}>{product.name}{product.isPreview ? " · preview" : ""}</option>)}</select></label>
            <label className="form-field"><span>Prospect</span><select value={prospectId} onChange={(event) => handleProspectChange(event.target.value)} disabled={!productProspects.length}><option value="">Select a prospect</option>{productProspects.map((prospect) => <option value={prospect.id} key={prospect.id}>{prospect.company} · {prospect.contact}{prospect.isSample ? " · sample" : prospect.isImported ? " · imported preview" : prospect.isPreview ? " · preview" : ""}</option>)}</select></label>
            {selectedProspect && <div className="draft-prospect-mini"><span className="company-avatar">{selectedProspect.company.slice(0, 1)}</span><div><strong>{selectedProspect.company}</strong><small>{selectedProspect.contact} · {selectedProspect.role}</small>{(selectedProspect.isSample || selectedProspect.isImported || selectedProspect.isPreview) && <em className="record-origin-tag">{selectedProspect.isSample ? "Seeded sample" : selectedProspect.isImported ? "Imported preview" : "Browser preview"}</em>}</div><StatusPill status={selectedProspect.status} /></div>}
            <label className="form-field context-notes-field"><span>Messaging context <em>Optional</em></span><textarea value={context} onChange={(event) => setContext(event.target.value)} rows={5} placeholder="Add a relevant product benefit, use case, or note for this draft." /></label>
            {selectedProspect && <AiSynthesisBlock model={activeModel} className="draft-context-synthesis" label="Prospect context · not model output"><p>{context || selectedProspect.summary || "No prospect summary is stored for this record."}</p><div className="ai-generated-context-note">{selectedProspect.isSample ? "Seeded sample context · verify against a primary source." : selectedProspect.isPreview ? "Preview context · not generated by Ollama." : "Stored local record context · review source evidence before use."}</div></AiSynthesisBlock>}
            <div className="context-evidence-note"><Icon as={FileText} className="icon-sm" /><span>Use verified research evidence. Preview records are illustrative and should be checked before use.</span></div>
            {selectedProspect && <Link to={`/research/${encodeURIComponent(selectedProspect.id)}`} className="text-link context-research-link"><Icon as={Sparkles} className="icon-xs" />Review research dossier</Link>}
          </section>
          <section className="model-context-card"><span className="model-context-icon"><Icon as={Sparkles} className="icon-sm" /></span><div><strong>{modelStatusLabel}</strong><code>{resolvedModel || modelPreference}</code></div><StatusPill status={isDemoConnection ? "Running" : apiStatus?.ollama?.model_installed === true ? "Ready" : apiStatus?.ollama?.model_installed === false ? "Review" : connected ? "Connected" : "Offline"}>{isDemoConnection ? "DEMO ONLY · NO INFERENCE" : apiStatus?.ollama?.model_installed === true ? "MODEL INSTALLED" : apiStatus?.ollama?.model_installed === false ? "MODEL MISSING" : connected ? "MODEL UNVERIFIED" : "OFFLINE"}</StatusPill></section>
        </aside>
        <section className="panel composer-panel" aria-labelledby="composer-heading"><div className="composer-heading-row"><div><p className="page-eyebrow">02 · COMPOSE</p><h2 id="composer-heading">{isFollowUpMode ? "Personalized Follow-up Draft" : "Personalized Email Draft"}</h2><p>Edit every field before saving for review.</p></div>{draftId && <StatusPill status="Saved">Saved {savedDraft?.savedAt || "locally"}</StatusPill>}</div>
          <div className="composer-actions composer-toolbar"><div className="composer-primary-actions"><button type="button" className="btn btn-ai" onClick={generate} disabled={busy || !selectedProspect || !connected}><Icon as={RefreshCw} className="icon-sm" />{busy ? "Working…" : subject || body ? "Regenerate Draft" : isFollowUpMode ? "Generate Follow-up Draft" : "Generate Draft"}</button><button type="button" className="btn btn-dark" onClick={save} disabled={!selectedProspect || !subject.trim() || !body.trim()}><Icon as={Save} className="icon-sm" />Save Draft</button></div><button type="button" className="btn btn-secondary" onClick={copy} disabled={!subject && !body}><Icon as={copied ? Check : Clipboard} className="icon-sm" />{copied ? "Copied" : "Copy Email"}</button></div>
          <label className="form-field composer-subject"><span>Subject line</span><input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="A short, relevant subject" maxLength={180} /></label>
          <label className="form-field composer-body-field"><span>Draft body</span><textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Choose a prospect, then generate or write your own draft. Keep it accurate, specific, and human-reviewed." rows={18} /></label>
          <div className="composer-meta-row"><span>{body.length.toLocaleString()} characters</span><span><Icon as={Sparkles} className="icon-xs" />AI-generated content can be inaccurate</span></div>
          {evidence && <div className="composer-evidence-note"><strong>Context used</strong><p>{evidence}</p></div>}
          {draftStatus && <p className="draft-status-line" role="status">{draftStatus}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="no-send-footnote"><Icon as={ShieldCheck} className="icon-sm" />There is no Send button or email integration in this workspace.</div>
          {draftId && selectedProspect && <Link className="reply-next-step-link" to={`/replies?prospectId=${encodeURIComponent(selectedProspect.id)}`}>Received a reply? Classify it <Icon as={ArrowRight} className="icon-xs" /></Link>}
        </section>
      </div>
      {!selectedProspect && !batchProspects.length && <div className="draft-empty-hint">Need a prospect first? <Link to="/prospects">Import or choose a prospect <span aria-hidden="true">→</span></Link></div>}
    </div>
  );
}
