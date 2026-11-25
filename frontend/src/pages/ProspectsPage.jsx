import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowDownUp, Check, FileSearch, Filter, MailPlus, Plus, Search, Upload, Users, X } from "lucide-react";
import { csvEscape, parseCsv } from "../data.js";
import { useWorkspace } from "../WorkspaceContext.jsx";
import { CircularScoreRing, DataTable, EmptyState, Icon, Modal, OfflineGuardBanner, PageHeader, StatusPill } from "../ui.jsx";

const IMPORT_FIELDS = [
  { key: "company_name", label: "Company name", required: true },
  { key: "contact_name", label: "Contact name" },
  { key: "contact_title", label: "Job title" },
  { key: "company_domain", label: "Company domain" },
  { key: "employee_count", label: "Employee count" },
  { key: "contact_email", label: "Contact email" },
  { key: "page_text_path", label: "Local page-text path" },
  { key: "do_not_contact", label: "Do not contact" },
];

function defaultMapping(headers) {
  const synonyms = {
    company_name: ["company_name", "company", "organization", "organization_name"],
    contact_name: ["contact_name", "contact", "full_name", "name"],
    contact_title: ["contact_title", "title", "role", "job_title"],
    company_domain: ["company_domain", "domain", "website", "company_website"],
    employee_count: ["employee_count", "employees", "employees_count", "headcount"],
    contact_email: ["contact_email", "email", "email_address"],
    page_text_path: ["page_text_path", "page_path", "local_page_path"],
    do_not_contact: ["do_not_contact", "dnc", "suppressed"],
  };
  return Object.fromEntries(IMPORT_FIELDS.map(({ key }) => [key, headers.find((header) => synonyms[key].includes(header)) || ""]));
}

