#!/usr/bin/env python3
"""Print one value of .github/sqlcipher3/lock.json:  lock.py openssl.sha256   (a list prints space-separated)."""
import json
import os
import sys

value = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sqlcipher3", "lock.json")))
for part in sys.argv[1].split("."):
    value = value[part]
print(" ".join(value) if isinstance(value, list) else value)
