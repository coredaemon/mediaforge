import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { getSettings } from "./api";
import { SetupWizard } from "./components/SetupWizard";
import { Layout } from "./components/Layout";
import { SessionDetailPage } from "./pages/SessionDetailPage";
import { SessionsPage } from "./pages/SessionsPage";
import { StatusPage } from "./pages/StatusPage";

function AppContent() {
  const navigate = useNavigate();
  const [state, setState] = useState<"loading" | "ready">("loading");

  useEffect(() => {
    getSettings()
      .then((s) => {
        if (!s.setup_completed) {
          navigate("/setup", { replace: true });
        }
        setState("ready");
      })
      .catch(() => setState("ready"));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state === "loading") {
    return (
      <div className="app-shell">
        <p>Загрузка...</p>
      </div>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<SessionsPage />} />
        <Route path="/sessions/:sessionId" element={<SessionDetailPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route
          path="/setup"
          element={
            <div className="app-shell">
              <SetupWizard onComplete={() => navigate("/")} />
            </div>
          }
        />
        <Route
          path="/settings"
          element={
            <div className="app-shell">
              <SetupWizard editMode onComplete={() => navigate(-1)} />
            </div>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
