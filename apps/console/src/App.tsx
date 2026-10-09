import { Route, Routes } from "react-router-dom";
import { Header } from "./layout/Header";
import { LeftRail } from "./layout/LeftRail";
import { ArchitecturePage } from "./views/Architecture";
import { LiveQueuePage } from "./views/LiveQueue";
import { CampaignsPage } from "./views/Campaigns";
import { CampaignDetailPage } from "./views/CampaignView";
import { EvidenceIndexPage, EvidencePage } from "./views/EvidenceViewer";
import { EmailAnalyzerPage } from "./views/EmailAnalyzer";
import { LedgerPage } from "./views/Ledger";
import { MetricsPage } from "./views/Metrics";
import { HealthPage } from "./views/Health";
import { OpsLogPage } from "./views/OpsLog";
import { TechnicalPage } from "./views/Technical";
import { TourOverlay } from "./tour/TourOverlay";
import { TourStartPage } from "./tour/TourStart";
import { DomainDrawer } from "./views/DomainDetail";
import { PageHeader } from "./components/Page";
import { Link } from "react-router-dom";

function NotFound() {
  return (
    <div>
      <PageHeader title="Page not found" />
      <p className="prose ink-2">This address does not match a console page. <Link className="link" to="/">Go to the architecture overview</Link>.</p>
    </div>
  );
}

export default function App() {
  return (
    <>
      <LeftRail />
      <Header />
      <main className="main">
        <div className="content">
          <Routes>
            <Route path="/" element={<ArchitecturePage />} />
            <Route path="/technical" element={<TechnicalPage />} />
            <Route path="/tour" element={<TourStartPage />} />
            <Route path="/queue" element={<LiveQueuePage />} />
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/campaigns/:id" element={<CampaignDetailPage />} />
            <Route path="/evidence" element={<EvidenceIndexPage />} />
            <Route path="/evidence/:id" element={<EvidencePage />} />
            <Route path="/email" element={<EmailAnalyzerPage />} />
            <Route path="/ledger" element={<LedgerPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/ops" element={<OpsLogPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </main>
      <DomainDrawer />
      <TourOverlay />
    </>
  );
}
