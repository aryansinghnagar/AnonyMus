import os
import re
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.migrations import run_migrations


def normalize_statement(stmt):
    stmt = stmt.strip()
    stmt = re.sub(r"\s+", " ", stmt)
    stmt = re.sub(r"\s*([(),;])\s*", r"\1", stmt)
    return stmt.lower()


class TestSchemaDrift(unittest.TestCase):
    def test_p2p_schema_drift(self):
        # 1. Run P2P migrations on fresh in-memory database
        conn = sqlite3.connect(":memory:")
        migrations_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "..", "transports", "p2p", "migrations"
            )
        )
        run_migrations(conn, migrations_dir)

        # 2. Dump statements from sqlite_master
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
        )
        actual_statements = [row[0] for row in cursor.fetchall()]
        conn.close()

        # 3. Read and split checked-in canonical schema
        schema_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "schema_p2p.sql")
        )
        with open(schema_file, encoding="utf-8") as f:
            expected_statements = f.read().split(";")

        actual_normalized = sorted(
            [normalize_statement(s) for s in actual_statements if s.strip()]
        )
        expected_normalized = sorted(
            [normalize_statement(s) for s in expected_statements if s.strip()]
        )

        self.assertEqual(
            actual_normalized,
            expected_normalized,
            "P2P Schema drift detected! Checked-in schema does not match migrations.",
        )

    def test_relay_schema_drift(self):
        # 1. Run Relay migrations on fresh in-memory database
        conn = sqlite3.connect(":memory:")
        migrations_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "transports",
                "relay",
                "migrations",
            )
        )
        run_migrations(conn, migrations_dir)

        # 2. Dump statements
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
        )
        actual_statements = [row[0] for row in cursor.fetchall()]
        conn.close()

        # 3. Read and split checked-in canonical schema
        schema_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "schema_relay.sql")
        )
        with open(schema_file, encoding="utf-8") as f:
            expected_statements = f.read().split(";")

        actual_normalized = sorted(
            [normalize_statement(s) for s in actual_statements if s.strip()]
        )
        expected_normalized = sorted(
            [normalize_statement(s) for s in expected_statements if s.strip()]
        )

        self.assertEqual(
            actual_normalized,
            expected_normalized,
            "Relay Schema drift detected! Checked-in schema does not match migrations.",
        )


if __name__ == "__main__":
    unittest.main()
