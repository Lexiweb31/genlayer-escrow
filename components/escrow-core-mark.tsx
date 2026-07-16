import { LockIcon } from "@/components/icons";

export function EscrowCoreMark({ size = "medium", tone = "active" }: { size?: "small" | "medium" | "large"; tone?: "active" | "success" | "pending" | "danger" }) {
  return <span className={`escrow-core-mark ${size} ${tone}`} aria-hidden="true"><i/><b><LockIcon size={size === "small" ? 13 : size === "large" ? 25 : 17}/></b><i/></span>;
}
