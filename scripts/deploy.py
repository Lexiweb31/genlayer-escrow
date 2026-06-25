"""
Deploy FreelanceEscrow and EvaluateSubmission to testnet_asimov.

Usage:
    cd /path/to/genlayer
    cp .env.example .env          # fill in DEPLOYER_PRIVATE_KEY
    source .venv/bin/activate
    python scripts/deploy.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
if not PRIVATE_KEY:
    sys.exit("Error: DEPLOYER_PRIVATE_KEY is not set. Copy .env.example to .env and fill it in.")

from genlayer_py import create_account, create_client, testnet_asimov
from genlayer_py.types.calldata import CalldataAddress
from gltest.utils import extract_contract_address

ROOT      = Path(__file__).parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

ESCROW_CODE = (ROOT / "contracts" / "freelance_escrow.py").read_text()
EVAL_CODE   = (ROOT / "contracts" / "evaluate_submission.py").read_text()

client  = create_client(testnet_asimov)
account = create_account(PRIVATE_KEY)

print(f"\nDeployer : {account.address}")
print(f"Network  : testnet_asimov\n")

# ── Deploy EvaluateSubmission ─────────────────────────────────────────────────
print("1/2  Deploying EvaluateSubmission …")
tx1 = client.deploy_contract(EVAL_CODE, account=account, args=[])
r1  = client.wait_for_transaction_receipt(tx1, retries=60)
eval_address = extract_contract_address(r1)
print(f"     ✓ EvaluateSubmission → {eval_address}")

# ── Deploy FreelanceEscrow (demo instance) ────────────────────────────────────
# Demo setup: deployer acts as both client and worker/platform.
# Replace with real addresses for a live job.
DEMO_SPEC     = (
    "Build a landing page for a fintech startup. Must include: "
    "a hero section with headline and CTA button, "
    "a features section with at least 3 items, "
    "and a footer with contact email."
)
WORKER_ADDR   = CalldataAddress(account.address)
PLATFORM_ADDR = CalldataAddress(account.address)
FEE_BPS       = 200   # 2%
MIN_SCORE     = 70
PARTIAL_FLOOR = 40

print("2/2  Deploying FreelanceEscrow …")
tx2 = client.deploy_contract(
    ESCROW_CODE,
    account=account,
    args=[DEMO_SPEC, WORKER_ADDR, PLATFORM_ADDR, FEE_BPS, MIN_SCORE, PARTIAL_FLOOR],
)
r2 = client.wait_for_transaction_receipt(tx2, retries=60)
escrow_address = extract_contract_address(r2)
print(f"     ✓ FreelanceEscrow    → {escrow_address}")

# ── Save ──────────────────────────────────────────────────────────────────────
deployment = {
    "network":             "testnet_asimov",
    "deployer":            account.address,
    "evaluate_submission": str(eval_address),
    "freelance_escrow":    str(escrow_address),
    "explorer": {
        "evaluate_submission": f"https://explorer-asimov.genlayer.com/address/{eval_address}",
        "freelance_escrow":    f"https://explorer-asimov.genlayer.com/address/{escrow_address}",
    },
}

out = ARTIFACTS / "deployments.json"
out.write_text(json.dumps(deployment, indent=2))

print(f"\nSaved to {out.relative_to(ROOT)}")
print("\nExplorer:")
print(f"  EvaluateSubmission → {deployment['explorer']['evaluate_submission']}")
print(f"  FreelanceEscrow    → {deployment['explorer']['freelance_escrow']}")
print()
