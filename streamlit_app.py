"""Streamlit Cloud entry point."""
import sys
from pathlib import Path

import streamlit as st

# Add src/ to path so reseller_tool package is importable
sys.path.append(str(Path(__file__).parent / "src"))

# Import runs all Streamlit code at module level
try:
    import reseller_tool.app
except ImportError as e:
    st.error(f"Failed to import app: {e}")
