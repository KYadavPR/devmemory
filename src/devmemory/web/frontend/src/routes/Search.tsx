import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSearch } from "@/api/client";
import { Async } from "@/components/Async";
import { PageHead, EmptyState, StatusBadge } from "@/components/primitives";
import { Icon } from "@/components/Icon";
import { Link } from "react-router-dom";
import { shortSha, vlabel } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

export function Search() {
  const { q: urlQ } = useParams<{ q: string }>();
  const navigate = useNavigate();
  const [q, setQ] = useState(urlQ ? decodeURIComponent(urlQ) : "");
  const debounced = useDebounced(q, 250);

  useEffect(() => setQ(urlQ ? decodeURIComponent(urlQ) : ""), [urlQ]);
  useEffect(() => {
    navigate(debounced.trim() ? `/search/${encodeURIComponent(debounced.trim())}` : "/search", {
      replace: true,
    });
  }, [debounced, navigate]);

  const query = useSearch(debounced.trim());

  return (
    <>
      <PageHead
        title="Search"
        subtitle="Across intent, agent, feature, files, commits, checkpoints, and analysis."
      />
      <div className="input-icon" style={{ marginBottom: 16 }}>
        <Icon name="search" size={15} />
        <input
          className="input"
          placeholder="authentication · learning rate · core.py · Codex …"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
      </div>

      {!debounced.trim() ? (
        <EmptyState icon="search" title="Type to search" />
      ) : (
        <Async
          query={query}
          isEmpty={(d) => d.count === 0}
          empty={<EmptyState icon="search" title={`No matches for “${debounced.trim()}”`} />}
        >
          {(res) => (
            <section className="card card--flush">
              {res.results.map((h) => (
                <Link key={h.version_id} className="vrow" to={`/version/${h.version_id}`}>
                  <span className="vrow__id">{vlabel(h.version_id)}</span>
                  <StatusBadge status={h.status} />
                  <span className="vrow__main">
                    <span className="vrow__intent truncate">
                      {h.snippet || h.intent || "—"}
                    </span>
                    <span className="vrow__meta">
                      {h.agent && <span>{h.agent}</span>}
                      {h.feature && <span>{h.feature}</span>}
                    </span>
                  </span>
                  <span className="pill vrow__sha">{shortSha(h.git_commit)}</span>
                </Link>
              ))}
            </section>
          )}
        </Async>
      )}
    </>
  );
}
