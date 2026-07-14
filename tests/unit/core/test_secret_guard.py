import os
import sys
import unittest

try:
    import eventlet.patcher

    subprocess = eventlet.patcher.original("subprocess")
except (ImportError, AttributeError):
    import subprocess

# Ensure project root is in path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)


class TestSecretGuard(unittest.TestCase):
    def test_placeholder_secrets(self):
        placeholders = [
            "your-secure-random-key-here",
            "diagnostics_ephemeral_control_key_2026",
            "changeme",
            "",
        ]

        import tempfile

        for placeholder in placeholders:
            env = os.environ.copy()
            env["ANONYMUS_PQ_DISABLE"] = "1"
            env["FLASK_SECRET_KEY"] = placeholder
            env["SECRET_KEY"] = placeholder

            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as tmp:
                res = subprocess.run(
                    [sys.executable, "-c", "import server"],
                    env=env,
                    stdout=tmp,
                    stderr=tmp,
                )
                tmp.seek(0)
                output = tmp.read()

            self.assertNotEqual(
                res.returncode,
                0,
                f"Server booted successfully with placeholder: '{placeholder}'",
            )
            self.assertIn(
                "Refusing to start: FLASK_SECRET_KEY is missing, empty, or a known placeholder.",
                output,
            )


if __name__ == "__main__":
    unittest.main()
