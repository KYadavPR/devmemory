import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useTasks,
  useProject,
  useProjectBrief,
  createTask,
  saveProjectBrief,
} from "@/api/client";
import { Async } from "@/components/Async";
import { Badge, Card, PageHead, EmptyState } from "@/components/primitives";
import { Icon } from "@/components/Icon";
import { statusTone, statusLabel } from "@/lib/status";
import { relativeTime } from "@/lib/format";
import type { NormalizedState } from "@/api/types";

export function Tasks() {
  const tasks = useTasks();
  const project = useProject();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [goal, setGoal] = useState("");
  const [testCmd, setTestCmd] = useState("");

  const create = useMutation<NormalizedState, Error, void>({
    mutationFn: () => createTask(goal.trim(), testCmd.trim() || undefined),
    onSuccess: (state) => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.setQueryData(["task-state", state.task.id], state);
      navigate(`/task/${state.task.id}`);
    },
  });

  return (
    <>
      <PageHead
        title="Tasks"
        subtitle="The state-aware coding loop — one normalized state per task, refreshed from Git, Entire, tests, and change-impact."
      />

      <ProjectBriefCard />

      <Card title="New task" pad style={{ marginTop: 16 }}>
        <label className="field-label">Goal</label>
        <input
          className="input"
          placeholder="e.g. Add password reset with email verification and tests"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && goal.trim() && create.mutate()}
        />
        <label className="field-label" style={{ marginTop: 12 }}>
          Test command <span className="muted">(optional — defaults to the project's)</span>
        </label>
        <input
          className="input"
          placeholder={project.data ? "pytest -q" : ""}
          value={testCmd}
          onChange={(e) => setTestCmd(e.target.value)}
          style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem" }}
        />
        <button
          className="btn btn--primary"
          style={{ marginTop: 14 }}
          disabled={!goal.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? <span className="spinner" /> : <Icon name="plus" size={15} />}
          Create task
        </button>
        {create.isError && (
          <p className="text-xs" style={{ color: "var(--bad)", marginTop: 8 }}>
            {create.error.message}
          </p>
        )}
      </Card>

      <div style={{ marginTop: 16 }}>
        <Async
          query={tasks}
          isEmpty={(t) => t.length === 0}
          empty={
            <EmptyState
              icon="target"
              title="No tasks yet"
              sub="Create one above, or run `devmemory task new` in the repo."
            />
          }
        >
          {(rows) => (
            <Card flush>
              {rows.map((t) => (
                <Link key={t.id} to={`/task/${t.id}`} className="task-row">
                  <span className="mono task-row__id">{t.id}</span>
                  <div className="task-row__main">
                    <div className="task-row__goal">{t.goal}</div>
                    <div className="task-row__meta">
                      <span className="mono">{t.branch}</span>
                      <span>
                        {t.requirements_complete}/{t.requirements_total} requirements
                      </span>
                      {t.test_command && <span className="mono">{t.test_command}</span>}
                      {t.updated_at && <span>{relativeTime(t.updated_at)}</span>}
                    </div>
                  </div>
                  <Badge tone={statusTone(t.status)}>{statusLabel(t.status)}</Badge>
                </Link>
              ))}
            </Card>
          )}
        </Async>
      </div>
    </>
  );
}

function ProjectBriefCard() {
  const brief = useProjectBrief();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (brief.data && !dirty) setText(brief.data.content);
  }, [brief.data, dirty]);

  const save = useMutation({
    mutationFn: () => saveProjectBrief(text),
    onSuccess: (doc) => {
      qc.setQueryData(["project-brief"], doc);
      setDirty(false);
    },
  });

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    const content = await file.text();
    setText((prev) => (prev.trim() ? `${prev.trim()}\n\n${content}` : content));
    setDirty(true);
  };

  return (
    <Card
      title="Project context"
      action={
        <span className="muted text-xs">
          single source of truth ·{" "}
          {brief.data?.updated_at ? `saved ${relativeTime(brief.data.updated_at)}` : "not set"}
        </span>
      }
      pad
    >
      <p className="muted text-sm" style={{ marginTop: 0 }}>
        Specs, constraints, decisions, conventions — anything the loop should treat as ground
        truth. Fed into requirement normalization and the prompts suggested back to your IDE.
      </p>
      <textarea
        className="input"
        rows={6}
        placeholder="# What this project is&#10;- …&#10;## Constraints&#10;- …&#10;## Conventions&#10;- …"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setDirty(true);
        }}
        style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", resize: "vertical" }}
      />
      <div className="row" style={{ gap: 8, marginTop: 12 }}>
        <button
          className="btn btn--primary"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? <span className="spinner" /> : <Icon name="check" size={14} />}
          Save
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".md,.txt,.markdown,text/plain,text/markdown"
          hidden
          onChange={(e) => {
            void onFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <button className="btn" onClick={() => fileRef.current?.click()}>
          <Icon name="plus" size={14} /> Append file
        </button>
        {dirty && <span className="text-xs muted">unsaved changes</span>}
        {save.isError && (
          <span className="text-xs" style={{ color: "var(--bad)" }}>
            {(save.error as Error).message}
          </span>
        )}
      </div>
    </Card>
  );
}
