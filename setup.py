#!/usr/bin/env python
from parcyl import setup

setup(py_modules=["parcyl"], entry_points={"console_scripts": ["parcyl = parcyl:_main"]})
