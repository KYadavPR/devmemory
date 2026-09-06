import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTasks, useProject, createTask } from "@/api/client";
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

      <Card title="New task" pad>
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
