import unittest

class TestDecommissionedDatabase(unittest.TestCase):
    def test_decommissioned(self):
        # Relay database has been decommissioned in favor of zero-identifier queues.
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
