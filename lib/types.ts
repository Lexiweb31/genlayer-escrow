export type JobStatus =
  | "UNFUNDED"
  | "OPEN"
  | "AGREED"
  | "SUBMITTED"
  | "EVALUATED"
  | "SETTLEMENT_PENDING"
  | "ACCEPTED"
  | "PARTIAL"
  | "REFUNDED"
  | "LEGACY_UNSAFE"
  | "UNKNOWN";

export type SettlementStatus =
  | "NOT_STARTED"
  | "PENDING_FINALIZATION"
  | "FINALIZED"
  | "LEGACY_UNSAFE"
  | string;

export interface DemoConfig {
  mode: "server-signed-demo" | "simulated-walkthrough" | string;
  network: string;
  live_actions_enabled: boolean;
  client_address: string | null;
  worker_address: string | null;
  notice: string;
}

export interface SettlementTransfer {
  recipient: string;
  amount: string;
  settlement_type: "WORKER_PAYOUT" | "CLIENT_REFUND" | "PLATFORM_FEE" | string;
}

export interface TransferEvidence extends SettlementTransfer {
  reference: string;
  status: string;
  explorer?: string | null;
  recipient_role?: string;
}

export interface SettlementRecord {
  outcome?: "ACCEPTED" | "PARTIAL" | "REFUNDED" | string;
  settlement_type?: string;
  transfer_status?: SettlementStatus;
  transfers?: SettlementTransfer[];
  transfer_evidence?: TransferEvidence[];
  transfer_reference?: string[];
  parent_transaction?: string;
  parent_status?: string;
  parent_explorer?: string;
  explorer?: string;
  confirmation_basis?: string;
  submitted_at?: string;
  finalized_at?: string;
}

export interface JobRecord {
  id?: string;
  address: string;
  title?: string;
  spec?: string;
  status: JobStatus;
  on_chain_status?: string;
  lifecycle_status?: string;
  amount?: string;
  fee_bps?: number;
  min_score?: number;
  partial_floor?: number;
  client?: string;
  worker?: string;
  client_address?: string;
  worker_address?: string;
  submission_url?: string;
  terms_agreed?: boolean;
  appeal_used?: boolean;
  score?: number | null;
  evaluation_complete?: boolean;
  settlement?: SettlementRecord;
  deployment_tx?: string;
  legacy_contract?: boolean;
  legacy_warning?: string;
  created_at?: string;
  updated_at?: string;
  error?: string;
}

export interface EvaluationResult {
  status?: JobStatus;
  score?: number | null;
  reasoning?: string;
  min_score?: number;
  settlement_outcome?: string;
  transfer_status?: string;
}

export interface ContractAddresses {
  escrow?: string;
  evaluator?: string;
  demo_client?: string;
  demo_worker?: string;
  account_mode?: string;
  explorer_escrow?: string;
  explorer_evaluator?: string;
}

export interface MarketplaceStats {
  network: string;
  total_jobs: number;
  active_jobs: number;
  open_opportunities: number;
  locked_wei: string;
  pending_settlement_wei: string;
  protected_wei: string;
  settlement_pending: number;
  finalized_settlements: number;
  finalized_settlement_wei: string;
  degraded_jobs: number;
  legacy_jobs: number;
  generated_at: string;
}

export interface JobsResponse {
  jobs: JobRecord[];
  stats: MarketplaceStats;
  demo: DemoConfig;
}

export interface JobDetailResponse {
  meta: JobRecord;
  job: JobRecord;
  result: EvaluationResult;
  addresses: ContractAddresses;
  demo: DemoConfig;
}

export interface ApiErrorDetail {
  code?: string;
  message?: string;
  action?: string;
  testnet_detail?: string;
  minimum_wei?: string;
}

export interface TransactionResponse {
  tx: string;
  status: string;
  job_status?: JobStatus;
  transaction_type: string;
  signer_role: string;
  settlement?: SettlementRecord;
  notice?: string;
}

export interface CreateJobInput {
  title?: string | null;
  spec: string;
  fee_bps: number;
  min_score: number;
  partial_floor: number;
}

export interface CreateJobResponse {
  job: JobRecord;
  tx: string;
  transaction_type: string;
  signer_role: string;
}
