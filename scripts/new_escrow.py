"""
Deploy a fresh FreelanceEscrow contract, reusing the existing EvaluateSubmission.

Usage:
    source .venv/bin/activate
    python scripts/new_escrow.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
ROOT = Path(__file__).parents[1]
load_dotenv(ROOT / ".env")

PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
if not PRIVATE_KEY:
    sys.exit("DEPLOYER_PRIVATE_KEY not set")

from genlayer_py import create_account, create_client, testnet_bradbury
from genlayer_py.types.calldata import CalldataAddress
from genlayer_py.types.transactions import TransactionStatus

account = create_account(PRIVATE_KEY)
client  = create_client(testnet_bradbury, account=account)

existing = json.loads((ROOT / "artifacts" / "deployments.json").read_text())
EVAL_ADDR = existing["evaluate_submission"]

ESCROW_CODE = (ROOT / "contracts" / "freelance_escrow.py").read_text()

SPEC = (
    "Build a landing page for a fintech startup. Must include: "
    "a hero section with headline and CTA button, "
    "a features section with at least 3 items, "
    "and a footer with contact email."
)

print(f"\nDeployer : {account.address}")
print(f"Reusing  : EvaluateSubmission @ {EVAL_ADDR}")
print("Deploying fresh FreelanceEscrow …")

tx = client.deploy_contract(
    ESCROW_CODE,
    account=account,
    args=[SPEC, CalldataAddress(account.address), CalldataAddress(account.address), 200, 70, 40],
)
print(f"  tx: {tx}")
r = client.wait_for_transaction_receipt(tx, status=TransactionStatus.ACCEPTED, interval=5000, retries=120)

td = (r.get("tx_data_decoded") or {})
addr = td.get("contract_address") or r.get("recipient")
if not addr:
    sys.exit(f"Could not find address in receipt:\n{json.dumps(dict(r), default=str, indent=2)}")

print(f"  ✓ FreelanceEscrow → {addr}")

existing["freelance_escrow"] = str(addr)
existing["explorer"]["freelance_escrow"] = f"https://explorer-bradbury.genlayer.com/address/{addr}"
(ROOT / "artifacts" / "deployments.json").write_text(json.dumps(existing, indent=2))

print(f"\ndeployments.json updated")
print(f"Explorer: {existing['explorer']['freelance_escrow']}\n")
