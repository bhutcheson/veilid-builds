#!/usr/bin/env python3
"""Prove a freshly built libsodium actually works, before it is released.

Usage:  prove_libsodium.py <dir containing the library>

⚠️ **A file that exists is not evidence that it works, and a successful library
lookup is not evidence that YOUR file was loaded.** D16's original probe
reported a false pass by resolving the *system* libsodium instead of the staged
copy, and it was only caught by reading the actually-mapped path. This script
avoids that class entirely by loading the artifact **by absolute path**, so
either that exact file loads or the call fails -- there is no search path for it
to fall through to.

What it asserts, in order:

1. Exactly one candidate library is present in the directory.
2. ``ctypes.CDLL(<absolute path>)`` succeeds.
3. ``sodium_init()`` returns >= 0 (0 = initialised, 1 = already initialised).
4. ``sodium_version_string()`` is readable and non-empty.
5. A real ``crypto_sign_keypair`` / ``crypto_sign_detached`` /
   ``crypto_sign_verify_detached`` round trip succeeds.
6. Verification **fails** on a tampered signature.

⚠️ Step 6 is the one that makes the rest mean something. Steps 3-5 can all pass
against a stub that returns 0 from everything; a library that "verifies"
a corrupted signature is worse than one that does not load, because it fails
open. If you ever simplify this script, keep the negative control.

Exit 0 = PASS. Any failure raises and the job fails.
"""
import ctypes
import json
import os
import sys

CANDIDATES = ("libsodium.so.23", "libsodium.dylib", "libsodium.dll")


def find_library_file(directory):
    """Exactly one candidate, or fail loudly.

    Zero means the package step is broken. Two or more means we cannot say
    which one the installer would load, and guessing here would be the same
    ambiguity the loader has at runtime.
    """
    found = []
    for entry in sorted(os.listdir(directory)):
        if entry in CANDIDATES or entry.startswith("libsodium.so."):
            found.append(os.path.join(directory, entry))
    if not found:
        raise SystemExit(
            f"FAIL: no libsodium library in {directory}. "
            f"Expected one of {CANDIDATES}. Present: {sorted(os.listdir(directory))}"
        )
    if len(found) > 1:
        raise SystemExit(f"FAIL: more than one candidate library: {found}")
    return found[0]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: prove_libsodium.py <dir>")
    directory = sys.argv[1]

    path = find_library_file(directory)
    print(f"artifact  : {path}")
    print(f"size      : {os.path.getsize(path)} bytes")

    info_path = os.path.join(directory, "BUILD_INFO.json")
    if os.path.exists(info_path):
        with open(info_path) as fh:
            info = json.load(fh)
        print(f"build info: {info.get('platform')} "
              f"v{info.get('version')} "
              f"(source verified: {info.get('signature_verified')})")

    # ABSOLUTE path -- this file or nothing. No find_library, no search path,
    # so a pass cannot be the system copy wearing our name.
    lib = ctypes.CDLL(os.path.abspath(path))
    print("loaded    : OK (by absolute path, so attribution is not in question)")

    if lib.sodium_init() < 0:
        raise SystemExit("FAIL: sodium_init() < 0")

    lib.sodium_version_string.restype = ctypes.c_char_p
    version = lib.sodium_version_string().decode()
    if not version:
        raise SystemExit("FAIL: empty sodium_version_string()")
    print(f"sodium    : {version}")

    # --- real crypto, not just symbol presence ------------------------------
    pk = ctypes.create_string_buffer(32)
    sk = ctypes.create_string_buffer(64)
    if lib.crypto_sign_keypair(pk, sk) != 0:
        raise SystemExit("FAIL: crypto_sign_keypair")

    message = b"kunuleco K-1 libsodium proof"
    sig = ctypes.create_string_buffer(64)
    siglen = ctypes.c_ulonglong(0)
    if lib.crypto_sign_detached(sig, ctypes.byref(siglen), message,
                                ctypes.c_ulonglong(len(message)), sk) != 0:
        raise SystemExit("FAIL: crypto_sign_detached")

    if lib.crypto_sign_verify_detached(sig, message,
                                       ctypes.c_ulonglong(len(message)), pk) != 0:
        raise SystemExit("FAIL: a valid signature did not verify")
    print(f"sign/verify: OK ({siglen.value}-byte signature)")

    # --- NEGATIVE CONTROL: this is what makes the above meaningful ----------
    tampered = bytearray(sig.raw[:64])
    tampered[0] ^= 0xFF
    bad = ctypes.create_string_buffer(bytes(tampered), 64)
    if lib.crypto_sign_verify_detached(bad, message,
                                       ctypes.c_ulonglong(len(message)), pk) == 0:
        raise SystemExit(
            "FAIL: a TAMPERED signature verified. This library fails open and "
            "must not ship -- every check above would pass against a stub too."
        )
    print("negative  : OK (tampered signature correctly rejected)")

    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
