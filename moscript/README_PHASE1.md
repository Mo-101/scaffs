# Scaffs Hybrid Portfolio Allocator — Phase 1 MoScripts

Purpose: standardize proposals from Idim Ikang, Scaffs Picker, Grid Futures and
Morning Glory; persist them; and build engine-specific shadow accounting.

## Safety invariant

**Phase 1 does not change live/paper allocation.**
Every proposal is marked `shadow_only=true` and the router writes
`SHADOW_ONLY`. Do not wire allocator execution until Phase 2/3 validation.

## Install

From the Scaffs repository root:

```bash
cp -R backend/agent/src/trading/hybrid <repo>/backend/agent/src/trading/
cp backend/agent/tests/test_hybrid_phase1.py <repo>/backend/agent/tests/
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_hybrid_phase1.sql
```

Adapt the DB connection factory to Scaffs' existing `resolve_dsn()` helper.

## Engine integration points

Wrap existing engine output; do not rewrite strategy logic in Phase 1:

```python
proposal = from_idim(
    native_signal,
    strategy_version=STRATEGY_VERSION,
    git_sha=GIT_SHA,
)
router.submit(proposal)
```

Equivalent adapters exist for Picker, Grid and Morning Glory.

### Do not route Equal-Weight Rebalance through the alpha allocator

Rebalancing is portfolio-management/risk logic, not an alpha proposal family.

## Required next wiring

1. Call the adapter immediately after each engine creates a candidate proposal.
2. Persist proposals before any allocator/risk decision.
3. Feed rejected proposals to the existing counterfactual price-marker so
   `shadow_engine_performance` resolves TP/SL/TIME.
4. Preserve current execution path unchanged.
5. Store exact image/git provenance for every proposal.
6. Once each family has enough resolved proposals, calibrate reliability,
   regime performance and inter-engine correlation chronologically.

## Phase 1 acceptance

- all four alpha engines emit a common proposal model;
- producer retries cannot create duplicates;
- all proposals have version/SHA/timestamps;
- rejected proposals resolve in the shadow ledger;
- current execution behavior is unchanged;
- scoreboard can group PF/expectancy/win-rate/MFE/MAE by engine and regime.

## Why no N-AHP / Grey / TOPSIS yet?

Those become portfolio-level allocation methods only after shadow history shows
which engines have empirical edge and in which regimes. The ranking layer should
combine validated evidence; it must not compensate for unvalidated engines.
