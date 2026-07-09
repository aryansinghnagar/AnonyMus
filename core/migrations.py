import os


def run_migrations(conn, migrations_dir):
    """
    Thread-safe SQL migration runner.
    Applies sequentially numbered .sql migration files in the target directory.
    """
    cursor = conn.cursor()

    # 1. Create schema_migrations tracker table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    if not os.path.exists(migrations_dir):
        return

    # 2. Collect and sort all .sql files
    migration_files = sorted(
        [f for f in os.listdir(migrations_dir) if f.endswith(".sql")]
    )

    for filename in migration_files:
        # Check if migration was already applied
        cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (filename,))
        if cursor.fetchone():
            continue

        print(f"[Migrations] Applying schema migration: {filename}")
        filepath = os.path.join(migrations_dir, filename)
        with open(filepath, encoding="utf-8") as f:
            sql_content = f.read()

        # 3. Apply the migration within a transaction
        try:
            if hasattr(conn, "executescript"):
                conn.executescript(sql_content)
            else:
                cursor.execute(sql_content)

            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (filename,)
            )
            conn.commit()
            print(f"[Migrations] Successfully applied: {filename}")
        except Exception as e:
            conn.rollback()
            print(f"[Migrations] FATAL: Failed to apply {filename}: {e}")
            raise e
