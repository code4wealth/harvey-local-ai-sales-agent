import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Boxes, Check, Edit3, ExternalLink, FileSearch, Globe2, Plus, Sparkles, Trash2, X } from "lucide-react";
import { Drawer, EmptyState, Icon, OfflineGuardBanner, PageHeader, StatusPill } from "../ui.jsx";
import { useWorkspace } from "../WorkspaceContext.jsx";

const blankProduct = {
  name: "",
  company: "",
  website: "",
  pricing: "",
  targetMarket: "",
  icpTags: "",
  description: "",
  benefits: "",
  icpCriteria: "",
  docsPath: "",
};

function ProductFormField({ label, name, value, onChange, textarea = false, placeholder = "", required = false, rows = 3, help }) {
  const Control = textarea ? "textarea" : "input";
  return (
    <label className="form-field">
      <span>{label}{required && <b className="field-required">*</b>}</span>
      <Control name={name} value={value ?? ""} onChange={onChange} placeholder={placeholder} required={required} rows={textarea ? rows : undefined} />
      {help && <small className="field-help">{help}</small>}
    </label>
  );
}

function ProductEditor({ product, onClose }) {
  const { createProduct, updateProduct, notify } = useWorkspace();
  const [form, setForm] = useState(() => product ? {
    name: product.name || "",
    company: product.company || "",
    website: product.website || "",
    pricing: product.pricing || "",
    targetMarket: product.targetMarket || "",
    icpTags: (product.icpTags || []).join(", "),
    description: product.description || "",
    benefits: (product.benefits || []).join("\n"),
    icpCriteria: product.icpCriteria || "",
    docsPath: product.docsPath || "",
  } : blankProduct);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const onChange = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const details = {
        ...form,
        icpTags: form.icpTags.split(",").map((tag) => tag.trim()).filter(Boolean),
        benefits: form.benefits.split("\n").map((benefit) => benefit.trim()).filter(Boolean),
      };
      if (product) await updateProduct(product.id, details);
      else await createProduct(details);
      onClose();
    } catch (cause) {
      setError(cause.message || "Product could not be saved.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={product ? "Edit product & ICP" : "Create product & ICP"} description="Your product context stays in this browser or the local SQLite workspace." onClose={onClose}>
      <form className="drawer-form" onSubmit={save}>
        <div className="form-section-caption"><span className="form-step-number">01</span><div><strong>Product basics</strong><small>Tell Sellbird what you offer.</small></div></div>
        <div className="form-grid-two">
          <ProductFormField label="Product name" name="name" value={form.name} onChange={onChange} placeholder="e.g. Sellbird Core" required />
          <ProductFormField label="Company" name="company" value={form.company} onChange={onChange} placeholder="Your organization" />
        </div>
        <div className="form-grid-two">
          <ProductFormField label="Website" name="website" value={form.website} onChange={onChange} placeholder="example.com" />
          <ProductFormField label="Pricing" name="pricing" value={form.pricing} onChange={onChange} placeholder="$149 / month" />
        </div>
        <ProductFormField label="Short description" name="description" value={form.description} onChange={onChange} textarea placeholder="What does this product help customers do?" rows={3} />
        <div className="form-section-caption form-section-spaced"><span className="form-step-number">02</span><div><strong>Ideal customer profile</strong><small>Use these details to focus local prospect research.</small></div></div>
        <ProductFormField label="Target market" name="targetMarket" value={form.targetMarket} onChange={onChange} placeholder="Industry, team size, geography" />
        <ProductFormField label="ICP tags" name="icpTags" value={form.icpTags} onChange={onChange} placeholder="Revenue Operations, SaaS, 50–500 employees" help="Separate tags with commas." />
        <ProductFormField label="ICP criteria" name="icpCriteria" value={form.icpCriteria} onChange={onChange} textarea placeholder="Describe the best-fit organization and buying context." rows={4} />
        <ProductFormField label="Key benefits" name="benefits" value={form.benefits} onChange={onChange} textarea placeholder="One benefit per line" rows={3} />
        <ProductFormField label="Local product docs path (optional)" name="docsPath" value={form.docsPath} onChange={onChange} placeholder="data/company_info/product.md" help="A local path is never uploaded. The API validates configured data directories." />
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="drawer-safety-note"><Icon as={Sparkles} className="icon-sm" />Product and ICP information is used for local matching and draft context only.</div>
        <div className="drawer-form-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button><button type="submit" className="btn btn-dark" disabled={busy}>{busy ? "Saving…" : product ? "Save changes" : "Create product"}</button></div>
      </form>
    </Drawer>
  );
}

