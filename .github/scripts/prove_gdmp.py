#!/usr/bin/env python3
"""Prove a freshly built GDMP artifact before it is released.

Usage:
    prove_gdmp.py align  <dir with native libraries> [--negative <known-bad.so>]
    prove_gdmp.py detect <result.json written by prove_gdmp.gd>

⚠️ **A library that exists is not evidence that it works, and on Android a
library that WORKS is not evidence that it will LOAD.** Both halves have already
cost this project a build, so this script has two subcommands and neither is
optional.

## `align` -- the one that exists because a phone was the only detector

Kunuleco hit `PageSizeMismatchDialog` on a Pixel on 2026-09-14 with a GDExtension
whose arm64 library was linked at a 4 KB page alignment. Google made
`max-page-size=16384` the linker default in NDK 27; a toolchain older than that
produces a library that loads and works everywhere except on a device with 16 KB
pages, where the OS refuses it. **No test saw it. The export printed nothing.**

⚠️ **GDMP's own v0.6 release ships exactly this defect**: measured 2026-09-16,
`libs/arm64/libGDMP.android.so` has `p_align = 0x1000`. Upstream fixed it in
commit *"build android libs with 16KB alignment"* (2026-03-27), which is one of
the two reasons this repo builds GDMP from source rather than shipping theirs.

🔴 **`--negative` is what makes the check mean anything.** Pass it a library
known to be 4 KB aligned and the script asserts that it is REJECTED. A checker
that passes everything reports the same output as a checker that works, which is
this project's most expensive recurring failure shape.

It reads ELF program headers rather than trusting a filename or a build flag,
**because the flag is what was wrong upstream.**

## `detect` -- the one that proves MediaPipe actually ran

`prove_gdmp.gd` loads the built extension in a real Godot binary, runs
`MediaPipeFaceLandmarker` over a portrait, and writes what came back. This
asserts against that:

1. The extension loaded at all (the class list is non-empty).
2. The portrait yields exactly one face.
3. It yields **52 categories named the ARKit way** -- `jawOpen`, `eyeBlinkLeft`
   and the rest -- because that naming is the entire reason this dependency was
   chosen over a head-pose tracker. ⚠️ **52 CATEGORIES is `_neutral` plus 51
   shapes, not the ARKit 52**: MediaPipe does not emit `tongueOut`. Measured
   2026-09-16, and written here because "52" reading as the ARKit list is an
   off-by-one waiting to be repeated.
4. A 4x4 facial transformation matrix came back with it.
5. 🔴 **NEGATIVE CONTROL: a blank image yields ZERO faces.** Steps 2-4 can all
   pass against a stub that returns a canned result; a detector that finds a face
   in a flat grey square has told you nothing, and it fails in the permissive
   direction. **If this script is ever simplified, keep step 5.**

Exit 0 = PASS. Any failure prints what was measured and exits 1.
"""
import json
import os
import struct
import sys

WANT_ALIGN = 0x4000  # 16 KB, NDK 27's default and Android's requirement
PT_LOAD = 1

# A sample of the ARKit 52 that a stub would have to reproduce exactly. Not the
# whole list -- these are spread across eye, jaw, mouth and brow so a partial
# implementation cannot pass by covering one region.
ARKIT_WITNESS = (
    "eyeBlinkLeft", "eyeLookOutRight", "jawOpen", "mouthSmileLeft",
    "mouthPucker", "browDownRight", "cheekPuff", "noseSneerLeft",
)


def load_align(path):
    """Largest p_align over the PT_LOAD segments, or None if not an ELF."""
    with open(path, "rb") as f:
        head = f.read(64)
        if head[:4] != b"\x7fELF":
            return None
        if head[4] != 2:
            raise SystemExit("%s is a 32-bit ELF; this project ships none" % path)
        phoff = struct.unpack_from("<Q", head, 0x20)[0]
        phentsize = struct.unpack_from("<H", head, 0x36)[0]
        phnum = struct.unpack_from("<H", head, 0x38)[0]
        f.seek(phoff)
        blob = f.read(phentsize * phnum)
    best = 0
    for i in range(phnum):
        ph = blob[i * phentsize:(i + 1) * phentsize]
        if len(ph) < 56:
            continue
        p_type = struct.unpack_from("<I", ph, 0)[0]
        if p_type != PT_LOAD:
            continue
        best = max(best, struct.unpack_from("<Q", ph, 48)[0])
    return best