function CsvImportModal({ products, onClose, onImport }) {
  const [productId, setProductId] = useState(products[0] ? String(products[0].id) : "");
  const [parsed, setParsed] = useState(null);
  const [mapping, setMapping] = useState({});
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const readFile = async (file) => {
    if (!file) return;
    setFileName(file.name);
    setError("");
    setParsed(null);
    setResult(null);
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error("CSV is larger than 10 MB. Split it into smaller local files.");
      const text = await file.text();
      const next = parseCsv(text);
      setParsed({ ...next, sourceText: text });
      setMapping(defaultMapping(next.headers));
    } catch (cause) {
      setError(cause.message || "Could not parse this CSV file.");
    }
  };
  const handleImport = async () => {
    if (!productId) { setError("Choose a product for these prospects."); return; }
    if (!parsed) { setError("Choose a CSV file to continue."); return; }
    if (!mapping.company_name) { setError("Map a CSV column to Company name."); return; }
    const rows = parsed.rows.map((row) => Object.fromEntries(IMPORT_FIELDS.map(({ key }) => [key, mapping[key] ? String(row[mapping[key]] ?? "").trim() : ""])));
    if (rows.some((row) => !row.company_name)) { setError("Each prospect row needs a company name."); return; }
    const normalizedCsv = [IMPORT_FIELDS.map(({ key }) => key).join(","), ...rows.map((row) => IMPORT_FIELDS.map(({ key }) => csvEscape(row[key])).join(","))].join("\r\n");
    setBusy(true);
    setError("");
    try {
      const imported = await onImport(productId, normalizedCsv, { headers: IMPORT_FIELDS.map(({ key }) => key), rows });
      setResult(imported);
    } catch (cause) {
      setError(cause.message || "CSV import did not complete.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Import prospects from CSV" description="Choose a product, map your file, and review the first rows before importing locally." onClose={onClose} size="wide">
      {result ? <div className="import-success"><span className="import-success-icon"><Icon as={Check} className="icon-lg" /></span><h3>Import complete</h3><p><strong className="mono-number">{result.imported}</strong> records added{result.skipped ? ` · ${result.skipped} duplicates skipped` : ""}.</p><p className="import-preview-disclosure">{result.preview ? "These records were added to browser preview data, not SQLite." : "Prospects are stored in local SQLite. No data was uploaded."}</p><div className="modal-actions"><button type="button" className="btn btn-primary" onClick={onClose}>Done</button></div></div> : <div className="csv-import-body">
        <label className="form-field"><span>Product / ICP</span><select value={productId} onChange={(event) => setProductId(event.target.value)}><option value="">Select a product</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}{product.isPreview ? " · preview" : ""}</option>)}</select></label>
        <label className={`csv-dropzone ${parsed ? "csv-dropzone-ready" : ""}`}><input className="sr-only" type="file" accept=".csv,text/csv" onChange={(event) => readFile(event.target.files?.[0])} /><span className="csv-dropzone-icon"><Icon as={Upload} className="icon-lg" /></span><strong>{fileName || "Choose a CSV file"}</strong><small>{parsed ? `${parsed.rows.length} data rows · UTF-8 CSV parsed in your browser` : "Your file is read locally in this browser and is not uploaded anywhere."}</small><span className="btn btn-secondary btn-sm">Browse files</span></label>
        {parsed && <section className="csv-mapping-panel"><div className="csv-mapping-heading"><div><h3>Map your columns</h3><p>Required field: company name. Unmapped fields are left blank.</p></div><span className="csv-row-count mono-number">{parsed.rows.length} ROWS</span></div><div className="csv-mapping-grid">{IMPORT_FIELDS.map(({ key, label, required }) => <label className="form-field" key={key}><span>{label}{required && <b className="field-required">*</b>}</span><select value={mapping[key] || ""} onChange={(event) => setMapping((current) => ({ ...current, [key]: event.target.value }))}><option value="">Do not import</option>{parsed.headers.map((header) => <option key={header} value={header}>{header}</option>)}</select></label>)}</div><div className="csv-preview-wrap"><table className="csv-preview-table"><thead><tr>{IMPORT_FIELDS.filter(({ key }) => mapping[key]).map(({ key, label }) => <th key={key}>{label}</th>)}</tr></thead><tbody>{parsed.rows.slice(0, 3).map((row, index) => <tr key={index}>{IMPORT_FIELDS.filter(({ key }) => mapping[key]).map(({ key }) => <td key={key}>{row[mapping[key]] || "—"}</td>)}</tr>)}</tbody></table></div></section>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="import-safety-note"><Icon as={Check} className="icon-sm" />Local-first import · only prospect fields are stored. Email features create drafts only; nothing is sent.</div>
        <div className="modal-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button><button type="button" className="btn btn-dark" onClick={handleImport} disabled={busy || !parsed}>{busy ? "Importing locally…" : `Import ${parsed?.rows.length || ""} prospects`}</button></div>
      </div>}
    </Modal>
  );
}

