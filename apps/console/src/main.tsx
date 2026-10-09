import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { setApiUrl } from "./lib/api";
import { discoverApiUrl } from "./lib/apiUrl";
import { KeyGate } from "./layout/KeyGate";
import { ToastProvider } from "./components/Toast";
import { TourProvider } from "./tour/TourProvider";
import "./styles/app.css";

// Stale-while-revalidate everywhere; polling is opt-in per query and pauses while the tab is hidden.
const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 2000 } } });

const root = ReactDOM.createRoot(document.getElementById("root")!);
// The API's public URL changes whenever the laptop's quick tunnel restarts: look it up first (3 s at most).
discoverApiUrl().then((u) => { if (u) setApiUrl(u); }).finally(() => root.render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ToastProvider>
          <TourProvider>
            <KeyGate>
              <App />
            </KeyGate>
          </TourProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
));
