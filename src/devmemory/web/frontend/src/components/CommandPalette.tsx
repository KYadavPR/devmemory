import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useFeatures, useVersions } from "@/api/client";
import { Icon, type IconName } from "./Icon";
import { StatusBadge } from "./primitives";
import { featureName, vlabel } from "@/lib/format";

interface Item {
  id: string;
  title: string;
  hint?: string;
  icon: IconName;
  badge?: React.ReactNode;
  run: () => void;
  group: "Go to" | "Versions" | "Features" | "Actions";
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const { data: versions = [] } = useVersions(500, { enabled: open });
  const { data: features = [] } = useFeatures({ enabled: open });

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const go = (path: string) => {
    navigate(path);
    onClose();
  };

  const items = useMemo<Item[]>(() => {
    const nav: Item[] = [
      { id: "n-overview", title: "Overview", icon: "overview", group: "Go to", run: () => go("/") },
      { id: "n-timeline", title: "Timeline", icon: "timeline", group: "Go to", run: () => go("/timeline") },
      { id: "n-features", title: "Features", icon: "features", group: "Go to", run: () => go("/features") },
      { id: "n-intel", title: "Intelligence", icon: "intelligence", group: "Go to", run: () => go("/intelligence") },
      { id: "n-safe", title: "Safe to change?", icon: "shield", group: "Go to", run: () => go("/safe-to-change") },
      { id: "n-memory", title: "Memory", icon: "memory", group: "Go to", run: () => go("/memory") },
      { id: "n-compare", title: "Compare", icon: "compare", group: "Go to", run: () => go("/compare") },
    ];
    const vs: Item[] = versions
      .slice()
      .reverse()
      .map((v) => ({
        id: `v-${v.version_id}`,
        title: `${vlabel(v.version_id)} — ${v.intent ?? "no intent"}`,
        hint: [v.feature, v.agent].filter(Boolean).join(" · "),
        icon: "commit",
        badge: <StatusBadge status={v.status} />,
        group: "Versions",
        run: () => go(`/version/${v.version_id}`),
      }));
    const fs: Item[] = features.map((f) => ({
      id: `f-${f.feature_id}`,
      title: f.name,
      hint: `${f.version_count} version${f.version_count === 1 ? "" : "s"}`,
      icon: "features",
      badge: <StatusBadge status={f.status} />,
      group: "Features",
      run: () => go(`/feature/${encodeURIComponent(featureName(f.feature_id))}`),
    }));
    return [...nav, ...vs, ...fs];
  }, [versions, features]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    const base = term
      ? items.filter((i) => (i.title + " " + (i.hint ?? "")).toLowerCase().includes(term))
      : items;
    if (term) {
      base.push({
        id: "act-search",
        title: `Search all records for “${q.trim()}”`,
        icon: "search",
        group: "Actions",
        run: () => go(`/search/${encodeURIComponent(q.trim())}`),
      });
    }
    return base;
  }, [items, q]);

  useEffect(() => setActive(0), [q]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const grouped: [string, Item[]][] = [];
  for (const it of filtered) {
    const last = grouped[grouped.length - 1];
    if (last && last[0] === it.group) last[1].push(it);
    else grouped.push([it.group, [it]]);
  }
  let idx = -1;

  return (
    <div className="palette-overlay" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="palette__input">
          <Icon name="search" size={17} />
          <input
            ref={inputRef}
            className="palette__field"
            placeholder="Jump to a version, feature, page — or search everything"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, filtered.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                filtered[active]?.run();
              } else if (e.key === "Escape") {
                onClose();
              }
            }}
          />
          <kbd>esc</kbd>
        </div>

        <div className="palette__list" ref={listRef}>
          {filtered.length === 0 && <div className="palette__empty">No matches</div>}
          {grouped.map(([group, groupItems]) => (
            <div key={group}>
              <div className="palette__group">{group}</div>
              {groupItems.map((it) => {
                idx++;
                const i = idx;
                return (
                  <button
                    key={it.id}
                    data-idx={i}
                    className={`palette__item${i === active ? " palette__item--active" : ""}`}
                    onMouseMove={() => setActive(i)}
                    onClick={it.run}
                  >
                    <Icon name={it.icon} size={15} />
                    <span className="palette__title truncate">{it.title}</span>
                    {it.hint && <span className="palette__hint truncate">{it.hint}</span>}
                    {it.badge}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
