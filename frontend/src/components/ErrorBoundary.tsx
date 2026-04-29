import { Component, type ReactNode, type ErrorInfo } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h1>出错了</h1>
          <p>
            {this.state.error?.message ?? "应用发生未知错误"}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="clay-btn clay-btn--outline"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
