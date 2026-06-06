#!/usr/bin/env python3
"""
AI-DOS: AI Disk Operating System
Entry point. Boots the kernel.

Usage:
    python ai_dos.py                          # Auto-detect: Groq or Ollama
    python ai_dos.py --model llama3.2:3b      # Specific Ollama model
    python ai_dos.py --dry-run                # Simulation mode (no real execution)
    GROQ_API_KEY=gsk_... python ai_dos.py     # Force Groq
"""

import sys
import os

# Ensure we can import kernel modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kernel.engine import run_ai_dos


def main():
    model = "llama3.2:1b"
    dry_run = "--dry-run" in sys.argv

    # Parse --model flag
    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model = sys.argv[idx + 1]

    # Parse --dry-run flag
    if "--dry-run" in sys.argv:
        sys.argv.remove("--dry-run")

    run_ai_dos(model=model, dry_run=dry_run)


if __name__ == "__main__":
    main()
