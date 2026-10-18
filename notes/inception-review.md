# Inception review — consistency check, 18 Oct 2026

Working note (human reference, not agent context).

## Checked
VISION.md, PRD.md, ARCHITECTURE.md, CLAUDE.md and all six diagrams in `diagrams/`, against each other.

## Fixed directly (housekeeping, no scope change)
- VISION OQ4 and OQ5 marked resolved (answered in Navigate); PRD open-questions table and PRD 3.3 sources list updated to match.
- VISION "Stack" constraint updated from "to be decided" to the actual decision, with the revised cost estimate (~$310–480/month including hosting).
- VISION assumptions A6–A10 marked confirmed, since each is written into the approved PRD.
- ARCHITECTURE Section 9: how fixed subscriptions vs metered costs are measured (PRD 3.12 needs both).
- Linear team key changed from TW to PER in CLAUDE.md (AQ2).
- `diagrams/system-architecture.md`: subgraph id fixed for Mermaid compatibility.

## Conflicts needing an Owner decision
| ID | Conflict | Documents | Status |
|---|---|---|---|
| IR1 | Hard stop "liquidity not locked or burned" would wrongly remove established DeFi tokens whose liquidity sits in ordinary open LP pools. Mostly a launch-stage rug check. | PRD 3.4, 3.5, 3.7 | **Resolved (a):** hard stop only for tokens under 72h; older tokens use the liquidity-depth risk factor. PRD 3.4 updated. |
| IR2 | Clerk free plan: no 2FA, sessions fixed at 7 days. PRD 3.1 says 30 days and lockout after 5 attempts / 15 min. | PRD 3.1, ARCHITECTURE AQ1 | **Resolved (a):** stay free; PRD 3.1 now 7-day sessions, Clerk's standard errors, Clerk lockout 5 attempts / 15 min. 2FA added to Future scope before Phase 2. |

## Found while writing tickets
- Spike tickets (PER-15–17) write to `docs/spikes/` and `backend/scripts/`, which were missing from the repository structure. Added to ARCHITECTURE.md Section 3 and CLAUDE.md Section 3.

## Not checked
- Mermaid diagrams were reviewed by hand only; no renderer was available in this session.
