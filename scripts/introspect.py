#!/usr/bin/env python3
"""Entry point script for running the full introspection pipeline.

Usage:
    python scripts/introspect.py
"""

import sys
from pathlib import Path

# Ensure the package is importable when running from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes_introspection import main

if __name__ == "__main__":
    main()