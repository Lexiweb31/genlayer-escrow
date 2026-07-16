import type {
  ApiErrorDetail,
  CreateJobInput,
  CreateJobResponse,
  DemoConfig,
  JobDetailResponse,
  JobsResponse,
  TransactionResponse,
} from "@/lib/types";

export class MeritApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly action?: string;

  constructor(status: number, detail: ApiErrorDetail) {
    super(detail.message || "The Merit API could not complete this request.");
    this.name = "MeritApiError";
    this.status = status;
    this.code = detail.code || "API_ERROR";
    this.action = detail.action;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!path.startsWith("/api/")) {
    throw new Error("Merit browser requests must use a same-origin /api route.");
  }
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload
      ? (payload as { detail?: ApiErrorDetail }).detail || {}
      : {};
    throw new MeritApiError(response.status, detail);
  }
  return payload as T;
}

export const meritApi = {
  demoMode: (signal?: AbortSignal) => request<DemoConfig>("/api/demo-mode", { signal }),
  jobs: (signal?: AbortSignal) => request<JobsResponse>("/api/jobs", { signal }),
  job: (id: string, signal?: AbortSignal) =>
    request<JobDetailResponse>(`/api/jobs/${encodeURIComponent(id)}`, { signal }),
  createJob: (input: CreateJobInput) =>
    request<CreateJobResponse>("/api/jobs", { method: "POST", body: JSON.stringify(input) }),
  fund: (id: string, amountWei: string) =>
    action(id, "fund", { amount_wei: amountWei }),
  acceptTerms: (id: string) => action(id, "accept_terms"),
  submit: (id: string, url: string) => action(id, "submit", { url }),
  evaluate: (id: string) => action(id, "evaluate"),
  appeal: (id: string) => action(id, "appeal"),
  finalize: (id: string) => action(id, "finalize"),
};

function action(id: string, actionName: string, body: object = {}) {
  return request<TransactionResponse>(
    `/api/jobs/${encodeURIComponent(id)}/${actionName}`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function friendlyApiError(error: unknown): string {
  if (!(error instanceof MeritApiError)) {
    return error instanceof Error ? error.message : "Unexpected network error. Please retry.";
  }
  const messages: Record<string, string> = {
    BELOW_MINIMUM_DEMO_AMOUNT: "Minimum demo deposit is 0.001 GEN.",
    INSUFFICIENT_DEMO_GEN: "The Bradbury demo signer does not have enough testnet GEN.",
    WRONG_ROLE: "This action belongs to a different Bradbury demo role.",
    STALE_STATE: "The escrow changed on-chain. Refresh before retrying.",
    TESTNET_REJECTION: "Bradbury rejected the transaction. No success has been recorded.",
    LEGACY_SETTLEMENT_CONTRACT: "Legacy settlement contract — read only and unsafe to fund.",
    DEMO_ROLES_UNAVAILABLE: "Live demo actions require two different server-side demo signers.",
  };
  return messages[error.code] || error.message;
}