function AddProspectModal({ products, onClose, onAdd }) {
  const [productId, setProductId] = useState(products[0] ? String(products[0].id) : "");
  const [form, setForm] = useState({ company: "", contact: "", role: "", domain: "", employeeCount: "", email: "", pageTextPath: "", doNotContact: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const update = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.type === "checkbox" ? event.target.checked : event.target.value }));
  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onAdd(productId, form);
      onClose();
    } catch (cause) {
      setError(cause.message || "Prospect could not be added.");
    } finally {
      setBusy(false);
    }
  };
  return <Modal title="Add prospect" description="Create a local prospect record. Saved source paths stay on this machine." onClose={onClose}>
    <form className="drawer-form add-prospect-form" onSubmit={save}>
      <label className="form-field"><span>Product / ICP <b className="field-required">*</b></span><select value={productId} onChange={(event) => setProductId(event.target.value)} required><option value="">Select a product</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}{product.isPreview ? " · preview" : ""}</option>)}</select></label>
      <div className="form-grid-two"><label className="form-field"><span>Company name <b className="field-required">*</b></span><input name="company" value={form.company} onChange={update} required placeholder="Company" /></label><label className="form-field"><span>Company domain</span><input name="domain" value={form.domain} onChange={update} placeholder="example.com" /></label></div>
      <div className="form-grid-two"><label className="form-field"><span>Contact name</span><input name="contact" value={form.contact} onChange={update} placeholder="Contact name" /></label><label className="form-field"><span>Job title</span><input name="role" value={form.role} onChange={update} placeholder="Job title" /></label></div>
      <div className="form-grid-two"><label className="form-field"><span>Contact email</span><input name="email" value={form.email} onChange={update} type="email" placeholder="name@example.com" /></label><label className="form-field"><span>Employee count</span><input name="employeeCount" value={form.employeeCount} onChange={update} type="number" min="1" placeholder="100" /></label></div>
      <label className="form-field"><span>Local saved page-text path</span><input name="pageTextPath" value={form.pageTextPath} onChange={update} placeholder="data/pages/company.txt" /><small className="field-help">No public page is fetched automatically. Add a trusted local path if one exists.</small></label>
      <label className="do-not-contact-control"><input type="checkbox" name="doNotContact" checked={form.doNotContact} onChange={update} /><span>Mark as do-not-contact / suppressed</span></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button><button type="submit" className="btn btn-primary" disabled={busy || !productId}>{busy ? "Adding locally…" : "Add prospect"}</button></div>
    </form>
  </Modal>;
}

