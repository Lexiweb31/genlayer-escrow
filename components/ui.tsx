import { RefreshIcon } from "@/components/icons";
import { EscrowCoreMark } from "@/components/escrow-core-mark";

export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return <header className="page-header">
    <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div>
    {actions && <div className="page-actions">{actions}</div>}
  </header>;
}

export function LoadingState({ label = "Loading Merit data…" }: { label?: string }) {
  return <div className="state-panel" aria-live="polite"><span className="loading-core"><EscrowCoreMark/></span><strong>{label}</strong><p>Reading the shared Render registry and Bradbury state.</p></div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="state-panel state-error" role="alert"><strong>Couldn’t load this view</strong><p>{message}</p>{retry && <button className="button secondary" onClick={retry}><RefreshIcon/> Retry</button>}</div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  return <div className="state-panel"><strong>{title}</strong><p>{description}</p>{action}</div>;
}

export function StatusPill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info" }) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}

export function MonoValue({ children, title }: { children: React.ReactNode; title?: string }) {
  return <code className="mono-value" title={title}>{children}</code>;
}
