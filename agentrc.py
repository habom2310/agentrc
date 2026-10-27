#!/usr/bin/env python3
"""
agentrc runner script
"""
import sys
from pathlib import Path

# Add src and script directory to sys.path
bin_dir = Path(__file__).resolve().parent
src_dir = bin_dir / "src"
if src_dir.is_dir() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(bin_dir) not in sys.path:
    sys.path.insert(0, str(bin_dir))

from agentrc.cli import main

if __name__ == "__main__":
    main()
