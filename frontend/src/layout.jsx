import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Boxes,
  ChevronRight,
  Cpu,
  Database,
  FileSearch,
  LayoutDashboard,
  MailPlus,
  Menu,
  MessageSquareText,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Icon } from "./ui.jsx";

const NAV_ITEMS = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard, end: true },
  { label: "Products", path: "/products", icon: Boxes, badge: "products" },
  { label: "Prospects", path: "/prospects", icon: Users, badge: "prospects" },
  { label: "Prospect Research", path: "/research", icon: FileSearch },
  { label: "Email Drafts", path: "/campaigns", icon: MailPlus, badge: "drafts" },
  { label: "Reply Classifier", path: "/replies", icon: MessageSquareText },
  { label: "Activity Queue", path: "/activity", icon: Activity, badge: "tasks", liveDot: true },
  { label: "Local AI & Models", path: "/settings/models", icon: Cpu },
  { label: "General Settings", path: "/settings/general", icon: Settings },
];

const PAGE_CRUMBS = [
  ["/products", "Products"],
  ["/prospects", "Prospects"],
  ["/research", "Prospect Research"],
  ["/campaigns", "Email Drafts"],
  ["/replies", "Reply Classifier"],
  ["/activity", "Activity Queue"],
  ["/settings/models", "Local AI & Models"],
  ["/settings/general", "General & Storage"],
];

function engineLabel({ connected, isDemoConnection, apiState, apiStatus }) {
  if (isDemoConnection) return connected ? "Demo only · UI override" : "Demo offline · UI override";
  if (apiState === "loading") return "Checking local Ollama";
  if (apiStatus?.ollama?.state === "slow") return "Ollama responding slowly";
  return connected ? "Ollama connected" : "Ollama offline";
}

function SearchBox() {
  const navigate = useNavigate();
  const { products, prospects, tasks } = useWorkspace();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    const closeOnOutsideClick = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, []);

  useEffect(() => {
    const openSearch = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", openSearch);
    return () => window.removeEventListener("keydown", openSearch);
  }, []);

  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return [];
    const productMatches = products
      .filter((product) => `${product.name} ${product.company} ${product.targetMarket}`.toLowerCase().includes(term))
      .slice(0, 3)
      .map((product) => ({ type: "Product", label: product.name, detail: product.company, to: `/products?productId=${encodeURIComponent(product.id)}` }));
    const prospectMatches = prospects
      .filter((prospect) => `${prospect.company} ${prospect.contact} ${prospect.role} ${prospect.industry}`.toLowerCase().includes(term))
      .slice(0, 4)
      .map((prospect) => ({ type: "Prospect", label: prospect.company, detail: `${prospect.contact} · ${prospect.role}`, to: `/research/${encodeURIComponent(prospect.id)}` }));
    const taskMatches = tasks
      .filter((task) => `${task.title} ${task.type} ${task.id}`.toLowerCase().includes(term))
      .slice(0, 2)
      .map((task) => ({ type: "Task", label: task.title, detail: `${task.status} · ${task.id}`, to: "/activity" }));
    return [...productMatches, ...prospectMatches, ...taskMatches].slice(0, 7);
  }, [products, prospects, tasks, query]);

  const goToFirst = (event) => {
    event.preventDefault();
    if (results[0]) navigate(results[0].to);
    else if (query.trim()) navigate(`/prospects?search=${encodeURIComponent(query.trim())}`);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="global-search-wrap">
      <form className="global-search" role="search" onSubmit={goToFirst}>
        <Icon as={Search} className="icon-sm search-icon" />
        <input
          ref={inputRef}
          aria-label="Search prospects, companies, or tasks"
          placeholder="Search prospects, companies, or tasks..."
          value={query}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
        />
        <kbd>⌘K</kbd>
      </form>
      {open && query.trim() && (
        <div className="search-results" role="listbox" aria-label="Search results">
          {results.length ? results.map((result) => (
            <button key={`${result.type}-${result.label}`} type="button" className="search-result" onClick={() => { navigate(result.to); setOpen(false); setQuery(""); }}>
              <span className="search-result-type">{result.type}</span>
              <span className="search-result-copy"><strong>{result.label}</strong><small>{result.detail}</small></span>
            </button>
          )) : <p className="search-empty">No matches. Press Enter to search prospects.</p>}
        </div>
      )}
    </div>
  );
}

