"""
End-to-end payment flow for freelance_escrow.py on a network that can move GEN.

The v0.79.1 localnet rejects any transaction carrying value, so this runs only
against testnet:

    # .env
    DEPLOYER_PRIVATE_KEY=0x...   # client: deploys, funds, links the detector
    WORKER_PRIVATE_KEY=0x...     # worker: accepts terms and submits work

    gltest tests/integration/test_escrow_payment_flow.py -v -s --network testnet_bradbury

Use throwaway wallets. Both need testnet GEN for gas; the client also needs
ESCROW_AMOUNT (wei, default 0.01 GEN) per test.
"""
import json
import os
import time

import pytest
from eth_utils import decode_hex, to_bytes
from genlayer_py.abi import calldata
from genlayer_py.abi.transactions import serialize
from genlayer_py.contracts.utils import make_calldata_object
from genlayer_py.exceptions import GenLayerError
from genlayer_py.types.calldata import CalldataAddress

from gltest import create_account, get_contract_factory, get_default_account, get_gl_client
from gltest.assertions import tx_execution_succeeded
from gltest.utils import extract_contract_address
from gltest_cli.config.general import get_general_config


NETWORK = get_general_config().get_network_name()
WORKER_KEY = os.environ.get("WORKER_PRIVATE_KEY", "")
AMOUNT = int(os.environ.get("ESCROW_AMOUNT", str(10**16)))
FEE_BPS = 200
MIN_SCORE = 70
FLOOR = 40

# example.com is stable and says exactly this, so a fair judge scores it high.
SPEC = (
    "A single web page stating that the domain is reserved for use in "
    "documentation examples and may be used without asking for permission."
)
URL = "https://example.com"

MANDATE = "Deliver documentation pages only. Never touch client funds or trade assets."
EVIDENCE_DRIFT = (
    "Activity log: agent moved the client's entire treasury into a 10x leveraged "
    "perpetual position on a new token and stopped producing documentation."
)

pytestmark = pytest.mark.skipif(
    not NETWORK.startswith("testnet") or not WORKER_KEY,
    reason="needs --network testnet_* and WORKER_PRIVATE_KEY (localnet can't move GEN)",
)

# Waits for ACCEPTED; settlement is confirmed separately by balance polling.
WAIT = dict(wait_interval=10000, wait_retries=120)


def _addr(account) -> CalldataAddress:
    return CalldataAddress(to_bytes(hexstr=str(account.address)))


def _balance(account) -> int:
    return int(get_gl_client().get_balance(account.address))


def _succeeded(receipt) -> bool:
    # gltest only reads consensus_data.leader_receipt, which testnet receipts
    # leave empty. On testnet, require that validators agreed (UNDETERMINED /
    # NO_MAJORITY writes nothing) and that the agreed execution returned.
    if tx_execution_succeeded(receipt):
        return True
    return (
        receipt.get("status_name") in ("ACCEPTED", "FINALIZED")
        and receipt.get("result_name") == "AGREE"
        and receipt.get("tx_execution_result_name") == "FINISHED_WITH_RETURN"
    )


def _send(method, args=None, value=0, attempts=3):
    """transact() with retries: Bradbury occasionally reverts the EVM wrapper
    tx (genlayer-py estimates gas with no margin), raising "Transaction failed".
    A reverted send changes nothing, so resending is safe."""
    for i in range(attempts):
        try:
            return method(args=args or []).transact(value=value, **WAIT)
        except GenLayerError as e:
            if "Transaction failed" not in str(e) or i == attempts - 1:
                raise
            print(f"  retrying after reverted send ({i + 1}/{attempts - 1})")
            time.sleep(10)


def _committed(receipt) -> None:
    assert _succeeded(receipt), {k: receipt.get(k) for k in ("tx_id", "recipient", "status_name", "result_name", "tx_execution_result_name")}


def _deploy(contract_file: str, args: list):
    factory = get_contract_factory(contract_file_path=contract_file)
    receipt = factory.deploy_contract_tx(args=args, **WAIT)
    _committed(receipt)
    try:
        address = extract_contract_address(receipt)
    except (TypeError, ValueError):
        address = receipt["recipient"]  # testnet: tx_data_decoded is empty
    return factory.build_contract(contract_address=address)


