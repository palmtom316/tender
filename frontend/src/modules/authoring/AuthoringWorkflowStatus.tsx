import { authoringSteps, type AuthoringWorkflowStatusInput } from "./authoringWorkflow";

interface Props {
  status?: AuthoringWorkflowStatusInput;
  activeTab: string;
  onNavigate?: (tab: string) => void;
}

const stateLabel = {
  done: "完成",
  active: "当前",
  blocked: "阻断",
  pending: "待办",
} as const;

export function AuthoringWorkflowStatus({ status = {}, activeTab, onNavigate }: Props) {
  const steps = authoringSteps(status, activeTab);
  return (
    <nav className="authoring-workflow-status" aria-label="编制流程状态">
      {steps.map((step) => {
        const clickable = Boolean(step.tab && step.state !== "blocked" && onNavigate);
        const content = (
          <>
            <span className="authoring-workflow-status__dot" aria-hidden="true" />
            <span className="authoring-workflow-status__label">{step.label}</span>
            <span className="authoring-workflow-status__state">{stateLabel[step.state]}</span>
          </>
        );
        return clickable ? (
          <button
            type="button"
            key={step.id}
            className={`authoring-workflow-status__step is-${step.state}`}
            onClick={() => step.tab && onNavigate?.(step.tab)}
            aria-current={step.state === "active" ? "step" : undefined}
          >
            {content}
          </button>
        ) : (
          <span key={step.id} className={`authoring-workflow-status__step is-${step.state}`} aria-current={step.state === "active" ? "step" : undefined}>
            {content}
          </span>
        );
      })}
    </nav>
  );
}
