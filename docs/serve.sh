#!/bin/bash
cd "$(dirname "$0")"
python3 -m http.server "${PORT:-8765}"
