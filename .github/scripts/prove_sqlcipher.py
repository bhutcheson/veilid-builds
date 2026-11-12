#!/usr/bin/env python3
"""Prove an INSTALLED sqlcipher3 wheel is the build lock.json describes, and that it encrypts.

Usage:  <venv>/bin/python prove_sqlcipher.py <lock.json>

Run it with the interpreter of a fresh venv into which the wheel under test, and nothing else, was installed. It is the
Windows and macOS import gate of RULINGS 248 as well as the Linux one: every job runs it on the runner that built the wheel.

What it asserts, in order:

1. The extension that imports is the venv's own (under sys.prefix), and the package holds exactly one extension module.
2. The versions are the lock's: SQLite, SQLCipher (community), the provider (openssl), and the provider's RUNTIME version
   (`PRAGMA cipher_provider_version` asks the linked library, so it names the OpenSSL that actually runs).
3. The extension names no shared OpenSSL library, so nothing on the host can stand in for the static one.
4. A database opened with a raw key has no plaintext header, and `PRAGMA cipher_status` says the handle encrypts.
5. Python's own sqlite3 refuses the file, and so does a wrong key.
6. NEGATIVE CONTROL: one flipped byte inside an encrypted page is refused (the page HMAC), rather than read back.
7. The right key reads back what was written.
8. The connection has no `enable_load_extension` (the build defines SQLITE_OMIT_LOAD_EXTENSION).

Step 6 is what makes the rest mean something: steps 4, 5 and 7 all pass against a build that "encrypts" with no
authentication. If you ever simplify this script, keep the negative control.

Exit 0 = PASS. Any failure raises and the job fails.
"""
import json
import os
import sqlite3
import sys
import tempfile

RAW_KEY = "x'" + "2b" * 32 + "'"
WRONG_KEY = "x'" + "2c" * 32 + "'"
SHARED_OPENSSL_NAMES = (b"libcrypto.so", b"libssl.so", b"libcrypto.3.dylib", b"libssl.3.dylib",
                        b"libcrypto-3", b"libssl-3", b"libcrypto.dll", b"libeay32")


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    print(f"ok   {what}")


def one(conn, sql):
    row = conn.execute(sql).fetchone()
    return row[0] if row else None


