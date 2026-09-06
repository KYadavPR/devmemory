import { Link } from "react-router-dom";
import type { PreviousAttempt } from "@/api/types";
import { StatusBadge } from "./primitives";
import { Icon } from "./Icon";
import { vlabel } from "@/lib/format";

export function AttemptCard({ a }: { a: PreviousAttempt }) {
  return (
    <div className={`attempt${a.is_adverse ? " attempt--adverse" : ""}`}>
      <div className="row row--wrap" style={{ gap: 8, marginBottom: 6 }}>
        <Link className="link" to={`/version/${a.version_id}`} style={{ fontWeight: 640 }}>
          {vlabel(a.version_id)}
        </Link>
        <StatusBadge status={a.status} />
        {a.feature && <span className="pill">{a.feature}</span>}
        <span className="spacer" />
        <span className="muted text-xs">{a.matched_on.join(" · ")}</span>
      </div>
      <div className="text-sm">{a.intent || a.change_summary}</div>
      <div className="secondary text-sm" style={{ marginTop: 4 }}>
        result: {a.result}
      </div>
      {a.recommendation && (
        <div className="attempt__rec">
          <Icon name="arrowRight" size={13} /> {a.recommendation}
        </div>
      )}
    </div>
  );
}
