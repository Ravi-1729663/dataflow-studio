import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

const NAV_ITEMS = [
  { to: "/datasources", label: "Data Sources" },
  { to: "/pipelines", label: "Pipelines" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/lineage", label: "Lineage" },
  { to: "/scorecards", label: "Scorecards" },
];

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-brand">DataFlow Studio</div>
        <nav className="app-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="app-header-right">
          <WorkspaceSwitcher />
          <span className="app-user">
            {user?.username} <span className="app-role">{user?.role}</span>
          </span>
          <button type="button" className="ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
