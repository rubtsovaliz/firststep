import { useState } from "react";
import { Dashboard } from "./pages/Dashboard";
import { History } from "./pages/History";

type AppPage = "dashboard" | "history";

export default function App() {
  const [page, setPage] = useState<AppPage>("dashboard");

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar__brand">Polymarket WeatherBot</div>
        <nav className="app-sidebar__nav">
          <button
            type="button"
            className={`app-sidebar__link${page === "dashboard" ? " app-sidebar__link--active" : ""}`}
            onClick={() => setPage("dashboard")}
          >
            Dashboard
          </button>
          <button
            type="button"
            className={`app-sidebar__link${page === "history" ? " app-sidebar__link--active" : ""}`}
            onClick={() => setPage("history")}
          >
            History
          </button>
        </nav>
      </aside>
      <main className="app-main">
        {page === "dashboard" ? <Dashboard /> : <History />}
      </main>
    </div>
  );
}
