# AnonyMus Test Runner

import json
import os
import sys
import time
import unittest
import warnings

if __name__ == "__main__":
    # Add project root to path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, project_root)

    print("Discovering and running all Python tests...")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__))

    captured_warnings = []
    original_showwarning = warnings.showwarning

    def custom_showwarning(message, category, filename, lineno, file=None, line=None):
        warn_data = {
            "message": str(message),
            "category": category.__name__,
            "filename": os.path.relpath(filename, project_root)
            if os.path.isabs(filename)
            else filename,
            "lineno": lineno,
        }
        captured_warnings.append(warn_data)
        original_showwarning(message, category, filename, lineno, file, line)

    warnings.showwarning = custom_showwarning

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Process errors and failures
    errors_list = []
    failures_list = []

    for test_case, tb_str in result.errors:
        errors_list.append(
            {"test": str(test_case), "type": "error", "traceback": tb_str}
        )

    for test_case, tb_str in result.failures:
        failures_list.append(
            {"test": str(test_case), "type": "failure", "traceback": tb_str}
        )

    log_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
        "summary": {
            "total_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "warnings": len(captured_warnings),
            "was_successful": result.wasSuccessful(),
        },
        "failures": failures_list,
        "errors": errors_list,
        "warnings": captured_warnings,
    }

    log_path = os.path.join(project_root, "test_errors.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)

    print(f"\nTest results, warnings, and errors logged to: {log_path}")
    sys.exit(0 if result.wasSuccessful() else 1)
