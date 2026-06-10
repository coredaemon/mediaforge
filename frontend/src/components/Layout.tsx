import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { ApiError, getHealth } from "../api";

type HealthState = "loading" | "ok" | "error";

export function Layout() {
  const [healthState, setHealthState] = useState<HealthState>("loading");
  const [healthMessage, setHealthMessage] = useState("Checking backend...");

  useEffect(() => {
    let active = true;

    async function loadHealth() {
      try {
        const health = await getHealth();
        if (!active) {
          return;
        }
        setHealthState("ok");
        setHealthMessage(`${health.app} ${health.status}`);
      } catch (error) {
        if (!active) {
          return;
        }
        setHealthState("error");
        const message = error instanceof ApiError ? error.message : "Backend unavailable";
        setHealthMessage(message);
      }
    }

    void loadHealth();
    const intervalId = window.setInterval(() => {
      void loadHealth();
    }, 15000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1 className="app-title">MediaForge</h1>
          <nav className="app-nav">
            <Link to="/">Sessions</Link>
            <Link to="/status">About / Status</Link>
          </nav>
        </div>
        <div className="health-badge" title={healthMessage}>
          <span className={`health-dot ${healthState}`} />
          <span>{healthState === "ok" ? "Backend online" : healthMessage}</span>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