function Sidebar({ mobile = false, collapsed = false, onClose, onToggleCollapse }) {
  const location = useLocation();
  const {
    connected,
    isDemoConnection,
    activeModel,
    activeTaskCount,
    savedDraftCount,
    products,
    prospects,
    setDemoConnection,
    resetDemoConnection,
    storageMetrics,
    apiState,
    apiStatus,
  } = useWorkspace();
  const engineDot = isDemoConnection ? (connected ? "is-demo" : "is-offline") : apiState === "loading" || apiStatus?.ollama?.state === "slow" ? "is-checking" : connected ? "is-online" : "is-offline";
  const engineDetail = isDemoConnection
    ? connected ? "Demo connected · no inference" : "Disconnected · demo state"
    : apiState === "loading" ? "Checking local endpoint"
      : apiStatus?.ollama?.state === "slow" ? "Responding slowly"
        : apiStatus?.ollama?.state === "error" ? "Model-tag error"
          : connected ? "Connected" : "Disconnected";
  const readinessDetail = apiState === "loading"
    ? "Checking local readiness"
    : apiStatus?.local_readiness?.ready
      ? "Inference and embeddings ready"
      : apiStatus?.local_readiness
        ? "Local prerequisites need attention"
        : apiState === "offline" ? "Readiness unavailable" : "Readiness not reported";
  const toggleDemoState = () => isDemoConnection ? resetDemoConnection() : setDemoConnection(false);

  return (
    <aside className={`sidebar ${mobile ? "sidebar-mobile" : "sidebar-desktop"} ${collapsed && !mobile ? "sidebar-collapsed" : ""}`} aria-label={mobile ? "Mobile navigation" : "Primary navigation"}>
      <div className="sidebar-brand-row">
        <Link to="/" className="brand-lockup" onClick={onClose} title={collapsed ? "Sellbird AI Dashboard" : undefined}>
          <span className="brand-mark"><Icon as={Boxes} className="icon-md" /></span>
          {!collapsed && <><span className="brand-copy"><strong>Sellbird AI</strong><span>Local workspace</span></span><span className="local-badge">LOCAL-FIRST</span></>}
        </Link>
        {mobile
          ? <button type="button" className="icon-button mobile-close" onClick={onClose} aria-label="Close navigation"><Icon as={X} className="icon-md" /></button>
          : !collapsed && <button type="button" className="icon-button sidebar-collapse-button" onClick={onToggleCollapse} aria-label="Collapse navigation panel" title="Collapse navigation panel"><Icon as={PanelLeftClose} className="icon-sm" /></button>}
      </div>
      <nav className="sidebar-nav" aria-label="Workspace pages">
        {NAV_ITEMS.map(({ label, path, icon, badge, end, liveDot, settings }) => {
          const isActive = end
            ? location.pathname === "/"
            : path === "/research"
              ? location.pathname.startsWith("/research")
              : location.pathname === path;
          return (
            <Link key={path} to={path} title={collapsed ? label : undefined} aria-label={label} aria-current={isActive ? "page" : undefined} data-tooltip={label} className={`nav-link ${isActive ? "nav-link-active" : ""}`} onClick={onClose}>
              <span className="nav-link-icon-wrap"><Icon as={icon} className="nav-link-icon" />{liveDot && activeTaskCount > 0 && <i className="nav-live-dot" />}</span>
              {!collapsed && <span className="nav-link-label">{label}</span>}
              {!collapsed && badge === "products" && products.length > 0 && <span className="nav-count nav-count-neutral">{products.length}</span>}
              {!collapsed && badge === "prospects" && prospects.length > 0 && <span className="nav-count nav-count-neutral">{prospects.length}</span>}
              {!collapsed && badge === "drafts" && savedDraftCount > 0 && <span className="nav-count nav-count-brand">{savedDraftCount}</span>}
              {!collapsed && badge === "tasks" && activeTaskCount > 0 && <span className="nav-count nav-count-brand">{activeTaskCount}</span>}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-bottom-stack">
        <div className="sidebar-engine-card">
          <Link to="/settings/models" className="sidebar-engine-link" onClick={onClose} aria-label={`Local Ollama Engine · ${engineDetail} · model preference ${activeModel}`}>
            <span className="engine-icon"><Icon as={Cpu} className="icon-md" /></span>
            {!collapsed && <span className="sidebar-engine-copy">
              <strong>Local Ollama Engine</strong>
              <span className="engine-model-status"><i className={`engine-status-light ${engineDot}`} />{engineDetail} · <code>{apiStatus?.ollama?.model || apiStatus?.ollama?.requested_model || activeModel}</code></span>
              <small>{readinessDetail} · no cloud APIs</small>
            </span>}
          </Link>
          {!collapsed && <button type="button" className="engine-toggle" onClick={toggleDemoState} aria-pressed={isDemoConnection && !connected} title={isDemoConnection ? "Return to live local Ollama status" : "Simulate Ollama offline for this browser session"}>
            {isDemoConnection ? "Use live status" : "Simulate offline"}
          </button>}
        </div>
        {!collapsed && <Link className={`rail-storage-link ${storageMetrics ? "is-ready" : "is-unverified"}`} to="/settings/general" onClick={onClose} aria-label={`SQLite ${storageMetrics ? "available" : "not verified"} · General and Storage`}>
          <Database className="icon-sm" strokeWidth={1.75} aria-hidden="true" />
          <span>SQLite · {storageMetrics?.database_name || "status unverified"}</span>
          <span className={`rail-storage-dot ${storageMetrics ? "is-ready" : "is-unverified"}`} />
        </Link>}
        {!collapsed && <div className="sidebar-footer"><span className="sidebar-footer-dot" />Local-first · draft-only workspace</div>}
      </div>
    </aside>
  );
}

function TopBar({ onOpenMobileNav, sidebarCollapsed, onToggleSidebar }) {
  const location = useLocation();
  const { connected, isDemoConnection, activeModel, activeTaskCount, storageMetrics, apiState, apiStatus } = useWorkspace();
  const pageName = location.pathname === "/"
    ? "Dashboard"
    : PAGE_CRUMBS.find(([path]) => location.pathname === path || (path === "/research" && location.pathname.startsWith("/research/")))?.[1] || "Workspace";
  const engineText = isDemoConnection
    ? connected ? "Demo connected" : "Disconnected"
    : apiState === "loading" ? "Checking"
      : apiStatus?.ollama?.state === "slow" ? "Responding slowly"
        : apiStatus?.ollama?.state === "error" ? "Model-tag error"
          : connected ? "Connected" : "Disconnected";
  const engineClass = isDemoConnection
    ? connected ? "connection-pill-demo" : "connection-pill-offline connection-pill-demo"
    : apiState === "loading" || apiStatus?.ollama?.state === "slow" ? "connection-pill-checking"
      : connected ? "connection-pill-online" : "connection-pill-offline";
  const databaseName = storageMetrics?.database_name || "not verified";
  const engineTitle = isDemoConnection
    ? "Demo override changes UI state only; no local model call is made."
    : apiState === "loading"
      ? "Checking the local Ollama endpoint. No cloud fallback is used."
      : apiStatus?.ollama?.state === "slow"
        ? apiStatus.ollama.message || "Local Ollama is responding slowly."
        : apiStatus?.ollama?.state === "error"
          ? apiStatus.ollama.message || "Local Ollama model tags could not be read."
          : connected
            ? "Local Ollama responds; the resolved installed model is shown in Local AI & Models."
            : "Local Ollama is disconnected. No cloud fallback is used.";

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button type="button" className="mobile-menu-trigger" onClick={onOpenMobileNav} aria-label="Open navigation"><Icon as={Menu} className="icon-md" /></button>
        <button type="button" className="topbar-sidebar-toggle" onClick={onToggleSidebar} aria-label={sidebarCollapsed ? "Expand navigation panel" : "Collapse navigation panel"} title={sidebarCollapsed ? "Expand navigation panel" : "Collapse navigation panel"}><Icon as={sidebarCollapsed ? PanelLeftOpen : PanelLeftClose} className="icon-sm" /></button>
        <nav className="breadcrumb-trail" aria-label="Breadcrumb">
          <Link to="/">Sellbird AI</Link><Icon as={ChevronRight} className="icon-xs breadcrumb-separator" />
          <Link to="/">Workspace</Link><Icon as={ChevronRight} className="icon-xs breadcrumb-separator" />
          <span className="breadcrumb-current" aria-current="page">{pageName}</span>
        </nav>
      </div>
      <div className="topbar-right">
        <SearchBox />
        <Link to="/settings/models" className={`connection-pill ${engineClass}`} title={engineTitle} aria-label={`Ollama ${engineText}, model preference ${activeModel}`}>
          <span className={`connection-dot ${isDemoConnection ? "is-demo" : ""}`} />
          <span>Model:</span><code>{apiStatus?.ollama?.model || apiStatus?.ollama?.requested_model || activeModel}</code><span className="connection-state-label">{engineText}</span>
          {isDemoConnection && <em>DEMO</em>}
        </Link>
        <Link className={`topbar-icon-button ${activeTaskCount ? "has-live-tasks" : ""}`} to="/activity" aria-label={`Activity queue, ${activeTaskCount} active tasks`} title="Activity queue">
          <Icon as={Activity} className="icon-md" />
          {activeTaskCount > 0 && <span className="topbar-notification-count">{activeTaskCount}</span>}
        </Link>
        <Link className={`sqlite-badge ${storageMetrics ? "sqlite-badge-ready" : "sqlite-badge-unverified"}`} to="/settings/general" title={`Local SQLite · ${databaseName} · General & Storage`} aria-label={`SQLite database ${databaseName}`}>
          <Icon as={Database} className="icon-sm" /><span>SQLite · {databaseName}</span>
        </Link>
      </div>
    </header>
  );
}

export function AppLayout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  return (
    <div className={`app-shell ${sidebarCollapsed ? "is-sidebar-collapsed" : ""}`}>
      <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={() => setSidebarCollapsed((current) => !current)} />
      <div className="app-main-column">
        <a href="#main-content" className="skip-link">Skip to page content</a>
        <TopBar sidebarCollapsed={sidebarCollapsed} onToggleSidebar={() => setSidebarCollapsed((current) => !current)} onOpenMobileNav={() => setMobileNavOpen(true)} />
        <main id="main-content" className="app-content"><Outlet /></main>
      </div>
      {mobileNavOpen && <div className="mobile-nav-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setMobileNavOpen(false)}><Sidebar mobile onClose={() => setMobileNavOpen(false)} /></div>}
    </div>
  );
}
