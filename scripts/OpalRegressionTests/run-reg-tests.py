#!/usr/bin/env python3

"""Compatibility wrapper for the active regression-test runner."""

import runpy
import sys
from pathlib import Path


scripts_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(scripts_dir))
runpy.run_path(str(scripts_dir / "run-reg-tests.py"), run_name="__main__")
