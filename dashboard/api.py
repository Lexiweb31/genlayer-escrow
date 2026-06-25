"""
Dispute Dashboard API — FastAPI backend for the FreelanceEscrow contract.

Run:
    source .venv/bin/activate
    cd dashboard
    uvicorn api:app --reload --port 8000
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).parents[1]
load_dotenv(ROOT / ".env")

import eth_utils
from genlayer_py import create_account, create_client, testnet_bradbury
from genlayer_py.abi.calldata.encoder import encode as calldata_encode
from genlayer_py.abi.calldata.decoder import decode as calldata_decode
from genlayer_py.abi.transactions import serialize as tx_serialize
from genlayer_py.contracts.utils import make_calldata_object
from genlayer_py.types.calldata import CalldataAddress
from genlayer_py.types.transactions import TransactionStatus

# ── Chain / accounts ──────────────────────────────────────────────────────────
PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
if not PRIVATE_KEY:
    sys.exit("DEPLOYER_PRIVATE_KEY not set — copy .env.example to .env")

account = create_account(PRIVATE_KEY)
client  = create_client(testnet_bradbury, account=account)

deployments = json.loads((ROOT / "artifacts" / "deployments.json").read_text())
ESCROW_ADDR = deployments["freelance_escrow"]
EVAL_ADDR   = deployments["evaluate_submission"]

ESCROW_CODE = (ROOT / "contracts" / "freelance_escrow.py").read_text()
EVAL_CODE   = (ROOT / "contracts" / "evaluate_submission.py").read_text()

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Freelance Escrow Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://genlayer-escrow.vercel.app", "http://localhost:8001", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _wait(tx_hash: str) -> dict:
    return client.wait_for_transaction_receipt(
        tx_hash,
        status=TransactionStatus.ACCEPTED,
        interval=5000,
        retries=120,
    )


def _call_read(contract_addr: str, method: str, args: list = None) -> str:
    """Call a view method via gen_call, decoding the hex result."""
    data = [
        calldata_encode(make_calldata_object(method=method, args=args or [], kwargs=None)),
        b"\x00",
    ]
    raw = client.provider.make_request(
        method="gen_call",
        params=[{
            "type": "read",
            "to": contract_addr,
            "from": account.address,
            "data": tx_serialize(data),
            "transaction_hash_variant": "latest-nonfinal",
        }],
    )["result"]
    hex_str = raw["data"] if isinstance(raw, dict) else raw
    return calldata_decode(eth_utils.hexadecimal.decode_hex("0x" + hex_str))


def _call_write(method: str, args: list = None, value: int = 0) -> str:
    return client.write_contract(
        address=ESCROW_ADDR,
        function_name=method,
        args=args or [],
        value=value,
    )


# ── Routes: read ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "index.html").read_text()


@app.get("/api/status")
def get_status():
    try:
        job    = json.loads(_call_read(ESCROW_ADDR, "get_job"))
        result = json.loads(_call_read(ESCROW_ADDR, "get_result"))
        return {
            "job":    job,
            "result": result,
            "addresses": {
                "escrow":   ESCROW_ADDR,
                "evaluator": EVAL_ADDR,
                "deployer":  account.address,
                "explorer_escrow":   deployments["explorer"]["freelance_escrow"],
                "explorer_evaluator": deployments["explorer"]["evaluate_submission"],
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Routes: write ─────────────────────────────────────────────────────────────

class FundRequest(BaseModel):
    amount_wei: int = 1000000000000000   # 0.001 GEN default

@app.post("/api/fund")
def fund(req: FundRequest):
    try:
        tx = _call_write("fund", value=req.amount_wei)
        receipt = _wait(tx)
        return {"tx": tx, "status": receipt.get("status_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/accept_terms")
def accept_terms():
    try:
        tx = _call_write("accept_terms")
        receipt = _wait(tx)
        return {"tx": tx, "status": receipt.get("status_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SubmitRequest(BaseModel):
    url: str

@app.post("/api/submit")
def submit_work(req: SubmitRequest):
    try:
        tx = _call_write("submit_work", args=[req.url])
        receipt = _wait(tx)
        return {"tx": tx, "status": receipt.get("status_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/evaluate")
def evaluate():
    try:
        tx = _call_write("evaluate")
        receipt = _wait(tx)
        return {"tx": tx, "status": receipt.get("status_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/appeal")
def appeal():
    try:
        tx = _call_write("appeal")
        receipt = _wait(tx)
        return {"tx": tx, "status": receipt.get("status_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/finalize")
def finalize():
    try:
        tx = _call_write("finalize")
        receipt = _wait(tx)
        return {"tx": tx, "status": receipt.get("status_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
