"""
conftest.py

Pytest configuration. Adds project root to sys.path so src modules are importable.
"""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))
