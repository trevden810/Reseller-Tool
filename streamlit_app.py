"""Streamlit Cloud entry point."""
import sys
from pathlib import Path

# Add src/ to path so reseller_tool package is importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Re-export the full app
from reseller_tool.app import *  # noqa: F401, F403
