import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "./Icon";
import { useProject } from "@/api/client";
import { Logo } from "./Logo";

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: "/", label: "Overview", icon: "overview" },
  { to: "/timeline", label: "Timeline", icon: "timeline" },
  { to: "/features", label: "Features", icon: "features" },
  { to: "/intelligence", label: "Intelligence", icon: "intelligence" },
  { to: "/safe-to-change", label: "Safe to change?", icon: "shield" },
  { to: "/memory", label: "Memory", icon: "memory" },
  { to: "/compare", label: "Compare", icon: "compare" },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { data: project } = useProject();

  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="sidebar__brand">
        <Logo size={28} />
        <div style={{ minWidth: 0 }}>
          <div className="sidebar__name">DevMemory</div>
          <div className="sidebar__repo truncate">{project?.name ?? "…"}</div>
        </div>
      </div>

      <div className="sidebar__nav">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) => `nav-link${isActive ? " nav-link--active" : ""}`}
            onClick={onNavigate}
          >
            <Icon name={item.icon} size={16} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>

      <div className="spacer" />

      {project && (
        <div className="sidebar__foot">
          {project.branch && (
            <div className="row" style={{ gap: 6 }}>
              <Icon name="commit" size={12} />
              <span className="truncate">{project.branch}</span>
            </div>
          )}
          <div className="truncate" title={project.repo_path}>
            {project.repo_path}
          </div>
          <div className="row" style={{ gap: 6 }}>
            <span
              className="badge__dot"
              style={{ background: project.entire_enabled ? "var(--ok)" : "var(--text-muted)" }}
            />
            <span>
              Entire {project.entire_enabled ? "on" : project.entire_installed ? "off" : "absent"}
              {project.entire_version ? ` · ${project.entire_version}` : ""}
            </span>
          </div>
        </div>
      )}
    </nav>
  );
}
