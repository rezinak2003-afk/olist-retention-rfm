#!/usr/bin/env python
"""Run the complete Olist retention/RFM pipeline from the project root."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.olist_analysis import main  # noqa: E402

if __name__ == "__main__":
    main()
