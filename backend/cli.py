#!/usr/bin/python3
"""Dock Panel CLI 入口。由 Cockpit 通过 cockpit.spawn 调用。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
