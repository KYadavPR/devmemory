import { useProject } from "@/api/client";
import { useTheme } from "@/theme/ThemeProvider";
import { Icon } from "./Icon";
import { shortSha } from "@/lib/format";

export function TopBar({
  onOpenPalette,
  onOpenNav,
}: {
  onOpenPalette: () => void;
  onOpenNav: () => void;
}) {
  const { data: project } = useProject();
  const { pref, cycle } = useTheme();

  const themeIcon = pref === "dark" ? "moon" : pref === "light" ? "sun" : "monitor";
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

  return (
    <header className="topbar">
      <button className="topbar__menu btn btn--ghost btn--sm" onClick={onOpenNav} aria-label="Open navigation">
        <Icon name="layers" size={16} />
      </button>

      <div className="topbar__context truncate">
        {project?.head_subject ? (
          <>
            <span className="pill">{shortSha(project.head_sha)}</span>
            <span className="truncate secondary">{project.head_subject}</span>
            {!project.head_has_version && (
              <span className="badge badge--warn">
                <span className="badge__dot" />
                uncheckpointed
              </span>
            )}
          </>
        ) : (
          <span className="muted">DevMemory</span>
        )}
      </div>

      <div className="spacer" />

      <button className="topbar__search" onClick={onOpenPalette} aria-label="Search and commands">
        <Icon name="search" size={15} />
        <span>Search…</span>
        <kbd>{isMac ? "⌘" : "Ctrl"} K</kbd>
      </button>

      <button
        className="btn btn--ghost btn--sm"
        onClick={cycle}
        aria-label={`Theme: ${pref}. Click to change.`}
        title={`Theme: ${pref}`}
      >
        <Icon name={themeIcon} size={16} />
      </button>
    </header>
  );
}
