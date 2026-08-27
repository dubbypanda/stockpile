#!/usr/bin/env python3
"""Launch the positions console:

    uv run streamlit run positions/run_console.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from console_app import main

main()
