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
        <div style={{ padding: 40, textAlign: "center" }}>
          <h1 style={{ marginBottom: 8 }}>出错了</h1>
          <p style={{ color: "#666", marginBottom: 16 }}>
            {this.state.error?.message ?? "应用发生未知错误"}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "8px 24px",
              cursor: "pointer",
              borderRadius: 6,
              border: "1px solid #ccc",
              background: "#f5f5f5",
            }}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