def _view(contract, method: str, *args) -> dict:
    """Read a JSON-returning view. Testnet's gen_call wraps the payload as
    {"data": <hex>, ...}, which genlayer-py's read_contract can't decode."""
    client = get_gl_client()
    data = serialize([calldata.encode(make_calldata_object(method=method, args=list(args), kwargs=None)), b"\x00"])
    result = client.provider.make_request(method="gen_call", params=[{
        "type": "read", "to": contract.address, "from": client.local_account.address,
        "data": data, "transaction_hash_variant": "latest-nonfinal",
    }])["result"]
    raw = result["data"] if isinstance(result, dict) else result
    return json.loads(calldata.decode(decode_hex("0x" + raw)))


def _wait_for_balance_change(account, before: int, timeout: int = 3600) -> int:
    """Settlement transfers run only after finalize() is FINALIZED; on Bradbury
    that takes ~30 min (the appeal window), so allow up to an hour."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        now = _balance(account)
        if now != before:
            return now
        time.sleep(15)
    return _balance(account)


def _open_job(worker, platform):
    """Client deploys the escrow (unfunded)."""
    return _deploy("freelance_escrow.py", [SPEC, _addr(worker), _addr(platform), FEE_BPS, MIN_SCORE, FLOOR])


def _fund_and_submit(escrow, worker):
    """Client funds; worker accepts terms and submits; the work is evaluated."""
    _committed(_send(escrow.fund, value=AMOUNT))
    as_worker = escrow.connect(worker)
    _committed(_send(as_worker.accept_terms))
    _committed(_send(as_worker.submit_work, [URL]))
    _committed(_send(escrow.evaluate))
    result = _view(escrow, "get_result")
    for _ in range(12):  # reads can briefly lag the accepted write on testnet
        if result["status"] != "SUBMITTED":
            break
        time.sleep(10)
        result = _view(escrow, "get_result")
    print(f"\n  escrow {escrow.address} evaluated: score={result.get('score')} status={result.get('status')}")
    assert result["status"] == "EVALUATED", result
    assert result["score"] >= MIN_SCORE, f"Expected a passing score for {URL}: {result}"


@pytest.fixture
def parties():
    worker = create_account(WORKER_KEY)
    assert worker.address.lower() != get_default_account().address.lower(), (
        "WORKER_PRIVATE_KEY must differ from DEPLOYER_PRIVATE_KEY"
    )
    return worker, create_account()


class TestEscrowPaymentFlow:

    def test_accepted_work_pays_worker_and_platform(self, parties):
        worker, platform = parties
        escrow = _open_job(worker, platform)
        _fund_and_submit(escrow, worker)

        worker_before = _balance(worker)
        _committed(_send(escrow.finalize))

        job = _view(escrow, "get_job")
        fee = AMOUNT * FEE_BPS // 10000
        worker_after = _wait_for_balance_change(worker, worker_before)
        print(f"  settlement: {job['settlement']['outcome']} worker+{worker_after - worker_before} platform+{_balance(platform)}")
        assert job["settlement"]["outcome"] == "ACCEPTED"
        assert job["amount"] == 0
        assert worker_after - worker_before == AMOUNT - fee
        assert _balance(platform) == fee

    def test_drifted_worker_payout_is_held(self, parties):
        worker, platform = parties
        detector = _deploy("value_drift_detector.py", [str(worker.address), MANDATE, [], False, 0, 80])
        escrow = _open_job(worker, platform)
        _committed(_send(escrow.link_drift_detector, [_addr(detector), 3600]))
        _fund_and_submit(escrow, worker)

        _committed(_send(detector.submit_evidence, ["text", EVIDENCE_DRIFT, "testnet flow"]))
        _committed(_send(detector.trigger_review))
        drift_status = _view(detector, "get_status")["status"]
        print(f"  detector: {drift_status}")
        assert drift_status in ("DRIFTED", "REVOKED")

        worker_before = _balance(worker)
        _committed(_send(escrow.finalize))

        job = _view(escrow, "get_job")
        print(f"  after finalize: {job['status']} gate={job['drift_gate']}")
        assert job["status"] == "EVALUATED"
        assert job["amount"] == AMOUNT
        assert job["drift_gate"]["hold_since"] != ""
        assert job["drift_gate"]["last_status"] == drift_status
        assert _balance(worker) == worker_before
