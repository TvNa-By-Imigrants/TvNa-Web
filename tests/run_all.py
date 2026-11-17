#!/usr/bin/env python3
"""Run every offline check (tests/test_stage*.py: no internet, no Gemini) and print one total.
Exits 1 if any check fails or a test file crashes.

Usage:
    python tests/run_all.py
"""
import re
import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SUMMARY = re.compile(r"^(\d+)/(\d+) passed$", re.M)
CRASH_LINES = 15
TIME_LIMIT = 300  # seconds per test file; a hung file is reported instead of blocking the rest


def main():
    files = sorted(TESTS_DIR.glob("test_stage*.py"))
    if not files:
        sys.exit(f"No test files found in {TESTS_DIR}.")
    passed_all = checks_all = 0
    bad = []
    for path in files:
        start = time.monotonic()
        try:
            result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=TIME_LIMIT)
        except subprocess.TimeoutExpired:
            print(f"{path.name:<18} TIMED OUT after {TIME_LIMIT} s")
            bad.append(path.name)
            continue
        seconds = time.monotonic() - start
        found = SUMMARY.findall(result.stdout)
        passed, checks = map(int, found[-1]) if found else (0, 0)
        passed_all, checks_all = passed_all + passed, checks_all + checks

        if found and result.returncode == 0 and passed == checks:
            print(f"{path.name:<18} {passed}/{checks} passed ({seconds:.1f} s)")
            continue
        bad.append(path.name)
        if not found:
            print(f"{path.name:<18} CRASHED (exit code {result.returncode}):")
            for line in (result.stderr or result.stdout).strip().splitlines()[-CRASH_LINES:]:
                print(f"    {line}")
            continue
        print(f"{path.name:<18} {passed}/{checks} passed, {checks - passed} FAILED ({seconds:.1f} s):")
        failing = False
        for line in result.stdout.splitlines():
            if line.startswith(("PASS ", "FAIL ")) or not line.strip():
                failing = line.startswith("FAIL ")
            if failing:
                print(f"    {line}")

    print(f"\nTotal: {passed_all}/{checks_all} passed in {len(files)} files"
          + (f". Fix: {', '.join(bad)}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
