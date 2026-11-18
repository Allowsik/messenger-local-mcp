import os
import runpy
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
runpy.run_module("messenger_mcp.server", run_name="__main__")
