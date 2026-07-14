"""
Marketplace API — FastAPI backend for the multi-job FreelanceEscrow marketplace.

Each posted job deploys its own FreelanceEscrow Intelligent Contract on
testnet_bradbury, signed by the server's deployer key. Deployed job addresses
are tracked in artifacts/jobs.json (the registry).

Run:
    source .venv/bin/activate
    cd dashboard
    uvicorn api:app --reload --port 8000
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

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
EVAL_ADDR   = deployments["evaluate_submission"]
EXPLORER    = "https://explorer-bradbury.genlayer.com/address/"

ESCROW_CODE = (ROOT / "contracts" / "freelance_escrow.py").read_text()

# ── Job registry (artifacts/jobs.json) ────────────────────────────────────────
# NOTE: on Render's free tier the filesystem is ephemeral, so this registry
# resets on redeploy/restart. Attach a persistent disk mounted at artifacts/
# to keep posted jobs across restarts. Acceptable for the demo.
JOBS_FILE = ROOT / "artifacts" / "jobs.json"


def _load_jobs() -> list[dict]:
    if JOBS_FILE.exists():
        return json.loads(JOBS_FILE.read_text()).get("jobs", [])
    # Seed with the escrow already deployed by scripts/deploy.py so the
    # marketplace isn't empty on first boot.
    seed = deployments.get("freelance_escrow")
    jobs: list[dict] = []
    if seed:
        jobs.append({
            "id":            seed,
            "address":       seed,
            "title":         "Fintech landing page",
            "spec":          "Build a landing page for a fintech startup. Must include: a "
                             "hero section with headline and CTA button, a features section "
                             "with at least 3 items, and a footer with contact email.",
            "fee_bps":       200,
            "min_score":     70,
            "partial_floor": 40,
            "created_at":    datetime.now(timezone.utc).isoformat(),
            "explorer":      EXPLORER + seed,
        })
        _save_jobs(jobs)
    return jobs


def _save_jobs(jobs: list[dict]) -> None:
    JOBS_FILE.write_text(json.dumps({"jobs": jobs}, indent=2))


def _find_job(job_id: str) -> dict:
    for j in _load_jobs():
        if j["id"] == job_id or j["address"].lower() == job_id.lower():
            return j
    raise HTTPException(status_code=404, detail=f"No job with id {job_id}")


# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Freelance Escrow Marketplace")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://genlayer-escrow.vercel.app",
        "https://lexiweb31.github.io",
        "http://localhost:8001",
        "http://localhost:3000",
    ],
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


def _call_write(contract_addr: str, method: str, args: list = None, value: int = 0) -> str:
    return client.write_contract(
        address=contract_addr,
        function_name=method,
        args=args or [],
        value=value,
    )


def _get_address(receipt: dict) -> Optional[str]:
    td = receipt.get("tx_data_decoded") or {}
    return td.get("contract_address") or receipt.get("recipient")


def _addresses(escrow_addr: str) -> dict:
    return {
        "escrow":              escrow_addr,
        "evaluator":           EVAL_ADDR,
        "deployer":            account.address,
        "explorer_escrow":     EXPLORER + escrow_addr,
        "explorer_evaluator":  EXPLORER + EVAL_ADDR,
    }


def _job_state(escrow_addr: str) -> dict:
    """Read live on-chain job + result for one escrow."""
    job    = json.loads(_call_read(escrow_addr, "get_job"))
    result = json.loads(_call_read(escrow_addr, "get_result"))
    return {"job": job, "result": result}


# ── Routes: read ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    # Kept for backward compat with the bundled single-page dashboard.
    return (Path(__file__).parent / "index.html").read_text()


@app.get("/api/health")
def health():
    return {"ok": True, "network": "testnet_bradbury", "jobs": len(_load_jobs())}


# Non-terminal statuses = a job that's still live in the marketplace.
_ACTIVE_STATUSES = {"UNFUNDED", "OPEN", "AGREED", "SUBMITTED", "EVALUATED"}


@app.get("/api/stats")
def stats():
    """
    Registry-wide aggregates for the live hero badge:
    total jobs, active (non-terminal) jobs, and total GEN currently locked
    in escrow across every job. Reads each job's live on-chain state; a
    single unreachable job degrades that job's contribution, not the request.
    """
    jobs = _load_jobs()
    total = len(jobs)
    active = 0
    escrow_wei = 0
    degraded = 0
    for j in jobs:
        try:
            state = _job_state(j["address"])
            status = state["job"].get("status")
            if status in _ACTIVE_STATUSES:
                active += 1
            # amount is zeroed on finalize, so only live jobs contribute.
            escrow_wei += int(state["job"].get("amount") or 0)
        except Exception:
            degraded += 1
    return {
        "network":        "testnet_bradbury",
        "total_jobs":     total,
        "active_jobs":    active,
        "escrow_wei":     escrow_wei,
        "escrow_gen":     escrow_wei / 1e18,
        "degraded_jobs":  degraded,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/jobs")
def list_jobs():
    """List every posted job with its live on-chain status."""
    out = []
    for j in _load_jobs():
        entry = {**j}
        try:
            state = _job_state(j["address"])
            entry["status"] = state["job"].get("status")
            entry["amount"] = state["job"].get("amount")
            entry["score"]  = state["result"].get("score")
        except Exception as e:
            entry["status"] = "UNKNOWN"
            entry["error"]  = str(e)
        out.append(entry)
    return {"jobs": out}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = _find_job(job_id)
    try:
        state = _job_state(job["address"])
        return {
            "meta":      job,
            "job":       state["job"],
            "result":    state["result"],
            "addresses": _addresses(job["address"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Routes: create ────────────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    spec:          str
    title:         Optional[str] = None
    fee_bps:       int = Field(default=200, ge=0, le=1000)
    min_score:     int = Field(default=70,  ge=0, le=100)
    partial_floor: int = Field(default=40,  ge=0, le=100)


@app.post("/api/jobs")
def create_job(req: CreateJobRequest):
    """Deploy a fresh FreelanceEscrow for this job and register it."""
    spec = req.spec.strip()
    if len(spec) < 20:
        raise HTTPException(status_code=422, detail="Spec must be at least 20 characters")
    if req.partial_floor > req.min_score:
        raise HTTPException(status_code=422, detail="partial_floor cannot exceed min_score")

    # Server signs as deployer, so client = worker = platform = deployer.
    try:
        tx = client.deploy_contract(
            ESCROW_CODE,
            account=account,
            args=[
                spec,
                CalldataAddress(account.address),
                CalldataAddress(account.address),
                req.fee_bps,
                req.min_score,
                req.partial_floor,
            ],
        )
        receipt = _wait(tx)
        addr = _get_address(receipt)
        if not addr:
            raise RuntimeError(f"No contract address in receipt: {json.dumps(dict(receipt), default=str)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deploy failed: {e}")

    addr  = str(addr)
    title = (req.title or spec.split(".")[0]).strip()[:80]
    record = {
        "id":            addr,
        "address":       addr,
        "title":         title,
        "spec":          spec,
        "fee_bps":       req.fee_bps,
        "min_score":     req.min_score,
        "partial_floor": req.partial_floor,
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "explorer":      EXPLORER + addr,
    }
    jobs = _load_jobs()
    jobs.insert(0, record)
    _save_jobs(jobs)
    return {"job": record, "tx": tx}


# ── Routes: per-job actions ───────────────────────────────────────────────────

class FundRequest(BaseModel):
    amount_wei: int = 1000000000000000   # 0.001 GEN default


class SubmitRequest(BaseModel):
    url: str


def _action(escrow_addr: str, method: str, args: list = None, value: int = 0) -> dict:
    tx = _call_write(escrow_addr, method, args=args, value=value)
    receipt = _wait(tx)
    return {"tx": tx, "status": receipt.get("status_name")}


@app.post("/api/jobs/{job_id}/fund")
def fund(job_id: str, req: FundRequest):
    job = _find_job(job_id)
    if req.amount_wei <= 0:
        raise HTTPException(status_code=422, detail="amount_wei must be positive")
    try:
        return _action(job["address"], "fund", value=req.amount_wei)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/accept_terms")
def accept_terms(job_id: str):
    job = _find_job(job_id)
    try:
        return _action(job["address"], "accept_terms")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/submit")
def submit_work(job_id: str, req: SubmitRequest):
    job = _find_job(job_id)
    if not req.url.startswith("http"):
        raise HTTPException(status_code=422, detail="URL must start with http")
    try:
        return _action(job["address"], "submit_work", args=[req.url])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/evaluate")
def evaluate(job_id: str):
    job = _find_job(job_id)
    try:
        return _action(job["address"], "evaluate")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/appeal")
def appeal(job_id: str):
    job = _find_job(job_id)
    try:
        return _action(job["address"], "appeal")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/finalize")
def finalize(job_id: str):
    job = _find_job(job_id)
    try:
        return _action(job["address"], "finalize")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
