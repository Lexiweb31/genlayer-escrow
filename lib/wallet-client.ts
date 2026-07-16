"use client";

import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { ExecutionResult, TransactionStatus, type CalldataEncodable, type TransactionHash } from "genlayer-js/types";
import { isBradburyChain, walletErrorMessage } from "@/lib/wallet";

interface WalletWriteInput {
  account: string;
  address: string;
  functionName: string;
  args?: CalldataEncodable[];
  value?: bigint;
}

export interface WalletWriteResult {
  hash: string;
  status: string;
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

export function sameAddress(left?: string | null, right?: string | null): boolean {
  return Boolean(left && right && left.toLowerCase() === right.toLowerCase());
}

export async function writeWalletContract(input: WalletWriteInput): Promise<WalletWriteResult> {
  const provider = browserProvider();
  if (!provider) throw new Error("Connect a browser wallet before submitting this transaction.");
  const chainId = String(await provider.request({ method: "eth_chainId" }));
  if (!isBradburyChain(chainId)) throw new Error("Switch the connected wallet to Bradbury before submitting this transaction.");

  type ClientConfig = NonNullable<Parameters<typeof createClient>[0]>;
  const client = createClient({
    chain: testnetBradbury,
    account: accountAddress(input.account),
    provider: provider as ClientConfig["provider"],
  });

  try {
    const hash = await client.writeContract({
      address: contractAddress(input.address),
      functionName: input.functionName,
      args: input.args || [],
      value: input.value || 0n,
    }) as TransactionHash;
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
