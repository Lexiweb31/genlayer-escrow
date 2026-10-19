# Bradbury custody matrix

`scripts/custody_matrix.py` is a deliberately opt-in, **Bradbury testnet-only**
release gate. It creates disposable wallet-created escrows and verifies the
entire custody path: deployment registration, role-gated lifecycle calls,
evaluation, settlement registration, background reconciliation, replay safety,
and finalized transfer evidence.

It never loads `.env`, never writes environment values to evidence, and never
prints a private key. Do not use production wallets, production RPC endpoints,
or mainnet funds.

## Safe preflight

Use Python 3.12 and the project virtual environment. The default command and
`--dry-run` send **no transactions**. Both modes require these environment
variables so the actual wallets and Bradbury balance can be verified:

```bash
export MERIT_API_URL='https://your-render-service.example'
export BRADBURY_RPC_URL='https://your-bradbury-rpc.example'
export CLIENT_PRIVATE_KEY='0x…'
export WORKER_PRIVATE_KEY='0x…'

.venv/bin/python scripts/custody_matrix.py --dry-run
```

The client and worker must resolve to different, funded addresses. Dry-run
output contains only their public addresses, the public service URLs, and the
fact that zero writes were sent. A failure never echoes a private-key parser or
RPC diagnostic.

## Live testnet execution

The Bounty contract requires two different non-client entrants. Therefore a
complete live matrix additionally needs a third, distinct, funded **testnet**
wallet and seven public deterministic fixture URLs:

```bash
export BOUNTY_SECOND_WORKER_PRIVATE_KEY='0x…'
export MERIT_FULL_FIXTURE_URL='https://…'
export MERIT_SPLIT_FIXTURE_URL='https://…'
export MERIT_REFUND_FIXTURE_URL='https://…'
export MERIT_BOUNTY_WINNER_URL='https://…'
export MERIT_BOUNTY_LOSER_URL='https://…'
export MERIT_BOUNTY_REFUND_FIRST_URL='https://…'
export MERIT_BOUNTY_REFUND_SECOND_URL='https://…'

.venv/bin/python scripts/custody_matrix.py \
  --execute --confirm-testnet-custody \
  --output /tmp/merit-custody-evidence.json
```

`--execute` alone is not enough; the acknowledgement flag prevents an ordinary
test invocation from spending testnet GEN. The runner validates all fixture
URLs and all three funded, distinct wallets before its first deployment, so a
missing Bounty input cannot leave a partial run behind.

Before a write, the runner asks the exact `BRADBURY_RPC_URL` for `eth_chainId`
and requires chain `4221`; neither a URL name nor the separate Render API URL
can satisfy that check. `--timeout-seconds` must be between 1 and 3600. Live
execution requires `--output`: it atomically updates a redacted recovery file
immediately after every transaction broadcast, so an interrupted run retains
submitted transaction hashes.

The fixtures must be public and stable under GenLayer rendering. The full-pay
and Bounty-winner scenarios use a zero threshold to make their successful
settlement deterministic. The split and refund scenarios require fixtures that
are known not to score a perfect 100; the runner fails evidence rather than
reclassifying an unexpected model result.

## Evidence and acceptance criteria

The JSON report records only public data: job address, all transaction hashes,
observed state transitions, winning Bounty entry, durable-registry replay
response, starting/ending balances, and finalized settlement transfer records.
Each settlement parent must reach Bradbury `FINALIZED`; after finalization
submission, the runner waits through the public registry rather than locally
polling chain state. Repeating settlement registration must return
`replayed: true`.

Every lifecycle transaction is followed by a fresh contract read. The evidence
stores the observed state and its originating transaction hash, rather than a
prewritten lifecycle array. A second settlement registration that is not
explicitly marked `replayed: true` fails the gate.

For recipients that do not sign `finalize`, the observed balance delta must
equal the finalized contract transfer exactly. The client may be a refund
recipient and is also the finalizing signer; its raw balance delta is marked
`fee_adjusted_recipient` because it includes its parent transaction fee. Its
gross refund remains verified from finalized external-message evidence. Any
other recipient mismatch marks that scenario unverified and gives the process a
non-zero exit status.