function ProductCard({ product, matched, onEdit, onDelete }) {
  const matchPercent = product.prospects ? Math.round((product.researched / product.prospects) * 100) : 0;
  return (
    <article className="product-card">
      <div className="product-card-top">
        <span className="product-card-icon"><Icon as={Boxes} className="icon-lg" /></span>
        <div className="product-card-actions">
          <StatusPill status={product.isPreview ? "Needs Info" : "Saved"}>{product.isSample ? "Seeded sample" : product.isImported ? "Imported preview" : product.isPreview ? "Browser preview" : "SQLite"}</StatusPill>
          <button type="button" className="icon-button" onClick={() => onEdit(product)} aria-label={`Edit ${product.name}`} title="Edit product"><Icon as={Edit3} className="icon-sm" /></button>
          <button type="button" className="icon-button icon-button-danger" onClick={() => onDelete(product)} aria-label={`Delete ${product.name}`} title="Delete product"><Icon as={Trash2} className="icon-sm" /></button>
        </div>
      </div>
      <div className="product-card-copy"><h2>{product.name}</h2><p>{product.description || "Add a concise description to give your local AI useful product context."}</p></div>
      <div className="product-card-meta">
        {product.company && <span><Icon as={Boxes} className="icon-xs" />{product.company}</span>}
        {product.website && <span><Icon as={Globe2} className="icon-xs" />{product.website}</span>}
        {product.pricing && <span><Icon as={Sparkles} className="icon-xs" />{product.pricing}</span>}
      </div>
      <div className="product-market-block"><span className="detail-label">TARGET MARKET</span><p>{product.targetMarket || "Target market not configured yet."}</p>{product.icpCriteria && <p className="product-criteria-copy">{product.icpCriteria}</p>}<div className="tag-list">{product.icpTags?.length ? product.icpTags.slice(0, 4).map((tag) => <span key={tag} className="tag">{tag}</span>) : <span className="tag tag-muted">No ICP tags</span>}</div></div>
      <div className="product-kpis">
        <div><strong className="mono-number">{Number(product.prospects || 0).toLocaleString()}</strong><span>Prospects</span></div>
        <div><strong className="mono-number">{Number(product.researched || 0).toLocaleString()}</strong><span>Researched</span></div>
        <div><strong className="mono-number">{Number(product.drafts || 0).toLocaleString()}</strong><span>Saved drafts</span></div>
      </div>
      <div className="product-progress-track" aria-label={`${matchPercent}% researched`}><span style={{ width: `${matchPercent}%` }} /></div>
      <div className="product-progress-label"><span>{matchPercent}% researched</span><span>Average fit <strong className="mono-number">{Number(product.averageScore || 0)}</strong></span></div>
      <div className="product-card-footer"><Link to={`/prospects?productId=${encodeURIComponent(product.id)}`} className="btn btn-secondary btn-sm">View Matching Prospects <Icon as={ArrowRight} className="icon-xs" /></Link><Link to={`/research?productId=${encodeURIComponent(product.id)}`} className="btn btn-text btn-sm"><Icon as={FileSearch} className="icon-xs" />Research</Link></div>
      <span className="sr-only">{matched} matching prospect records currently loaded.</span>
    </article>
  );
}

