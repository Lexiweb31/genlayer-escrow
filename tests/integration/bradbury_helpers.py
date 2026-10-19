"""
Shared helpers for tests that run against the Bradbury testnet.

gltest 0.29.2 and genlayer-py misread current Bradbury responses, so these
helpers read receipts, deploy addresses and view results themselves, and
retry the transient failures testnet produces (EVM wrapper reverts, leader
timeouts). Wallets come from .env: DEPLOYER_PRIVATE_KEY (client) and
WORKER_PRIVATE_KEY (worker); use throwaways.
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


from genlayer_py.types import transactions as _tx

# Bradbury reports transaction status codes newer than genlayer-py knows (seen:
# 14), and get_transaction() then raises KeyError mid-poll. Treat unknown codes
# as still in flight so waits continue to a real terminal status.
for _code in range(14, 32):
    _tx.TRANSACTION_STATUS_NUMBER_TO_NAME.setdefault(str(_code), _tx.TransactionStatus.PENDING)

NETWORK = get_general_config().get_network_name()
WORKER_KEY = os.environ.get("WORKER_PRIVATE_KEY", "")

requires_testnet = pytest.mark.skipif(
    not NETWORK.startswith("testnet") or not WORKER_KEY,
    reason="needs --network testnet_* and WORKER_PRIVATE_KEY (localnet can't move GEN)",
)

# Waits for ACCEPTED; settlement is confirmed separately by balance polling.
WAIT = dict(wait_interval=10000, wait_retries=120)


def addr(account) -> CalldataAddress:
    return CalldataAddress(to_bytes(hexstr=str(account.address)))


def balance(account) -> int:
    return int(get_gl_client().get_balance(account.address))


def succeeded(receipt) -> bool:
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


def outcome(receipt) -> str:
    return f"{receipt.get('status_name')}/{receipt.get('result_name')}"


def send(method, args=None, value=0, attempts=3):
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


def send_until_agreed(method, args=None, attempts=3):
    """For consensus writes whose failed rounds (LEADER_TIMEOUT, UNDETERMINED)
    write nothing, so a retry is safe. Returns the last receipt."""
    for attempt in range(attempts):
        receipt = send(method, args)
        if succeeded(receipt) or attempt == attempts - 1:
            return receipt
        print(f"  {outcome(receipt)}; retrying")


def committed(receipt) -> None:
    assert succeeded(receipt), {k: receipt.get(k) for k in ("tx_id", "recipient", "status_name", "result_name", "tx_execution_result_name")}


def deploy(contract_file: str, args: list):
    factory = get_contract_factory(contract_file_path=contract_file)
    receipt = factory.deploy_contract_tx(args=args, **WAIT)
    committed(receipt)
    try:
        address = extract_contract_address(receipt)
    except (TypeError, ValueError):
        address = receipt["recipient"]  # testnet: tx_data_decoded is empty
    return factory.build_contract(contract_address=address)


def view(contract, method: str, *args) -> dict:
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


def view_until(contract, method: str, done, tries: int = 12) -> dict:
    """Poll a view until done(result): reads can briefly lag an accepted write."""
    result = view(contract, method)
    for _ in range(tries):
        if done(result):
            break
        time.sleep(10)
        result = view(contract, method)
    return result


def wait_for_balance_change(account, before: int, timeout: int = 3600) -> int:
    """Settlement transfers run only after finalize() is FINALIZED; on Bradbury
    that takes ~30 min (the appeal window), so allow up to an hour."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        now = balance(account)
        if now != before:
            return now
        time.sleep(15)
    return balance(account)


def worker_account():
    worker = create_account(WORKER_KEY)
    assert worker.address.lower() != get_default_account().address.lower(), (
        "WORKER_PRIVATE_KEY must differ from DEPLOYER_PRIVATE_KEY"
    )
    return worker


def open_job(spec: str, worker, platform, url: str, amount: int,
             fee_bps: int = 200, min_score: int = 70, floor: int = 40, detector=None) -> tuple:
    """Deploy, (link detector), fund, accept, submit and evaluate one escrow job.
    Returns (escrow, evaluate_receipt, result). result is None when evaluate()
    never reached agreement; the job then stays SUBMITTED."""
    escrow = deploy("freelance_escrow.py", [spec, addr(worker), addr(platform), fee_bps, min_score, floor])
    if detector is not None:
        committed(send(escrow.link_drift_detector, [addr(detector), 3600]))
    committed(send(escrow.fund, value=amount))
    as_worker = escrow.connect(worker)
    committed(send(as_worker.accept_terms))
    committed(send(as_worker.submit_work, [url]))
    receipt = send_until_agreed(escrow.evaluate)
    if not succeeded(receipt):
        return escrow, receipt, None
    result = view_until(escrow, "get_result", lambda r: r["status"] != "SUBMITTED")
    return escrow, receipt, result
