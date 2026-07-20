"use client";

import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { CalldataAddress, ExecutionResult, TransactionStatus, type CalldataEncodable, type TransactionHash } from "genlayer-js/types";
import { isBradburyChain, walletErrorMessage } from "@/lib/wallet";

interface WalletWriteInput {
  account: string;
  address: string;
  functionName: string;
  args?: CalldataEncodable[];
  value?: bigint;
  onStage?: (stage: WalletWriteStage, transactionHash?: string) => void;
}

export type WalletWriteStage = "preparing" | "awaiting_wallet" | "submitted" | "confirming";

export interface WalletWriteResult {
  hash: string;
  status: string;
}

export interface WalletTransactionState {
  status: string;
  executionResult: string;
  result: string;
  failed: boolean;
  confirmed: boolean;
}

interface WalletDeployInput {
  account: string;
  code: string;
  spec: string;
  worker: string;
  platform: string;
  feeBps: number;
  minScore: number;
  partialFloor: number;
}

export interface WalletDeployResult extends WalletWriteResult {
  address: string;
}

interface BrowserProvider {
  request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>;
}

function browserProvider(): BrowserProvider | null {
  if (typeof window === "undefined") return null;
  return (window as Window & { ethereum?: BrowserProvider }).ethereum || null;
}

function contractAddress(value: string): `0x${string}` {
  if (!/^0x[0-9a-fA-F]{40}$/.test(value)) throw new Error("The escrow contract address is invalid.");
  return value as `0x${string}`;
}

function accountAddress(value: string): `0x${string}` {
  if (!/^0x[0-9a-fA-F]{40}$/.test(value)) throw new Error("The connected wallet address is invalid.");
  return value as `0x${string}`;
}

function calldataAddress(value: string): CalldataAddress {
  const normalized = accountAddress(value).slice(2);
  return new CalldataAddress(Uint8Array.from(normalized.match(/.{2}/g)!.map((byte) => Number.parseInt(byte, 16))));
}

async function walletClient(account: string, onWalletRequest?: () => void) {
  const provider = browserProvider();
  if (!provider) throw new Error("Connect a browser wallet before submitting this transaction.");
  const chainId = String(await provider.request({ method: "eth_chainId" }));
  if (!isBradburyChain(chainId)) throw new Error("Switch the connected wallet to Bradbury before submitting this transaction.");
  const accounts = await provider.request({ method: "eth_accounts" }) as string[];
  if (!accounts.some((candidate) => sameAddress(candidate, account))) {
    throw new Error("The connected wallet account changed. Reconnect Wallet Mode and try again.");
  }
  const notifyingProvider: BrowserProvider = {
    request: async (request) => {
      if (request.method === "eth_sendTransaction" || request.method === "eth_signTransaction") onWalletRequest?.();
      return provider.request(request);
    },
  };
  type ClientConfig = NonNullable<Parameters<typeof createClient>[0]>;
  return createClient({ chain: testnetBradbury, account: accountAddress(account), provider: notifyingProvider as ClientConfig["provider"] });
}

export function sameAddress(left?: string | null, right?: string | null): boolean {
  return Boolean(left && right && left.toLowerCase() === right.toLowerCase());
}

export async function readBradburyTransaction(hash: string): Promise<WalletTransactionState> {
  if (!/^0x[0-9a-fA-F]{64}$/.test(hash)) throw new Error("The saved evaluation transaction hash is invalid.");
  const client = createClient({ chain: testnetBradbury });
  const transaction = await client.getTransaction({ hash: hash as TransactionHash });
  const status = String(transaction.statusName || transaction.status || "UNKNOWN");
  const executionResult = String(transaction.txExecutionResultName || transaction.txExecutionResult || "UNKNOWN");
  const result = String(transaction.resultName || transaction.result || "UNKNOWN");
  const failedStatuses = new Set(["CANCELED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"]);
  return {
    status,
    executionResult,
    result,
    failed: failedStatuses.has(status) || executionResult === ExecutionResult.FINISHED_WITH_ERROR || result === "FAILURE",
    confirmed: ["ACCEPTED", "FINALIZED"].includes(status) && executionResult === ExecutionResult.FINISHED_WITH_RETURN,
  };
}

export async function writeWalletContract(input: WalletWriteInput): Promise<WalletWriteResult> {
  input.onStage?.("preparing");
  const client = await walletClient(input.account, () => input.onStage?.("awaiting_wallet"));

  try {
    const hash = await client.writeContract({
      address: contractAddress(input.address),
      functionName: input.functionName,
      args: input.args || [],
      value: input.value || 0n,
    }) as TransactionHash;
    input.onStage?.("submitted", String(hash));
    input.onStage?.("confirming", String(hash));
    const receipt = await client.waitForTransactionReceipt({
      hash,
      status: TransactionStatus.ACCEPTED,
      interval: 4_000,
      retries: 150,
    });
    if (receipt.txExecutionResultName === ExecutionResult.FINISHED_WITH_ERROR) {
      throw new Error("Bradbury accepted the transaction but contract execution failed. Inspect the transaction before retrying.");
    }
    if (receipt.txExecutionResultName !== ExecutionResult.FINISHED_WITH_RETURN) {
      throw new Error("The transaction reached consensus without a confirmed successful execution result.");
    }
    return { hash: String(hash), status: String(receipt.statusName || TransactionStatus.ACCEPTED) };
  } catch (error) {
    throw new Error(walletErrorMessage(error));
  }
}

export async function deployWalletEscrow(input: WalletDeployInput): Promise<WalletDeployResult> {
  const client = await walletClient(input.account);
  try {
    const hash = await client.deployContract({
      code: input.code,
      args: [
        input.spec,
        calldataAddress(input.worker),
        calldataAddress(input.platform),
        input.feeBps,
        input.minScore,
        input.partialFloor,
      ],
    }) as TransactionHash;
    const receipt = await client.waitForTransactionReceipt({ hash, status: TransactionStatus.ACCEPTED, interval: 4_000, retries: 150 });
    if (receipt.txExecutionResultName === ExecutionResult.FINISHED_WITH_ERROR) {
      throw new Error("Bradbury accepted the deployment but contract execution failed. Inspect the transaction before retrying.");
    }
    if (receipt.txExecutionResultName !== ExecutionResult.FINISHED_WITH_RETURN) {
      throw new Error("The deployment reached consensus without a confirmed successful execution result.");
    }
    const decoded = receipt.txDataDecoded && "contractAddress" in receipt.txDataDecoded ? receipt.txDataDecoded.contractAddress : undefined;
    const address = receipt.recipient || decoded;
    if (!address || !/^0x[0-9a-fA-F]{40}$/.test(String(address))) {
      throw new Error("The accepted deployment did not return a valid contract address. Inspect the transaction before retrying.");
    }
    return { hash: String(hash), address: String(address), status: String(receipt.statusName || TransactionStatus.ACCEPTED) };
  } catch (error) {
    throw new Error(walletErrorMessage(error));
  }
}