export default function ProspectsPage() {
  const { prospects, products, importProspectsCsv, addProspect, runResearch, notify, previewMode, fitScoreThreshold } = useWorkspace();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("search") || "");
  const [productId, setProductId] = useState(searchParams.get("productId") || "all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [minScore, setMinScore] = useState("all");
  const [selectedIds, setSelectedIds] = useState([]);
  const [sort, setSort] = useState({ key: "updatedAt", direction: "desc" });
  const [importOpen, setImportOpen] = useState(searchParams.get("import") === "true");
  const [addOpen, setAddOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  useEffect(() => {
    const queryProduct = searchParams.get("productId");
    if (queryProduct) setProductId(queryProduct);
    const search = searchParams.get("search");
    if (search !== null) setQuery(search);
    if (searchParams.get("import") === "true") setImportOpen(true);
  }, [searchParams]);
  const rows = useMemo(() => {
    const filtered = prospects.filter((prospect) => {
      const searchMatch = `${prospect.company} ${prospect.contact} ${prospect.role} ${prospect.domain} ${prospect.industry}`.toLowerCase().includes(query.trim().toLowerCase());
      const productMatch = productId === "all" || String(prospect.productId) === String(productId);
      const statusMatch = statusFilter === "all" || String(prospect.status).toLowerCase() === statusFilter.toLowerCase();
      const score = Number(prospect.score || 0);
      const scoreMatch = minScore === "all"
        || (minScore === "threshold" && score >= fitScoreThreshold)
        || (minScore === "0-49" && score >= 0 && score < 50)
        || (minScore === "50-74" && score >= 50 && score < 75)
        || (minScore === "75-100" && score >= 75);
      return searchMatch && productMatch && statusMatch && scoreMatch;
    });
    const direction = sort.direction === "asc" ? 1 : -1;
    filtered.sort((a, b) => {
      const left = a[sort.key] ?? "";
      const right = b[sort.key] ?? "";
      if (sort.key === "score") return (Number(left) - Number(right)) * direction;
      return String(left).localeCompare(String(right), undefined, { numeric: true }) * direction;
    });
    return filtered;
  }, [prospects, query, productId, statusFilter, minScore, sort, fitScoreThreshold]);
  const columns = [
    { key: "company", header: "Company & contact", sortKey: "company", width: "270px", render: (row) => <div className="company-cell"><span className="company-avatar">{row.company.slice(0, 1).toUpperCase()}</span><span><strong>{row.company}</strong><small>{row.contact} · {row.role}</small>{(row.isSample || row.isImported || row.isPreview) && <em className="record-origin-tag">{row.isSample ? "Seeded sample" : row.isImported ? "Imported preview" : "Browser preview"}</em>}</span></div> },
    { key: "domain", header: "Website", width: "160px", render: (row) => row.domain ? <a className="table-product-link" href={/^https?:\/\//i.test(row.domain) ? row.domain : `https://${row.domain}`} target="_blank" rel="noreferrer">{row.domain}</a> : <span className="industry-label">Not provided</span> },
    { key: "industry", header: "Industry", width: "145px", sortKey: "industry", render: (row) => <span className="industry-label">{row.industry || "Not specified"}</span> },
    { key: "product", header: "Product / ICP", width: "155px", render: (row) => <Link className="table-product-link" to={`/products?productId=${encodeURIComponent(row.productId)}`}>{products.find((product) => String(product.id) === String(row.productId))?.name || "Unknown product"}</Link> },
    { key: "score", header: "Fit score", width: "100px", sortKey: "score", render: (row) => <CircularScoreRing score={row.score} size={42} /> },
    { key: "status", header: "Research status", width: "150px", sortKey: "status", render: (row) => <StatusPill status={row.status} /> },
    { key: "updatedAt", header: "Updated", width: "145px", sortKey: "updatedAt", render: (row) => <span className="updated-label">{row.updatedAt}</span> },
    { key: "actions", header: "Actions", width: "155px", render: (row) => <div className="table-actions"><Link className="table-action-link" to={`/research/${encodeURIComponent(row.id)}`}>View Dossier</Link><Link className="table-action-link table-action-brand" to={`/campaigns?prospectId=${encodeURIComponent(row.id)}`}>Draft Email</Link></div> },
  ];
  const handleSort = (key) => setSort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));
  const importFile = async (selectedProduct, text, parsed) => {
    const result = await importProspectsCsv(selectedProduct, text, parsed);
    setProductId(String(selectedProduct));
    setSearchParams({ productId: String(selectedProduct) });
    setSelectedIds([]);
    return result;
  };
  const researchSelected = async () => {
    const selected = prospects.filter((prospect) => selectedIds.includes(String(prospect.id)));
    if (!selected.length) return;
    setBulkBusy(true);
    const results = await Promise.allSettled(selected.map((prospect) => runResearch(prospect)));
    const successCount = results.filter((result) => result.status === "fulfilled").length;
    const failures = results.filter((result) => result.status === "rejected");
    if (failures.length) notify(`${successCount} queued · ${failures.length} could not start. ${failures[0].reason?.message || "Check local Ollama status."}`);
    else notify(`${successCount} local research task${successCount === 1 ? "" : "s"} queued.`);
    setBulkBusy(false);
    setSelectedIds([]);
  };
  const draftSelected = () => {
    const ids = prospects.filter((prospect) => selectedIds.includes(String(prospect.id))).map((prospect) => String(prospect.id));
    if (ids.length) navigate(`/campaigns?prospectIds=${encodeURIComponent(ids.join(","))}`);
  };
  return (
    <div className="page-stack">
      <PageHeader eyebrow="WORKSPACE · LOCAL RECORDS" title="Prospects" subtitle="Search imported companies, inspect local research status, and create reviewable Email Drafts." secondaryAction={<button className="btn btn-secondary" type="button" onClick={() => { setImportOpen(true); setSearchParams((current) => { const next = new URLSearchParams(current); next.set("import", "true"); return next; }); }}><Icon as={Upload} className="icon-sm" />Import CSV</button>} primaryAction={<button className="btn btn-primary" type="button" onClick={() => setAddOpen(true)}><Icon as={Plus} className="icon-sm" />Add Prospect</button>} />
      <OfflineGuardBanner compact />
      <section className="prospects-summary-row"><div className="prospects-count-card"><span className="prospects-count-icon"><Icon as={Users} className="icon-md" /></span><div><strong className="mono-number">{prospects.length}</strong><span>Total prospects</span></div><i /><div><strong className="mono-number">{prospects.filter((row) => row.status === "Completed").length}</strong><span>Researched</span></div><i /><div><strong className="mono-number">{prospects.filter((row) => row.score >= 75).length}</strong><span>High fit</span></div></div><span className="local-data-caption"><span className={`status-dot ${previewMode ? "status-dot-amber" : "status-dot-green"}`} />{previewMode ? "Seeded samples and imports are tagged" : "Records in local SQLite"}</span></section>
      <section className="panel prospects-table-panel">
        <div className="prospects-filter-row"><label className="table-search"><Icon as={Search} className="icon-sm" /><input aria-label="Search prospects" placeholder="Search company, contact, or role…" value={query} onChange={(event) => setQuery(event.target.value)} /><kbd>/</kbd></label><label className="filter-select"><Icon as={Filter} className="icon-xs" /><span className="sr-only">Filter by product</span><select value={productId} onChange={(event) => setProductId(event.target.value)}><option value="all">All products</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}{product.isPreview ? " · preview" : ""}</option>)}</select></label><label className="filter-select"><Icon as={Filter} className="icon-xs" /><span className="sr-only">Filter by research status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All statuses</option><option value="Completed">Completed</option><option value="Queued">Queued</option><option value="Running">Running</option><option value="Awaiting Research">Awaiting Research</option><option value="Failed">Failed</option></select></label><label className="filter-select"><Icon as={ArrowDownUp} className="icon-xs" /><span className="sr-only">Minimum fit score</span><select value={minScore} onChange={(event) => setMinScore(event.target.value)}><option value="all">Any fit score</option><option value="threshold">Workspace threshold · {fitScoreThreshold}+</option><option value="75-100">75–100 · high fit</option><option value="50-74">50–74 · medium</option><option value="0-49">0–49 · low</option></select></label></div>
        {selectedIds.length > 0 && <div className="bulk-action-bar"><span><strong className="mono-number">{selectedIds.length}</strong> selected</span><button type="button" className="btn btn-ai btn-sm" onClick={researchSelected} disabled={bulkBusy}><Icon as={FileSearch} className="icon-xs" />{bulkBusy ? "Queueing…" : "Research selected"}</button><button type="button" className="btn btn-primary btn-sm" onClick={draftSelected}><Icon as={MailPlus} className="icon-xs" />Draft selected</button><button type="button" className="icon-button" onClick={() => setSelectedIds([])} aria-label="Clear selection"><Icon as={X} className="icon-sm" /></button></div>}
        <DataTable columns={columns} rows={rows} selectedIds={selectedIds} onSelectionChange={setSelectedIds} sort={sort} onSort={handleSort} minWidth={1280} emptyTitle={query || productId !== "all" || statusFilter !== "all" ? "No prospects match these filters" : "No prospects yet"} emptyDescription={query || productId !== "all" || statusFilter !== "all" ? "Adjust the search, product, status, or score filters." : "Import a CSV to add prospect records to this local workspace."} emptyAction={<button className="btn btn-primary btn-sm" type="button" onClick={() => setImportOpen(true)}><Icon as={Upload} className="icon-xs" />Import CSV</button>} />
        <div className="panel-footer-row"><span>Showing {rows.length} of {prospects.length} records</span><span className="storage-note"><span className="status-dot status-dot-green" />{previewMode ? "Preview records are illustrative" : "Stored locally in SQLite"}</span></div>
      </section>
      <p className="prospect-footnote"><Icon as={Check} className="icon-xs" />Research runs on saved local page text and local models. Drafts remain editable and are never sent.</p>
      {importOpen && <CsvImportModal products={products} onClose={() => { setImportOpen(false); setSearchParams((current) => { const next = new URLSearchParams(current); next.delete("import"); return next; }); }} onImport={importFile} />}
      {addOpen && <AddProspectModal products={products} onClose={() => setAddOpen(false)} onAdd={async (selectedProduct, details) => { const result = await addProspect(selectedProduct, details); setProductId(String(selectedProduct)); setSearchParams({ productId: String(selectedProduct) }); return result; }} />}
    </div>
  );
}
