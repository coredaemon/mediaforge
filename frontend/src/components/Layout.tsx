import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { ApiError, getHealth } from "../api";
import { t } from "../i18n";

type HealthState = "loading" | "ok" | "error";

export function Layout() {
  const [healthState, setHealthState] = useState<HealthState>("loading");
  const [healthMessage, setHealthMessage] = useState<string>(t.health.checking);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "light");

  useEffect(() => {
    let active = true;

    async function loadHealth() {
      try {
        await getHealth();
        if (!active) return;
        setHealthState("ok");
        setHealthMessage(t.health.online);
      } catch (error) {
        if (!active) return;
        setHealthState("error");
        const msg = error instanceof ApiError ? error.message : t.health.offline;
        setHealthMessage(msg);
      }
    }

    void loadHealth();
    const id = window.setInterval(() => void loadHealth(), 15000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("mediaforge-theme", next);
    setTheme(next);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1 className="app-title">{t.appName}</h1>
          <nav className="app-nav">
            <Link to="/">{t.nav.sessions}</Link>
            <Link to="/status">{t.nav.about}</Link>
          </nav>
        </div>
        <div className="header-right">
          <div className="health-badge" title={healthMessage}>
            <span className={`health-dot ${healthState}`} />
            <span>{healthState === "ok" ? t.health.online : healthMessage}</span>
          </div>
          <button type="button" className="theme-toggle" title="Переключить тему" onClick={toggleTheme}>
            {theme === "dark" ? "☀" : "☾"}
          </button>
          <Link to="/settings">
            <button type="button">⚙ {t.nav.settings}</button>
          </Link>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
