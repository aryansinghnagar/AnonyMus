import eventlet
# Apply monkey patching before any other imports to avoid late-patching proxy errors in Flask/Werkzeug
eventlet.monkey_patch()

import os
import sys
import unittest

if __name__ == '__main__':
    # Add project root to path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, project_root)
    
    print("Discovering and running all Python tests...")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
