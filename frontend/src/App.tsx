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
  // Track whether first-run setup is done so /setup can redirect correctly.
  const [setupCompleted, setSetupCompleted] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSetupCompleted(s.setup_completed);
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
            setupCompleted ? (
              // Setup already done: redirect to settings (edit mode) instead of
              // showing the first-run wizard from the beginning.
              <Navigate to="/settings" replace />
            ) : (
              <div className="app-shell">
                <SetupWizard
                  onComplete={() => {
                    setSetupCompleted(true);
                    navigate("/");
                  }}
                />
              </div>
            )
          }
        />
        <Route
          path="/settings"
          element={
            <div className="app-shell">
              {/* Always use navigate("/") to avoid going back to /setup in history. */}
              <SetupWizard editMode onComplete={() => navigate("/")} />
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