def cmd_align(argv):
    if not argv:
        raise SystemExit("align: need a directory")
    root = argv[0]
    negative = None
    if "--negative" in argv:
        negative = argv[argv.index("--negative") + 1]
    # ⚠️ **Scope, stated rather than assumed.** 16 KB pages are an Android
    # requirement; a desktop x86_64 library is legitimately 4 KB aligned and
    # measured so -- GDMP's own `libGDMP.linux.so` is `p_align 0x1000` and that
    # is correct. So this gate is pointed at Android output only, and it REFUSES
    # to run over a directory with no Android library in it rather than
    # reporting a clean pass over the wrong files. `--any-platform` opts out,
    # for the day an arm64 desktop needs the same check.
    require_android = "--any-platform" not in argv

    checked, failed = [], []
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            path = os.path.join(dirpath, name)
            try:
                align = load_align(path)
            except Exception as exc:
                raise SystemExit("could not read %s: %s" % (path, exc))
            if align is None:
                continue
            gated = (not require_android) or ("android" in name.lower())
            checked.append((path, align, gated))
            if gated and align < WANT_ALIGN:
                failed.append((path, align))

    if not checked:
        raise SystemExit("align: found NO ELF libraries under %s -- the build "
                         "step produced nothing, which is a failure and not a pass"
                         % root)
    if require_android and not any(g for _p, _a, g in checked):
        raise SystemExit("align: %d ELF libraries under %s and NOT ONE is an "
                         "Android library. This gate is about Android page size; "
                         "run it on the Android build output, or pass "
                         "--any-platform if you mean it." % (len(checked), root))

    for path, align, gated in checked:
        if not gated:
            print("  %-64s p_align 0x%-6x (%2d KB)  not gated (not Android)"
                  % (os.path.relpath(path, root), align, align // 1024))
            continue
        print("  %-64s p_align 0x%-6x (%2d KB)  %s"
              % (os.path.relpath(path, root), align, align // 1024,
                 "ok" if align >= WANT_ALIGN else "TOO SMALL"))

    # The negative control. Without it, "everything passed" and "the check is
    # broken" render identically.
    if negative:
        neg = load_align(negative)
        if neg is None:
            raise SystemExit("negative control %s is not an ELF" % negative)
        if neg >= WANT_ALIGN:
            raise SystemExit(
                "negative control %s has p_align 0x%x, which is NOT the 4 KB "
                "library this check is supposed to reject -- the control is "
                "wrong, so the result above proves nothing" % (negative, neg))
        print("  negative control rejected as expected: %s p_align 0x%x (%d KB)"
              % (os.path.basename(negative), neg, neg // 1024))

    if failed:
        raise SystemExit("\n%d library(ies) below %d KB alignment -- this is the "
                         "PageSizeMismatchDialog defect and it only shows up on a "
                         "phone" % (len(failed), WANT_ALIGN // 1024))
    n_gated = sum(1 for _p, _a, g in checked if g)
    print("\n%d ELF libraries read, %d gated, all aligned to at least %d KB."
          % (len(checked), n_gated, WANT_ALIGN // 1024))


def cmd_detect(argv):
    if not argv:
        raise SystemExit("detect: need the result json")
    with open(argv[0], encoding="utf-8") as f:
        r = json.load(f)

    classes = r.get("mediapipe_classes", 0)
    if classes < 1:
        raise SystemExit("the extension registered %d MediaPipe classes -- it did "
                         "not load" % classes)
    print("  extension loaded: %d MediaPipe classes registered" % classes)

    if r.get("portrait_faces") != 1:
        raise SystemExit("portrait yielded %s faces, expected exactly 1"
                         % r.get("portrait_faces"))

    names = r.get("blendshape_names") or []
    if len(names) != 52:
        raise SystemExit("got %d categories, expected 52 -- the ARKit vocabulary "
                         "is the reason this dependency was chosen" % len(names))
    if "_neutral" not in names:
        raise SystemExit("no `_neutral` category: this is not MediaPipe's face "
                         "blendshape head, whatever else it is")
    missing = [n for n in ARKIT_WITNESS if n not in names]
    if missing:
        raise SystemExit("categories are not ARKit-named; missing %s" % missing)
    print("  portrait: 1 face, 52 categories (_neutral + 51 ARKit-named shapes)")

    top = r.get("top") or []
    if not top or float(top[0][1]) <= 0.0:
        raise SystemExit("every blend shape scored zero -- a face was found and "
                         "nothing was measured on it")
    print("  strongest: %s %.4f" % (top[0][0], float(top[0][1])))

    if not r.get("has_transform"):
        raise SystemExit("no facial transformation matrix -- the head pose is half "
                         "the point of this artifact")
    print("  head transform present")

    # The control. A detector that finds a face in flat grey has told you nothing.
    blank = r.get("blank_faces")
    if blank is None:
        raise SystemExit("the blank-image control did not run; without it a canned "
                         "result would pass every check above")
    if blank != 0:
        raise SystemExit("NEGATIVE CONTROL FAILED: %d face(s) detected in a blank "
                         "image" % blank)
    print("  negative control: 0 faces in a blank image")
    print("\nMediaPipe ran, in this Godot binary, on this artifact.")


def main(argv):
    if len(argv) < 2 or argv[1] not in ("align", "detect"):
        print(__doc__.strip())
        return 2
    {"align": cmd_align, "detect": cmd_detect}[argv[1]](argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
