"""
End-to-end demo of the FreelanceEscrow flow on testnet_bradbury.

Walks through every state:
  UNFUNDED → OPEN → AGREED → SUBMITTED → EVALUATED → ACCEPTED/PARTIAL/REFUNDED

Usage:
    source .venv/bin/activate
    python scripts/demo_flow.py
"""
import json
import os
import sys
from pathlib import Path

import eth_utils
from dotenv import load_dotenv

ROOT = Path(__file__).parents[1]
load_dotenv(ROOT / ".env")

PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
if not PRIVATE_KEY:
    sys.exit("DEPLOYER_PRIVATE_KEY not set")

from genlayer_py import create_account, create_client, testnet_bradbury
from genlayer_py.abi.calldata.decoder import decode as calldata_decode
from genlayer_py.abi.calldata.encoder import encode as calldata_encode
from genlayer_py.abi.transactions import serialize as tx_serialize
from genlayer_py.contracts.utils import make_calldata_object
from genlayer_py.types.transactions import TransactionStatus

deployments = json.loads((ROOT / "artifacts" / "deployments.json").read_text())
ESCROW_ADDR = deployments["freelance_escrow"]

account = create_account(PRIVATE_KEY)
client  = create_client(testnet_bradbury, account=account)

FUND_AMOUNT = 1_000_000_000_000_000   # 0.001 GEN in wei
SUBMIT_URL  = "https://stripe.com"    # real fintech page the AI will fetch & grade


# ── Helpers ───────────────────────────────────────────────────────────────────

def read(method, args=None):
    data = [
        calldata_encode(make_calldata_object(method=method, args=args or [], kwargs=None)),
        b"\x00",
    ]
    raw = client.provider.make_request(
        method="gen_call",
        params=[{
            "type": "read",
            "to": ESCROW_ADDR,
            "from": account.address,
            "data": tx_serialize(data),
            "transaction_hash_variant": "latest-nonfinal",
        }],
    )["result"]
    hex_str = raw["data"] if isinstance(raw, dict) else raw
    return calldata_decode(eth_utils.hexadecimal.decode_hex("0x" + hex_str))


def write(method, args=None, value=0):
    print(f"  → calling {method}() …", end="", flush=True)
    tx = client.write_contract(
        address=ESCROW_ADDR,
        function_name=method,
        args=args or [],
        value=value,
    )
    receipt = client.wait_for_transaction_receipt(
        tx, status=TransactionStatus.ACCEPTED, interval=5000, retries=120
    )
    status = receipt.get("status_name", "?")
    result = receipt.get("result_name", "?")
    print(f" {status} / {result}  (tx: {str(tx)[:12]}…)")
    return receipt


def banner(msg):
    print(f"\n{'─' * 55}")
    print(f"  {msg}")
    print(f"{'─' * 55}")


# ── Flow ──────────────────────────────────────────────────────────────────────

banner("Freelance Escrow — end-to-end demo")
print(f"  Deployer : {account.address}")
print(f"  Contract : {ESCROW_ADDR}")
print(f"  URL      : {SUBMIT_URL}")

job = json.loads(read("get_job"))
print(f"\n  Current status: {job['status']}")

# 1. Fund
if job["status"] == "UNFUNDED":
    banner("Step 1 / 5 — Fund")
    write("fund", value=FUND_AMOUNT)
    job = json.loads(read("get_job"))
    print(f"  Amount locked : {job['amount']} wei")

# 2. Accept terms (demo: deployer is also the worker)
if job["status"] == "OPEN":
    banner("Step 2 / 5 — Accept Terms")
    write("accept_terms")
    job = json.loads(read("get_job"))
    print(f"  Terms agreed  : {job['terms_agreed']}")

# 3. Submit work
if job["status"] == "AGREED":
    banner("Step 3 / 5 — Submit Work")
    write("submit_work", args=[SUBMIT_URL])
    job = json.loads(read("get_job"))
    print(f"  Submission    : {job.get('submission_url', SUBMIT_URL)}")

# 4. Evaluate (AI fetches URL and scores it — takes ~30 s on testnet)
if job["status"] == "SUBMITTED":
    banner("Step 4 / 5 — Evaluate  (AI is reading the page…)")
    write("evaluate")
    result_raw = read("get_result")
    result = json.loads(result_raw)
    score = result.get("score", 0)
    print(f"  Score     : {score} / 100")
    print(f"  Reasoning : {result.get('reasoning', '')}")

# 5. Finalize — trigger payout
job = json.loads(read("get_job"))
if job["status"] == "EVALUATED":
    banner("Step 5 / 5 — Finalize")
    write("finalize")

# ── Final state ───────────────────────────────────────────────────────────────
banner("Final state")
job    = json.loads(read("get_job"))
result = json.loads(read("get_result"))

print(f"  Status    : {job['status']}")
if result.get("score") is not None:
    print(f"  Score     : {result['score']} / 100")
    print(f"  Reasoning : {result['reasoning']}")
print(f"\n  Explorer  : {deployments['explorer']['freelance_escrow']}")
print()
