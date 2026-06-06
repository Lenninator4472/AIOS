#!/usr/bin/env python3
"""
AI-DOS: AI Disk Operating System
Entry point. Boots the kernel.

Usage:
    python ai_dos.py                  # Default model (llama3.2:1b)
"""

import sys
import os

# Ensure we can import kernel modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kernel.engine import run_ai_dos


def main():
    model = "llama3.2:1b"

    # Parse --model flag
    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model = sys.argv[idx + 1]

    # Future: hardware detection, memory store initialization,
    # filesystem indexing, driver loading goes here.
    run_ai_dos(model=model)


if __name__ == "__main__":
    main()
