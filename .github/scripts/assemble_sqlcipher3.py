#!/usr/bin/env python3
"""Assemble the sqlcipher3 build tree from VERIFIED inputs only.

Usage:  assemble_sqlcipher3.py <lock.json> <sources dir> <tree out>

<sources dir> holds what the `sources` job fetched and verified: the binding's sdist and the SQLCipher amalgamation
(sqlite3.c, sqlite3.h). Each is checked again here against lock.json's sha256, because it crossed a job boundary as an
artifact. The tree is the sdist's binding sources (src/*.c, src/*.h, sqlcipher3/, LICENSE) with the amalgamation replaced
and the build files replaced by .github/sqlcipher3/{setup.py,pyproject.toml}.

The sdist is extracted with tarfile's "data" filter: no absolute paths, no "..", no links out of the tree, no device files
(the NEW-02 class: an unsanitised extractall on a downloaded archive).
"""
import hashlib
import json
import os
import shutil
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verified(path, want):
    got = sha256(path)
    if got != want:
        raise SystemExit(f"FAIL: {path} has sha256 {got}, the lock says {want}")
    print(f"ok   {os.path.basename(path)} {got}")
    return path


def main(lock_path, sources, out):
    lock = json.load(open(lock_path))
    b = lock["binding"]
    sdist = verified(os.path.join(sources, os.path.basename(b["sdist_url"])), b["sdist_sha256"])
    amalg = {n: verified(os.path.join(sources, n), h) for n, h in lock["sqlcipher"]["amalgamation_sha256"].items()}
    if os.path.exists(out):
        raise SystemExit(f"FAIL: {out} exists; the tree is assembled fresh")
    staging = out + ".sdist"
    with tarfile.open(sdist) as tf:
        tf.extractall(staging, filter="data")
    (top,) = os.listdir(staging)
    root = os.path.join(staging, top)
    os.makedirs(os.path.join(out, "src", "sqlcipher"))
    for name in sorted(os.listdir(os.path.join(root, "src"))):
        if name.endswith((".c", ".h")):
            shutil.copy2(os.path.join(root, "src", name), os.path.join(out, "src", name))
    shutil.copytree(os.path.join(root, "sqlcipher3"), os.path.join(out, "sqlcipher3"))
    shutil.copy2(os.path.join(root, "LICENSE"), os.path.join(out, "LICENSE"))
    for name, path in amalg.items():
        shutil.copy2(path, os.path.join(out, "src", "sqlcipher", name))
    for name in ("setup.py", "pyproject.toml"):
        shutil.copy2(os.path.join(HERE, "..", "sqlcipher3", name), os.path.join(out, name))
    shutil.rmtree(staging)
    print(f"assembled {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
