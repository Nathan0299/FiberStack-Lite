#!/bin/bash

echo "=== FiberStack Sandbox Diagnostics ==="

python3 diagnostics/check_api.py
python3 diagnostics/check_timescale.py
python3 diagnostics/check_elastic.py
python3 diagnostics/check_etl.py
python3 diagnostics/check_probe.py
python3 diagnostics/check_dashboard.py

echo "=== Done ==="
