import { useMemo, useState } from "react";
import { Icon } from "./Icon";

interface DiffLine {
  kind: "add" | "del" | "ctx" | "hunk" | "meta";
  text: string;
  oldNo?: number;
  newNo?: number;
}
interface DiffFile {
  path: string;
  addition: number;
  deletion: number;
  lines: DiffLine[];
}

function parseDiff(raw: string): DiffFile[] {
  const files: DiffFile[] = [];
  let cur: DiffFile | null = null;
  let oldNo = 0;
  let newNo = 0;

  for (const line of raw.split("\n")) {
    if (line.startsWith("diff --git")) {
      cur = { path: "", addition: 0, deletion: 0, lines: [] };
      files.push(cur);
      const m = line.match(/ b\/(.+)$/);
      if (m) cur.path = m[1];
      continue;
    }
    if (!cur) continue;
    if (line.startsWith("--- ") || line.startsWith("+++ ") || line.startsWith("index ") || line.startsWith("new file") || line.startsWith("deleted file") || line.startsWith("similarity ") || line.startsWith("rename ")) {
      if (line.startsWith("+++ ") && cur.path === "") cur.path = line.slice(6);
      cur.lines.push({ kind: "meta", text: line });
      continue;
    }
    if (line.startsWith("@@")) {
      const m = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (m) {
        oldNo = parseInt(m[1], 10);
        newNo = parseInt(m[2], 10);
      }
      cur.lines.push({ kind: "hunk", text: line });
      continue;
    }
    if (line.startsWith("+")) {
      cur.addition++;
      cur.lines.push({ kind: "add", text: line.slice(1), newNo: newNo++ });
    } else if (line.startsWith("-")) {
      cur.deletion++;
      cur.lines.push({ kind: "del", text: line.slice(1), oldNo: oldNo++ });
    } else {
      cur.lines.push({ kind: "ctx", text: line.slice(1), oldNo: oldNo++, newNo: newNo++ });
    }
  }
  return files.filter((f) => f.path);
}

export function DiffView({ raw }: { raw: string }) {
  const files = useMemo(() => parseDiff(raw), [raw]);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  if (files.length === 0) {
    return <div className="card--pad muted">No textual diff.</div>;
  }

  return (
    <div className="diff">
      {files.map((f) => {
        const isCollapsed = collapsed[f.path];
        return (
          <div key={f.path} className="diff__file">
            <button
              className="diff__file-head"
              onClick={() => setCollapsed((c) => ({ ...c, [f.path]: !c[f.path] }))}
            >
              <Icon name={isCollapsed ? "chevronRight" : "chevronDown"} size={13} />
              <span className="mono truncate">{f.path}</span>
              <span className="spacer" />
              <span className="plus mono">+{f.addition}</span>
              <span className="minus mono">−{f.deletion}</span>
            </button>
            {!isCollapsed && (
              <div className="diff__body">
                {f.lines
                  .filter((l) => l.kind !== "meta")
                  .map((l, i) => (
                    <div key={i} className={`diff__line diff__line--${l.kind}`}>
                      <span className="diff__gutter">{l.oldNo ?? ""}</span>
                      <span className="diff__gutter">{l.newNo ?? ""}</span>
                      <span className="diff__mark">
                        {l.kind === "add" ? "+" : l.kind === "del" ? "−" : l.kind === "hunk" ? "" : " "}
                      </span>
                      <span className="diff__text">{l.text || " "}</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
