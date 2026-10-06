import { Route, Routes, useSearchParams } from "react-router-dom";
import { Header } from "./layout/Header";
import { LeftRail } from "./layout/LeftRail";
import { StreamRail } from "./layout/StreamRail";

function ConsoleMain() {
  const [params] = useSearchParams();
  const campaign = params.get("campaign");
  const domain = params.get("domain");
  if (!campaign && !domain) {
    return (
      <div className="p-8 max-w-[640px]">
        <p className="panel-title">Pick a campaign or a candidate</p>
        <p className="secondary mt-2">
          Campaigns are groups of confirmed domains on shared infrastructure; open one to plan takedowns. Candidates are
          name matches from the certificate stream — not yet verified, and never treated as accusations.
        </p>
      </div>
    );
  }
  return <div className="p-6 secondary">Loading…</div>;
}

export default function App() {
  return (
    <div className="shell">
      <Header />
      <LeftRail />
      <main>
        <Routes>
          <Route path="/" element={<ConsoleMain />} />
        </Routes>
      </main>
      <StreamRail />
    </div>
  );
}
