"""Safety-contract tests for the live Bradbury custody matrix runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "custody_matrix.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("custody_matrix", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configured_environment() -> dict[str, str]:
    return {
        "MERIT_API_URL": "https://merit.example",
        "BRADBURY_RPC_URL": "https://rpc.example",
        "CLIENT_PRIVATE_KEY": "0x" + "11" * 32,
        "WORKER_PRIVATE_KEY": "0x" + "22" * 32,
    }


def test_dry_run_uses_public_addresses_and_never_returns_private_keys():
    """Changing a caller to echo configuration secrets must break this test."""
    runner = load_runner()
    environment = configured_environment()

    config = runner.load_configuration(environment, balance_of=lambda _address: 1)
    evidence = runner.dry_run_evidence(config)
    rendered = str(evidence)

    assert evidence["wallets"]["client"] != evidence["wallets"]["worker"]
    assert environment["CLIENT_PRIVATE_KEY"] not in rendered
    assert environment["WORKER_PRIVATE_KEY"] not in rendered


def test_dry_run_rejects_the_same_wallet_for_client_and_worker():
    """Using one wallet for both contract roles would invalidate custody checks."""
    runner = load_runner()
    environment = configured_environment()
    environment["WORKER_PRIVATE_KEY"] = environment["CLIENT_PRIVATE_KEY"]

    with pytest.raises(runner.ConfigurationError, match="different"):
        runner.load_configuration(environment, balance_of=lambda _address: 1)


def test_dry_run_rejects_an_unfunded_required_wallet():
    """Removing the balance check would permit a matrix that cannot execute."""
    runner = load_runner()

    with pytest.raises(runner.ConfigurationError, match="funded"):
        runner.load_configuration(configured_environment(), balance_of=lambda _address: 0)


def test_live_mode_requires_an_explicit_execution_switch():
    """Removing the switch would allow an ordinary command to send live writes."""
    runner = load_runner()

    assert runner.execution_requested([]) is False
    assert runner.execution_requested(["--execute"]) is True
