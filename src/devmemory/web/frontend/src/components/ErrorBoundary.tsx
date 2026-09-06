import { Component, type ReactNode } from "react";
import { EmptyState } from "./primitives";

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <EmptyState icon="alert" title="This view hit an error" sub={this.state.error.message}>
          <button className="btn" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </EmptyState>
      );
    }
    return this.props.children;
  }
}
