#!/usr/bin/env python3
"""Verify a minisign signature, without needing the minisign binary.

Usage:  verify_minisign.py <file> <file.minisig> <base64 public key>

⚠️ **Why this exists rather than `apt-get install minisign`.** minisign is not
available in the ubuntu-22.04 runner's enabled suites (`E: Unable to locate
package minisign`), and 22.04 is not negotiable as the build host: building
libsodium on a newer glibc produces a shared library that will not load on
older distributions. Installing a prebuilt minisign binary in order to verify a
download only moves the trust problem to a different binary. minisign is
Ed25519, PyNaCl is on every runner, so the check is done directly here.

**Format** (minisign, from its own spec):

    signature file:
        untrusted comment: <text>
        base64( alg[2] || key_id[8] || signature[64] )
        trusted comment: <text>
        base64( global_signature[64] )

    public key:
        untrusted comment: <text>
        base64( alg[2] || key_id[8] || public_key[32] )

`alg` is `Ed` for a signature over the raw file, or `ED` for one over the
BLAKE2b-512 hash of it. libsodium publishes the prehashed (`ED`) form.

⚠️ **Both signatures are checked, and the second one matters.** The global
signature covers `signature || trusted_comment`. Verifying only the first would
leave the trusted comment -- which names the file and version -- unauthenticated
and swappable between releases. Checking one of two signatures and reporting
"verified" is the failure this whole file exists to avoid.

⚠️ **The key id is compared too.** A valid signature from the WRONG key is still
a valid signature; without this check an attacker who supplies both the tarball
and its .minisig passes.

Exit 0 = verified. Any failure raises SystemExit with a reason.
"""
import base64
import hashlib
import sys


def _parse(path, expect_lines):
    with open(path, "rb") as fh:
        lines = [ln.rstrip(b"\r\n") for ln in fh if ln.strip()]
    if len(lines) < expect_lines:
        raise SystemExit(f"FAIL: {path} has {len(lines)} lines, expected >= {expect_lines}")
    return lines


def parse_pubkey(b64_key):
    raw = base64.b64decode(b64_key)
    if len(raw) != 42:
        raise SystemExit(f"FAIL: public key is {len(raw)} bytes, expected 42")
    return raw[:2], raw[2:10], raw[10:]


def parse_sig(path):
    lines = _parse(path, 4)
    sig_raw = base64.b64decode(lines[1])
    if len(sig_raw) != 74:
        raise SystemExit(f"FAIL: signature line is {len(sig_raw)} bytes, expected 74")
    alg, key_id, signature = sig_raw[:2], sig_raw[2:10], sig_raw[10:]

    trusted_prefix = b"trusted comment: "
    if not lines[2].startswith(trusted_prefix):
        raise SystemExit("FAIL: no trusted comment line in the signature file")
    trusted_comment = lines[2][len(trusted_prefix):]

    global_sig = base64.b64decode(lines[3])
    if len(global_sig) != 64:
        raise SystemExit(f"FAIL: global signature is {len(global_sig)} bytes, expected 64")
    return alg, key_id, signature, trusted_comment, global_sig


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: verify_minisign.py <file> <file.minisig> <b64 pubkey>")
    target, sigfile, b64_key = sys.argv[1:4]

    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except ImportError:
        raise SystemExit("FAIL: PyNaCl is required (pip install pynacl)")

    key_alg, key_id, pubkey = parse_pubkey(b64_key)
    alg, sig_key_id, signature, trusted_comment, global_sig = parse_sig(sigfile)

    # A valid signature from the wrong key is still a valid signature.
    if sig_key_id != key_id:
        raise SystemExit(
            f"FAIL: signature key id {sig_key_id.hex()} does not match "
            f"the pinned public key id {key_id.hex()}"
        )

    with open(target, "rb") as fh:
        data = fh.read()

    if alg == b"ED":
        message = hashlib.blake2b(data, digest_size=64).digest()
        mode = "prehashed (BLAKE2b-512)"
    elif alg == b"Ed":
        message = data
        mode = "raw"
    else:
        raise SystemExit(f"FAIL: unknown signature algorithm {alg!r}")

    verifier = VerifyKey(pubkey)
    try:
        verifier.verify(message, signature)
    except BadSignatureError:
        raise SystemExit("FAIL: the file signature does NOT verify")

    # Covers signature || trusted_comment. Skipping this would leave the
    # trusted comment unauthenticated and swappable between releases.
    try:
        verifier.verify(signature + trusted_comment, global_sig)
    except BadSignatureError:
        raise SystemExit("FAIL: the GLOBAL signature (trusted comment) does NOT verify")

    print(f"minisign : VERIFIED  [{mode}]")
    print(f"key id   : {key_id.hex()}")
    print(f"trusted  : {trusted_comment.decode('utf-8', 'replace')}")
    print(f"sha256   : {hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
