# setup.py for the project's own sqlcipher3 wheel (RULINGS 248). It REPLACES the sdist's setup.py, which runs
# `conan remote update` and `conan install -b missing` (so the published wheels carry ConanCenter's prebuilt OpenSSL).
# Here OpenSSL is the static build the workflow made from the signature-verified tarball, at $OPENSSL_PREFIX.
#
# Kept from the sdist's setup.py 0.5.7: the sources (src/*.c + src/sqlcipher/sqlite3.c) and every define, except one:
#   SQLITE_ENABLE_LOAD_EXTENSION=1 is dropped and SQLITE_OMIT_LOAD_EXTENSION is defined, so the library cannot load an
#   extension and the binding compiles no enable_load_extension (connection.c guards it on SQLITE_OMIT_LOAD_EXTENSION).
#   The node never loads one; this removes the capability rather than relying on it staying off.
import os
import sys
from glob import glob

from setuptools import Extension, setup

prefix = os.environ["OPENSSL_PREFIX"]
version = os.environ["WHEEL_VERSION"]

define_macros = [
    ("MODULE_NAME", '"sqlcipher3.dbapi2"'),
    ("SQLITE_ENABLE_FTS3", "1"),
    ("SQLITE_ENABLE_FTS3_PARENTHESIS", "1"),
    ("SQLITE_ENABLE_FTS4", "1"),
    ("SQLITE_ENABLE_FTS5", "1"),
    ("SQLITE_ENABLE_JSON1", "1"),
    ("SQLITE_OMIT_LOAD_EXTENSION", "1"),
    ("SQLITE_ENABLE_RTREE", "1"),
    ("SQLITE_ENABLE_STAT4", "1"),
    ("SQLITE_ENABLE_UPDATE_DELETE_LIMIT", "1"),
    ("SQLITE_SOUNDEX", "1"),
    ("SQLITE_USE_URI", "1"),
    ("SQLITE_HAS_CODEC", "1"),
    ("SQLITE_TEMP_STORE", "2"),
    ("SQLITE_THREADSAFE", "1"),
    ("SQLITE_EXTRA_INIT", "sqlcipher_extra_init"),
    ("SQLITE_EXTRA_SHUTDOWN", "sqlcipher_extra_shutdown"),
    ("SQLCIPHER_CRYPTO_OPENSSL", "1"),
    ("HAVE_STDINT_H", "1"),
    ("SQLITE_MAX_VARIABLE_NUMBER", "250000"),
    ("SQLITE_DEFAULT_PAGE_SIZE", "4096"),
    ("SQLITE_DEFAULT_CACHE_SIZE", "-8000"),
    ("inline", "__inline"),
]

libdir = os.path.join(prefix, "lib")
if sys.platform == "win32":
    # The static libcrypto.lib and the system libraries it needs (OpenSSL NOTES-WINDOWS.md, "Linking native applications").
    extra_objects = [os.path.join(libdir, "libcrypto.lib")]
    libraries = ["ws2_32", "gdi32", "advapi32", "crypt32", "user32"]
    extra_compile_args = []
else:
    # The archive itself, never -lcrypto: a -l search could find a shared libcrypto on the build host first.
    extra_objects = [os.path.join(libdir, "libcrypto.a")]
    libraries = ["m", "pthread"]
    extra_compile_args = ["-Qunused-arguments"] if sys.platform == "darwin" else []

for path in extra_objects:
    if not os.path.isfile(path):
        raise SystemExit(f"the static OpenSSL is not at {path}")

# The three licences travel inside the wheel (the binding's zlib, SQLCipher's BSD-3, OpenSSL's Apache-2.0): the node's
# generate_credits.py reads a wheel's own metadata, and a wheel that names only zlib would under-credit what it carries.
LICENCES = ["LICENSE", "SQLCIPHER_LICENSE.md", "OPENSSL_LICENSE.txt"]
for path in LICENCES:
    if not os.path.isfile(path):
        raise SystemExit(f"the licence file {path} is missing from the build tree")

setup(
    name="sqlcipher3-wheels",
    version=version,
    packages=["sqlcipher3"],
    license_expression="Zlib AND BSD-3-Clause AND Apache-2.0",
    license_files=LICENCES,
    ext_modules=[Extension(
        name="sqlcipher3._sqlite3",
        sources=sorted(glob("src/*.c")) + ["src/sqlcipher/sqlite3.c"],
        define_macros=define_macros,
        include_dirs=["./src", os.path.join(prefix, "include")],
        extra_objects=extra_objects,
        libraries=libraries,
        extra_compile_args=extra_compile_args,
        language="c",
    )],
)
