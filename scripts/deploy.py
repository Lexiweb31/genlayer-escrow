"""
Deploy FreelanceEscrow and EvaluateSubmission to testnet_bradbury.

Usage:
    cd /path/to/genlayer
    cp .env.example .env          # fill in both DEMO_* keys
    source .venv/bin/activate
    python scripts/deploy.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CLIENT_PRIVATE_KEY = os.getenv("DEMO_CLIENT_PRIVATE_KEY")
WORKER_PRIVATE_KEY = os.getenv("DEMO_WORKER_PRIVATE_KEY")
if not CLIENT_PRIVATE_KEY or not WORKER_PRIVATE_KEY:
    sys.exit("Error: both DEMO_CLIENT_PRIVATE_KEY and DEMO_WORKER_PRIVATE_KEY are required.")

from genlayer_py import create_account, create_client, testnet_bradbury
from genlayer_py.types.calldata import CalldataAddress
from genlayer_py.types.transactions import TransactionStatus

ROOT      = Path(__file__).parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

ESCROW_CODE = (ROOT / "contracts" / "freelance_escrow.py").read_text()
EVAL_CODE   = (ROOT / "contracts" / "evaluate_submission.py").read_text()

client         = create_client(testnet_bradbury)
client_account = create_account(CLIENT_PRIVATE_KEY)
worker_account = create_account(WORKER_PRIVATE_KEY)
if str(client_account.address).lower() == str(worker_account.address).lower():
    sys.exit("Error: demo client and worker keys must resolve to different addresses.")

print(f"\nDemo client : {client_account.address}")
print(f"Demo worker : {worker_account.address}")
print(f"Network  : testnet_bradbury\n")

def _get_address(receipt):
    """Extract deployed contract address from receipt.

    GenLayer deployment receipts put the new contract address in 'recipient'.
    """
    td = receipt.get("tx_data_decoded") or {}
    if td.get("contract_address"):
        return td["contract_address"]
    # GenLayer testnet: recipient IS the newly deployed contract
    addr = receipt.get("recipient")
    if addr:
        return addr
    raise ValueError(f"Cannot find contract address in receipt:\n{json.dumps(dict(receipt), default=str, indent=2)}")


# ── Deploy EvaluateSubmission ─────────────────────────────────────────────────
print("1/2  Deploying EvaluateSubmission …")
tx1 = client.deploy_contract(EVAL_CODE, account=client_account, args=[])
print(f"     tx: {tx1}")
r1  = client.wait_for_transaction_receipt(
    tx1, status=TransactionStatus.ACCEPTED, interval=5000, retries=120
)
eval_address = _get_address(r1)
print(f"     ✓ EvaluateSubmission → {eval_address}")

# ── Deploy FreelanceEscrow (demo instance) ────────────────────────────────────
# Server-signed Bradbury demo setup. The client and worker must remain distinct.
DEMO_SPEC     = (
    "Build a landing page for a fintech startup. Must include: "
    "a hero section with headline and CTA button, "
    "a features section with at least 3 items, "
    "and a footer with contact email."
)
WORKER_ADDR   = CalldataAddress(worker_account.address)
PLATFORM_ADDR = CalldataAddress(client_account.address)
FEE_BPS       = 200   # 2%
MIN_SCORE     = 70
PARTIAL_FLOOR = 40

print("2/2  Deploying FreelanceEscrow …")
tx2 = client.deploy_contract(
    ESCROW_CODE,
    account=client_account,
    args=[DEMO_SPEC, WORKER_ADDR, PLATFORM_ADDR, FEE_BPS, MIN_SCORE, PARTIAL_FLOOR],
)
print(f"     tx: {tx2}")
r2 = client.wait_for_transaction_receipt(
    tx2, status=TransactionStatus.ACCEPTED, interval=5000, retries=120
)
escrow_address = _get_address(r2)
print(f"     ✓ FreelanceEscrow    → {escrow_address}")

# ── Save ──────────────────────────────────────────────────────────────────────
deployment = {
    "network":             "testnet_bradbury",
    "deployer":            client_account.address,
    "demo_client":         client_account.address,
    "demo_worker":         worker_account.address,
    "settlement_version":  "safe-eoa-external-message-v2",
    "deployment_transaction": str(tx2),
    "evaluate_submission": str(eval_address),
    "freelance_escrow":    str(escrow_address),
    "explorer": {
        "evaluate_submission": f"https://explorer-bradbury.genlayer.com/address/{eval_address}",
        "freelance_escrow":    f"https://explorer-bradbury.genlayer.com/address/{escrow_address}",
    },
}

out = ARTIFACTS / "deployments.json"
out.write_text(json.dumps(deployment, indent=2))

print(f"\nSaved to {out.relative_to(ROOT)}")
print("\nExplorer:")
print(f"  EvaluateSubmission → {deployment['explorer']['evaluate_submission']}")
print(f"  FreelanceEscrow    → {deployment['explorer']['freelance_escrow']}")
print()