def main(lock_path):
    with open(lock_path) as f:
        lock = json.load(f)
    import sqlcipher3._sqlite3 as _ext
    from sqlcipher3 import dbapi2

    ext = os.path.realpath(_ext.__file__)
    check(ext.startswith(os.path.realpath(sys.prefix) + os.sep), f"the extension is the venv's own: {ext}")
    pkg = os.path.dirname(ext)
    exts = [f for f in os.listdir(pkg) if f.endswith((".so", ".pyd", ".dylib"))]
    check(len(exts) == 1, f"exactly one extension module in the package: {exts}")

    with open(ext, "rb") as f:
        blob = f.read()
    named = [n.decode() for n in SHARED_OPENSSL_NAMES if n in blob]
    check(not named, f"the extension names no shared OpenSSL library: {named}")

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "probe.db")
        conn = dbapi2.connect(path)
        conn.execute(f'PRAGMA key = "{RAW_KEY}"')
        check(one(conn, "SELECT sqlite_version()") == lock["sqlcipher"]["sqlite_version"],
              f"SQLite is {lock['sqlcipher']['sqlite_version']}: {one(conn, 'SELECT sqlite_version()')}")
        version = one(conn, "PRAGMA cipher_version")
        check(version == f"{lock['sqlcipher']['version']} community",
              f"SQLCipher is {lock['sqlcipher']['version']} community: {version}")
        check(one(conn, "PRAGMA cipher_provider") == "openssl",
              f"the provider is openssl: {one(conn, 'PRAGMA cipher_provider')}")
        provider = one(conn, "PRAGMA cipher_provider_version") or ""
        check(provider.startswith(f"OpenSSL {lock['openssl']['version']} "),
              f"the provider runs OpenSSL {lock['openssl']['version']}: {provider}")
        check(one(conn, "PRAGMA cipher_status") == "1", "PRAGMA cipher_status says this handle encrypts")
        check(not hasattr(conn, "enable_load_extension"), "the connection has no enable_load_extension")
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.executemany("INSERT INTO t VALUES (?)", [(f"row {i} " + "y" * 200,) for i in range(200)])
        conn.commit()
        conn.close()

        with open(path, "rb") as f:
            raw = f.read()
        check(not raw.startswith(b"SQLite format 3\x00"), "the file has no plaintext SQLite header")
        check(b"row 1 yyyy" not in raw, "the rows are not in the file in plaintext")

        # 🔴 Every connection is closed in a `finally`: Windows will not delete a file a handle still holds, so a leak fails the
        # TemporaryDirectory cleanup (run 43164498626: this stdlib connection was never closed). Do not paper over it with
        # ignore_cleanup_errors; a handle left open is worth knowing about.
        plain = sqlite3.connect(path)
        try:
            plain.execute("SELECT count(*) FROM sqlite_master").fetchone()
            refused = False
        except sqlite3.DatabaseError:
            refused = True
        finally:
            plain.close()
        check(refused, "Python's own sqlite3 refuses the file")

        wrong = dbapi2.connect(path)
        wrong.execute(f'PRAGMA key = "{WRONG_KEY}"')
        try:
            wrong.execute("SELECT count(*) FROM sqlite_master").fetchone()
            refused = False
        except dbapi2.DatabaseError:
            refused = True
        finally:
            wrong.close()
        check(refused, "a wrong key is refused")

        right = dbapi2.connect(path)
        try:
            right.execute(f'PRAGMA key = "{RAW_KEY}"')
            rows = one(right, "SELECT count(*) FROM t")
            page = int(one(right, "PRAGMA cipher_page_size"))
        finally:
            right.close()
        check(rows == 200, "the right key reads back the 200 rows")

        tampered = bytearray(raw)
        tampered[page + page // 2] ^= 0x01                       # one bit in the middle of page 2's ciphertext
        bad = os.path.join(tmp, "tampered.db")
        with open(bad, "wb") as f:
            f.write(bytes(tampered))
        conn = dbapi2.connect(bad)
        conn.execute(f'PRAGMA key = "{RAW_KEY}"')
        try:
            conn.execute("SELECT count(*), max(length(v)) FROM t").fetchone()
            refused = False
        except dbapi2.DatabaseError:
            refused = True
        finally:
            conn.close()
        check(refused, "NEGATIVE CONTROL: a flipped bit in an encrypted page is refused (HMAC)")

        # no-autoload-config, proven rather than assumed: an openssl.cnf that activates ONLY the null provider would leave
        # OpenSSL with no AES and no HMAC if the library read it, so the keyed open below would fail. Built with
        # no-autoload-config it never reads one, wherever OPENSSL_CONF points. (A build with the default, which reads it, fails
        # here: measured on the PyPI 0.5.7 wheel.)
        conf = os.path.join(tmp, "planted.cnf")
        with open(conf, "w") as f:
            f.write("openssl_conf = init\n[init]\nproviders = prov\n[prov]\nnull = null_sect\n"
                    "[null_sect]\nactivate = 1\n")
        child = ("import sys; from sqlcipher3 import dbapi2; c = dbapi2.connect(sys.argv[1]); "
                 "c.execute('PRAGMA key = \"' + sys.argv[2] + '\"'); print(c.execute('SELECT count(*) FROM t').fetchone()[0])")
        import subprocess
        env = dict(os.environ, OPENSSL_CONF=conf)
        run = subprocess.run([sys.executable, "-I", "-c", child, path, RAW_KEY], env=env, capture_output=True, text=True)
        check(run.returncode == 0 and run.stdout.strip() == "200",
              f"an openssl.cnf planted through OPENSSL_CONF is never read (no-autoload-config): rc={run.returncode} "
              f"out={run.stdout.strip()!r} err={run.stderr.strip()[-200:]!r}")
    print("PASS")


if __name__ == "__main__":
    main(sys.argv[1])
