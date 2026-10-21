"""Make the package importable straight from a checkout, no install required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