export default function ProductsPage() {
  const { products, prospects, deleteProduct, notify, previewMode } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();
  const [editor, setEditor] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [query, setQuery] = useState("");
  const [deleting, setDeleting] = useState(false);
  useEffect(() => {
    const id = searchParams.get("productId");
    const match = id && products.find((product) => String(product.id) === id);
    if (match && searchParams.get("edit") === "true") setEditor(match);
  }, [products, searchParams]);
  const focusedProductId = searchParams.get("productId");
  const focusedProduct = products.find((product) => String(product.id) === focusedProductId);
  const filtered = products.filter((product) => (!focusedProductId || String(product.id) === focusedProductId) && `${product.name} ${product.company} ${product.targetMarket} ${(product.icpTags || []).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const addNew = () => { setSearchParams({}); setEditor({ create: true }); };
  const closeEditor = () => { setEditor(null); setSearchParams((current) => { const next = new URLSearchParams(current); next.delete("edit"); next.delete("productId"); return next; }); };
  const editProduct = (product) => { setEditor(product); setSearchParams({ productId: String(product.id), edit: "true" }); };
  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteProduct(pendingDelete.id);
      setPendingDelete(null);
    } catch (error) {
      notify(error.message || "Product could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };
  const productProspects = (productId) => prospects.filter((prospect) => String(prospect.productId) === String(productId)).length;
  return (
    <div className="page-stack">
      <PageHeader eyebrow="WORKSPACE · PRODUCTS / ICPS" title="Products & ICPs" subtitle="Keep your product context and ideal customer profile close to every local research workflow." primaryAction={<button type="button" className="btn btn-primary" onClick={addNew}><Icon as={Plus} className="icon-sm" />Add Product</button>} />
      <OfflineGuardBanner compact />
      <div className="product-page-toolbar"><div className="product-page-count"><span className="product-count-icon"><Icon as={Boxes} className="icon-md" /></span><div><strong>{focusedProduct ? focusedProduct.name : `${products.length} product${products.length === 1 ? "" : "s"}`}</strong><small>{previewMode ? "Seeded and imported preview rows are tagged." : "Persisted in the local workspace."}</small></div></div><label className="inline-search"><span className="sr-only">Search products</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search products or ICPs…" /></label>{focusedProduct && <button type="button" className="text-button" onClick={() => setSearchParams({})}>Clear product filter <Icon as={X} className="icon-xs" /></button>}</div>
      {filtered.length ? <section className="products-grid" aria-label="Products and ideal customer profiles">{filtered.map((product) => <ProductCard key={product.id} product={product} matched={productProspects(product.id)} onEdit={editProduct} onDelete={setPendingDelete} />)}</section> : <section className="panel"><EmptyState icon={Boxes} title={query ? "No matching products" : "No products in this workspace"} description={query ? "Try another product name, market, or ICP tag." : "Create a product to define the context used by local prospect matching and reviewed Email Drafts."} action={!query && <button className="btn btn-primary" type="button" onClick={addNew}><Icon as={Plus} className="icon-sm" />Create your first product</button>} /></section>}
      <div className="privacy-callout"><span className="privacy-callout-mark"><Icon as={Check} className="icon-sm" /></span><p><strong>Local by design.</strong> Product descriptions, ICP criteria, and local document paths stay in your local workspace. Email drafts remain drafts and are never sent.</p><Link to="/settings/general">Privacy settings <Icon as={ExternalLink} className="icon-xs" /></Link></div>
      {editor !== null && <ProductEditor product={editor?.id ? editor : null} onClose={closeEditor} />}
      {pendingDelete && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setPendingDelete(null)}><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-product-heading"><span className="confirm-icon confirm-icon-danger"><Icon as={Trash2} className="icon-lg" /></span><h2 id="delete-product-heading">Delete {pendingDelete.name}?</h2><p>This removes the product and linked prospects and Email Drafts from the local workspace. This cannot be undone.</p><div className="modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setPendingDelete(null)}>Cancel</button><button type="button" className="btn btn-danger" onClick={confirmDelete} disabled={deleting}>{deleting ? "Deleting…" : "Delete product"}</button></div></section></div>}
    </div>
  );
}
