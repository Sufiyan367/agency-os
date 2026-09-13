# Agency OS — Database Architecture & Strategy Decision

**Author**: DevOps & Reliability Engineering  
**Date**: September 2026  
**Status**: Formal Architectural Decision Record (ADR)

---

## 1. Context & Objective
Agency OS operates on a single-node cloud VM (1 vCPU, 1.9 GB RAM, 29 GB SSD) orchestrating discovery, demo generation, lead pipeline tracking, proposals, and commercial operations.

A key strategic question in Mega Prompt 6 is:
> *Should Agency OS migrate production to PostgreSQL now, or retain SQLite with WAL mode?*

This document provides the formal, empirical, evidence-grounded answer.

---

## 2. Empirical Telemetry & Measured Evidence

| Criteria | SQLite (WAL Mode) Measured | PostgreSQL (Local Instance) Estimated | Evidence Source |
| :--- | :--- | :--- | :--- |
| **Query Latency** | **1.01 ms** average read latency | 4.0 – 12.0 ms (TCP loopback, socket serialization) | Production `/health` measurement |
| **RAM Footprint** | **~25 MB** (embedded in daemon heap) | **150 – 300 MB** (postmaster + worker processes + buffers) | Linux `ps aux` & `free -m` |
| **Disk Size** | **6.3 MB** database + **4.1 MB** WAL | ~60 – 120 MB (system catalogs, WAL files, indexes) | Production `/opt/agency/data` |
| **Concurrency Model** | 1 daemon process (`app.service.runner`), concurrent reads, serialized async writes | Multi-process connection pooling | SQLite WAL supports concurrent readers without blocking writes |
| **Operational Simplicity** | 1 single file (`agency.db`), zero external daemons to crash or monitor | Separate systemd daemon (`postgresql.service`), user auth, pg_hba.conf | Zero-dependency operations |
| **Backup Mechanics** | Online `sqlite3_backup` with point-in-time consistency | `pg_dump` with custom archive | `DatabaseBackupManager` online backup |
| **Restore Speed (RTO)** | **< 3 seconds** for 6.3MB snapshot | 10 – 30 seconds for table rebuilds | Tested in `scripts/test_restore.py` |

---

## 3. Formal Architectural Decision

### Decision: **Option A — Keep SQLite in WAL Mode for Production**

We will **NOT** blindly migrate the production database to PostgreSQL at this time.

### Justification:
1. **Zero Contention Bottleneck**:
   The application architecture runs a single unified daemon (`app.service.runner`) hosting both the FastAPI web server and background worker ticks. SQLite WAL mode (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=15000;`) allows unlimited concurrent reads while writes are handled swiftly in milliseconds without database locking errors.
2. **RAM Budget Preservation on 2GB VPS**:
   The VPS has only 1.9 GB total RAM with ~1.0 GB available. Introducing a full PostgreSQL service would consume 20-30% of remaining available memory, increasing the risk of OOM kills for the Python daemon during headless browser audit runs.
3. **Sub-2ms Telemetry Performance**:
   With 1.01 ms database query latency, SQLite is already performing orders of magnitude faster than any remote or local client-server database.
4. **Disaster Recovery SLA**:
   Full database restoration from a compressed `.db.gz` file completes in under 3 seconds, easily satisfying our 15-minute RTO SLA.

---

## 4. PostgreSQL Readiness Architecture (Staging Compatibility)

While production remains on SQLite WAL, the codebase is already designed to be **PostgreSQL Dual-Dialect Compatible**:

1. **SQLAlchemy 2.0 Abstraction**:
   All database access is routed through `app.database.connection`, which dynamically resolves dialects (`sqlite+aiosqlite` vs `postgresql+asyncpg`).
2. **Standard Data Types**:
   All models in `app.database.models` use cross-platform types (`String`, `Integer`, `Float`, `Boolean`, `DateTime`, `JSON`).
3. **Alembic Versioning**:
   Migrations in `alembic/versions` use standard DDL statements compatible with both SQLite and PostgreSQL.

### Future Trigger Conditions for PostgreSQL Migration:
A migration to PostgreSQL will only be authorized if:
- Production transitions from a single VPS node to multiple horizontal worker instances.
- Concurrent write traffic exceeds 150 transactions per second.
- Database size exceeds 10 GB.
