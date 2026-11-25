import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { Activity, CheckCircle2, Compass, Home, ShieldCheck } from "lucide-react";
import { AppLayout } from "./layout.jsx";
import { WorkspaceProvider, useWorkspace } from "./WorkspaceContext.jsx";
import { Icon, PageHeader } from "./ui.jsx";
import ActivityPage from "./pages/ActivityPage.jsx";
import CampaignsPage from "./pages/CampaignsPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import GeneralSettingsPage from "./pages/GeneralSettingsPage.jsx";
import ModelsSettingsPage from "./pages/ModelsSettingsPage.jsx";
import ProductsPage from "./pages/ProductsPage.jsx";
import ProspectsPage from "./pages/ProspectsPage.jsx";
import RepliesPage from "./pages/RepliesPage.jsx";
import ResearchPage from "./pages/ResearchPage.jsx";

function ToastViewport() {
  const { toast } = useWorkspace();
  if (!toast) return null;
  return <div className="toast-message" role="status" aria-live="polite"><Icon as={CheckCircle2} className="icon-sm" />{toast}</div>;
}

function NotFoundPage() {
  return <section className="not-found-page"><span className="not-found-mark"><Icon as={Compass} className="icon-lg" /></span><PageHeader eyebrow="LOCAL WORKSPACE" title="That page is not here" subtitle="The route may have changed. Your local workspace data is untouched." primaryAction={<Link className="btn btn-dark" to="/"><Icon as={Home} className="icon-sm" />Back to dashboard</Link>} secondaryAction={<Link className="btn btn-secondary" to="/activity"><Icon as={Activity} className="icon-sm" />Open Activity Queue</Link>} /><p><Icon as={ShieldCheck} className="icon-xs" />Sellbird remains local-first · email drafts are never sent.</p></section>;
}

function WorkspaceRoutes() {
  return <>
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="prospects" element={<ProspectsPage />} />
        <Route path="prospects/import" element={<Navigate to="/prospects?import=true" replace />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="research/:prospectId" element={<ResearchPage />} />
        <Route path="campaigns" element={<CampaignsPage />} />
        <Route path="replies" element={<RepliesPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="settings/models" element={<ModelsSettingsPage />} />
        <Route path="settings/general" element={<GeneralSettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
    <ToastViewport />
  </>;
}

export default function App() {
  return <WorkspaceProvider><BrowserRouter><WorkspaceRoutes /></BrowserRouter></WorkspaceProvider>;
}
