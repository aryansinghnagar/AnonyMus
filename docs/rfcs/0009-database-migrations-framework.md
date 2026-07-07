# RFC 0009: Database Migrations Framework and Schema Drift Testing

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

Legacy schema updates relied on manual database table creation scripts. This approach fails to update existing databases when columns or indexes are added in code upgrades, and makes schema evolution verification hard.

## 2. Goals & Non-Goals

### Goals
- Automate database schema evolution using versioned migration files.
- Enable automatic execution of migrations during application startup.
- Prevent schema drift in development using automated tests.

### Non-Goals
- Introducing heavy third-party ORM libraries (like SQLAlchemy or Alembic) to a codebase that relies on raw SQL queries.

## 3. Design Details

The system implements a custom, lightweight SQL-based migration runner in `core/migrations.py`:
1. **Migration Runner:** The helper `run_migrations(conn, migrations_dir)` creates a `schema_migrations` tracking table if it doesn't exist, reads sequentially numbered `.sql` scripts from the target folder, and applies them inside transactions.
2. **Schema Separation:**
   - P2P migrations reside in `transports/p2p/migrations/`
   - Relay migrations reside in `transports/relay/migrations/`
3. **Drift Testing:** The unit test `tests/unit/test_schema_drift.py` loads migrations on in-memory databases, dumps the resulting SQLite schema, normalizes whitespace and statement order, and asserts equality against checked-in reference schemas.

## 4. Security & Privacy Implications

- **Transaction Integrity:** Failing migrations are rolled back automatically, preventing corrupt states.
- **Access Control:** Migration directories are packaged read-only within client binaries to prevent arbitrary SQL injections.

## 5. Backward Compatibility

Baseline schemas are versioned as `0001_baseline` migrations to ensure existing database objects are not overwritten or duplicate-created.
