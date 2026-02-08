"""CLI entry point for the Reseller Tool."""

import subprocess
import sys


def main():
    """Launch the Streamlit dashboard."""
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "src/reseller_tool/app.py"],
        check=True,
    )


if __name__ == "__main__":
    main()
