import os
import sys
import unittest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from transports.p2p.server import validate_nickname


class TestNicknameValidation(unittest.TestCase):
    def test_valid_nicknames(self):
        valid = [
            "Alice",
            "Bob123",
            "User-Name",
            "User_Name",
            "User Name",
            "User(1)",
            "user@domain",
        ]
        for name in valid:
            self.assertEqual(validate_nickname(name), name)

    def test_invalid_nicknames(self):
        invalid = [
            "",  # Empty
            "   ",  # Whitespace only
            "a" * 51,  # Too long
            "<script>alert(1)</script>",  # HTML injection
            "Alice & Bob",  # Invalid chars
            "Bob; DROP TABLE contacts;",  # SQL injection chars
            "Alice\nBob",  # Control chars
        ]
        for name in invalid:
            with self.assertRaises(ValueError):
                validate_nickname(name)


if __name__ == "__main__":
    unittest.main()
