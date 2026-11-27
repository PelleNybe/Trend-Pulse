"""
Simple test runner script.

You can run this script directly to perform the ForumEngine monitor tests:
    python tests/run_tests.py
"""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent

for _path in (str(TESTS_DIR), str(PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from test_monitor import TestLogMonitor


def main():
    """Run all TestLogMonitor unit tests."""
    print("=" * 60)
    print("ForumEngine Log parsing test")
    print("=" * 60)
    print()

    test_methods = [m for m in dir(TestLogMonitor) if m.startswith("test_")]
    passed = 0
    failed = 0

    for test_method_name in test_methods:
        test_instance = TestLogMonitor()
        if hasattr(test_instance, "setup_method"):
            test_instance.setup_method()
        test_method = getattr(test_instance, test_method_name)
        print(f"Run tests: {test_method_name}...", end=" ")

        try:
            test_method()
            print("✓ pass")
            passed += 1
        except AssertionError as e:
            print(f"✗ fail: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ error: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Test results: {passed} pass, {failed} fail")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
