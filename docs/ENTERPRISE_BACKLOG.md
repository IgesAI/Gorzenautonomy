# Enterprise backlog (audit follow-ups)

Separate epics from the functional audit; implement when product priorities require them.

## Multi-tenancy and mission state

- Replace singleton / shared `mission_drafts` with per-session or per-user mission IDs and tenant-scoped storage.
- Concurrency tests: parallel planning sessions must not overwrite each other.

## Parameter overrides and validation

- Fail or warn on unknown keys in `_apply_param_overrides` (envelope API) instead of silently ignoring.
- Optional strict mode for quote workflows.

## Dimensional analysis

- Apply `pint` (or equivalent) at solver boundaries: energy (Wh), speeds, distances, BSFC.

## Quote-first evidence gating

- Tie “quote without flying” to stored validation coverage, model version pins, and error budgets (e.g. endurance error percentiles over similar flight regimes).
- Automate prediction vs validation comparison beyond storing JSON blobs.

## Security and operations

- Harden auth defaults, secrets management, rate limits, and deployment baselines for production.

## ROS bridge

- Dedicated review of lat/lon scaling and AGL semantics vs PX4 uORB / `px4_msgs` for the `gorzen_bridge` path.
