import { useNavigate } from "react-router-dom";
import { EmptyState } from "@/components/primitives";

export function NotFound() {
  const navigate = useNavigate();
  return (
    <EmptyState icon="search" title="Nothing here" sub="That route doesn't exist.">
      <button className="btn btn--primary" onClick={() => navigate("/")}>
        Back to overview
      </button>
    </EmptyState>
  );
}
