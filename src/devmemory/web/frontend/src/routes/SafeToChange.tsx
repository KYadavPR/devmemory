import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { checkChange, useAnalytics } from "@/api/client";
import { Card, PageHead, Badge, EmptyState } from "@/components/primitives";
import { AttemptCard } from "@/components/AttemptCard";
import { Icon } from "@/components/Icon";
import { verdictTone } from "@/lib/status";
import type { ChangeGuidance } from "@/api/types";

export function SafeToChange() {
  const analytics = useAnalytics();
  const [files, setFiles] = useState("");
  const [intent, setIntent] = useState("");

  const mutation = useMutation<ChangeGuidance, Error, void>({
    mutationFn: () =>
      checkChange(
        files
          .split(/[\n,]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        intent,
      ),
  });

  const churn = analytics.data?.file_churn ?? [];

  return (
    <>
      <PageHead
        title="Safe to change?"
        subtitle="A pre-flight risk read for the change you're about to make — the same check the MCP server gives an AI agent."
      />

      <div className="grid grid--2" style={{ alignItems: "start" }}>
        <Card title="What are you about to touch?" pad>
          <label className="field-label">Files</label>
          <textarea
            className="input"
            rows={4}
            placeholder={"pricing/core.py\nsrc/auth/tokens.py"}
            value={files}
            onChange={(e) => setFiles(e.target.value)}
            style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", resize: "vertical" }}
          />
          {churn.length > 0 && (
            <div className="row row--wrap" style={{ gap: 6, marginTop: 8 }}>
              <span className="muted text-xs">frequently changed:</span>
              {churn.slice(0, 6).map((c) => (
                <button
                  key={c.path}
                  className="pill"
                  onClick={() =>
                    setFiles((f) => (f.split(/[\n,]+/).map((s) => s.trim()).includes(c.path) ? f : (f ? f + "\n" : "") + c.path))
                  }
                >
                  {c.path}
                  {c.adverse_changes > 0 && <span className="minus"> ⚠{c.adverse_changes}</span>}
                </button>
              ))}
            </div>
          )}

          <label className="field-label" style={{ marginTop: 14 }}>
            Intent
          </label>
          <input
            className="input"
            placeholder="e.g. change the discount tier logic"
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
          />

          <button
            className="btn btn--primary"
            style={{ marginTop: 14, width: "100%" }}
            disabled={!files.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? <span className="spinner" /> : <Icon name="shield" size={15} />}
            Check
          </button>
        </Card>

        <div>
          {mutation.isIdle && (
            <EmptyState
              icon="shield"
              title="No check run yet"
              sub="Add the files you're about to edit and describe the change."
            />
          )}
          {mutation.isError && (
            <EmptyState icon="alert" title="Check failed" sub={mutation.error.message} />
          )}
          {mutation.data && <Guidance g={mutation.data} />}
        </div>
      </div>
    </>
  );
}

function Guidance({ g }: { g: ChangeGuidance }) {
  const tone = verdictTone(g.verdict);
  return (
    <div className="stack">
      <Card className={`callout callout--${tone === "ok" ? "ok" : tone === "bad" ? "bad" : "warn"}`} pad>
        <div className="row" style={{ gap: 10, alignItems: "flex-start" }}>
          <Icon name={tone === "ok" ? "check" : "alert"} size={20} />
          <div>
            <div className="row" style={{ gap: 8, marginBottom: 4 }}>
              <Badge tone={tone}>{g.verdict}</Badge>
            </div>
            <div style={{ fontSize: "0.9375rem", fontWeight: 550 }}>{g.headline}</div>
          </div>
        </div>
      </Card>

      {g.warnings.length > 0 && (
        <Card title="Warnings" pad>
          <ul className="warn-list">
            {g.warnings.map((w, i) => (
              <li key={i}>
                <Icon name="alert" size={13} /> {w}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {g.recommendations.length > 0 && (
        <Card title="Recommendations" pad>
          <ul className="rec-list">
            {g.recommendations.map((r, i) => (
              <li key={i}>
                <Icon name="arrowRight" size={13} /> {r}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {g.related_attempts.length > 0 && (
        <Card title={`Related previous attempts · ${g.related_attempts.length}`} pad>
          <div className="stack" style={{ gap: 10 }}>
            {g.related_attempts.map((a) => (
              <AttemptCard key={a.version_id} a={a} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
