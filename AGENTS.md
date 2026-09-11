# Engineering & Audit Guidelines for Jainune

## 1. Core Mandate: Logical Correctness & Application Domain Security

Standard vulnerability scanners (Bandit, Trivy, Semgrep) and slash commands (`/goal`, `/grill-me`, automated scaffolding) only verify generic syntax, known CVEs, and mock-based unit tests. They **do not** catch application-specific logical bugs or domain state divergence.

### The Mock Illusion
Unit tests using `MagicMock` or mock databases will pass even when:
- SQL column aliases or names are wrong (`user_a` vs `user_a_id`).
- PostgreSQL transactions contain commands forbidden inside transaction blocks (e.g. `REINDEX CONCURRENTLY`).
- Unique constraints are missing on junction tables.
- Row-level security (RLS) policies prevent legitimate application reads.

**Always verify database logic against the actual migrations and PostgreSQL schema.**

---

## 2. Distinction: Slash Commands vs Logical Audits

- **Slash Commands & Scaffolding Skills**: Optimize for feature velocity, boilerplate scaffolding, and happy paths.
- **Logical Correctness Audit**: Adversarially inspects state machines, boundary failure modes, and downstream consequences.

---

## 3. Mandatory Audit Dimensions for Any Changes

1. **State Divergence**: If an entity status changes (e.g., account suspended, subscription expired), verify all dependent metrics (trust scores, daily limits, super connect credits, feed visibility) update atomically.
2. **Concurrency & TOCTOU**: Always execute validation checks (block lists, participant checks, expiration) and mutations inside the **same database connection and transaction**.
3. **Blast Radius of Fixes**: Never introduce security protections that lock out legitimate users (e.g., multi-device logins must not be flagged as token reuse theft).
4. **Cross-Datastore Order**: Never delete cache/buffers (Redis) before database persistence succeeds.
5. **Client Protocol Resilience**: Ensure reconnection backoff counters zero on screen/chat room switch; map vendor SDK lifecycle states (e.g., Apple StoreKit `DEFERRED` Ask-to-Buy states) to non-blocking UI states.
6. **Worker Isolation**: Ensure Celery Beat runs in a dedicated container with a persistent schedule volume to avoid missed or duplicate tasks on restart.
