#!/usr/bin/env python3
"""
Quick test runner that skips slow Docker integration tests.

Usage:
    python scripts/test_quick.py              # Run all fast tests
    python scripts/test_quick.py --verbose    # Run with verbose output
    python scripts/test_quick.py --coverage   # Run with coverage report
    python scripts/test_quick.py test_api     # Run specific test file
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run pytest with optimized settings for quick testing."""

    # Base pytest command
    cmd = [sys.executable, "-m", "pytest"]

    # Skip slow tests
    cmd.extend(["-m", "not slow and not docker"])

    # Ignore the integration test file
    cmd.extend(["--ignore", "tests/test_sandbox_integration.py"])

    # Add common options
    cmd.extend([
        "--tb=short",
        "--color=yes",
    ])

    # Check for additional arguments
    if "--verbose" in sys.argv or "-v" in sys.argv:
        cmd.append("-v")
        sys.argv = [arg for arg in sys.argv if arg not in ["--verbose", "-v"]]

    if "--coverage" in sys.argv:
        cmd.extend([
            "--cov=server",
            "--cov-report=term-missing",
            "--cov-report=html"
        ])
        sys.argv.remove("--coverage")

    # Add any remaining arguments (like specific test files)
    if len(sys.argv) > 1:
        # If specific test file provided, add it
        test_target = sys.argv[1]
        if not test_target.startswith("-"):
            if not test_target.startswith("tests/"):
                test_target = f"tests/{test_target}"
            if not test_target.endswith(".py"):
                test_target = f"{test_target}.py"
            cmd.append(test_target)
    else:
        # Default to all tests
        cmd.append("tests/")

    # Show what we're running
    print("Running quick tests (skipping slow Docker tests)...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 50)

    # Run the tests
    result = subprocess.run(cmd)

    # Exit with the same code as pytest
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()