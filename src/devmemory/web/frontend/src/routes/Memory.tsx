import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAttempts } from "@/api/client";
import { Async } from "@/components/Async";
import { PageHead, EmptyState } from "@/components/primitives";
import { AttemptCard } from "@/components/AttemptCard";
import { Icon } from "@/components/Icon";
import { useDebounced } from "@/lib/useDebounced";

export function Memory() {
  const { q: urlQ } = useParams<{ q: string }>();
  const navigate = useNavigate();
  const [q, setQ] = useState(urlQ ? decodeURIComponent(urlQ) : "");
  const debounced = useDebounced(q, 250);

  useEffect(() => {
    setQ(urlQ ? decodeURIComponent(urlQ) : "");
  }, [urlQ]);

  useEffect(() => {
    const path = debounced.trim() ? `/memory/${encodeURIComponent(debounced.trim())}` : "/memory";
    navigate(path, { replace: true });
  }, [debounced, navigate]);

  const query = useAttempts(debounced.trim());

  return (
    <>
      <PageHead
        title="Development memory"
        subtitle="Approaches that failed or regressed — so the next change (or agent) doesn't repeat them."
      />

      <div className="input-icon" style={{ marginBottom: 16 }}>
        <Icon name="search" size={15} />
        <input
          className="input"
          placeholder="Scope by intent — what are you about to try?"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
      </div>

      <Async
        query={query}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState
            icon="memory"
            title="No relevant previous attempts"
            sub="Nothing to avoid — yet."
          />
        }
      >
        {(attempts) => (
          <div className="stack" style={{ gap: 12 }}>
            {attempts.map((a) => (
              <AttemptCard key={a.version_id} a={a} />
            ))}
          </div>
        )}
      </Async>
    </>
  );
}
