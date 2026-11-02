"""Render the system architecture from its editable source."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("architecture.py")), run_name="__main__")
