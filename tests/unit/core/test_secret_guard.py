import os
import unittest
import sys
import subprocess

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

class TestSecretGuard(unittest.TestCase):
    def test_placeholder_secrets(self):
        placeholders = [
            "your-secure-random-key-here",
            "diagnostics_ephemeral_control_key_2026",
            "changeme",
            ""
        ]
        
        for placeholder in placeholders:
            env = os.environ.copy()
            env["FLASK_SECRET_KEY"] = placeholder
            res = subprocess.run(
                [sys.executable, "-c", "import server"],
                env=env,
                capture_output=True,
                text=True
            )
            self.assertNotEqual(res.returncode, 0, f"Server booted successfully with placeholder: '{placeholder}'")
            self.assertIn("Refusing to start: FLASK_SECRET_KEY is missing, empty, or a known placeholder.", res.stderr)

if __name__ == '__main__':
    unittest.main()
