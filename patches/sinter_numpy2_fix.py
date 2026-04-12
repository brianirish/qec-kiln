#!/usr/bin/env python3
"""
Patch sinter for numpy 2.x compatibility.

Background
----------
numpy 2.0 changed the int hierarchy: `isinstance(np.int64(5), int)` now returns
False (it returned True in numpy 1.x). Sinter has strict `assert isinstance(x,
int)` checks that crash when numpy ints flow through it.

The upstream cause is in `sinter._decoding._stim_then_decode_sampler` where
`classify_discards_and_errors()` uses `np.count_nonzero()` (which returns
`numpy.intp`, a numpy int subclass). The function is even annotated as
returning `tuple[int, int]` — the annotation lies. The numpy ints then flow
into `AnonTaskStats(errors=num_errors, ...)` which fails its `__post_init__`
assertion.

This patch coerces the return values to Python `int` at the source. That fixes
the assertion error in `AnonTaskStats.__post_init__` without weakening any
type guarantees in sinter.

Should be submitted upstream as a PR to quantumlib/Stim.

Usage
-----
    python3 sinter_numpy2_fix.py [<sinter_install_dir>]

If no path is given, the script imports sinter to find its install location.
Idempotent: applying twice is a no-op.
"""
import sys
from pathlib import Path


def find_sinter_dir() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    import sinter
    return Path(sinter.__file__).parent


def patch_classify_discards_and_errors(sinter_dir: Path) -> None:
    target = sinter_dir / "_decoding" / "_stim_then_decode_sampler.py"
    src = target.read_text()

    old = (
        "    num_errors = np.count_nonzero(fail_mask)\n"
        "    return num_discards, num_errors\n"
    )
    new = (
        "    # numpy 2.x compat: np.count_nonzero returns numpy.intp, not Python int.\n"
        "    # The function is annotated as returning tuple[int, int]; coerce to honor that.\n"
        "    num_errors = int(np.count_nonzero(fail_mask))\n"
        "    return int(num_discards), num_errors\n"
    )

    if new in src:
        print(f"[skip] already patched: {target}")
        return
    if old not in src:
        raise RuntimeError(
            f"Could not find expected snippet in {target}. "
            "Sinter version may have changed; update this patch."
        )
    target.write_text(src.replace(old, new))
    print(f"[ok]   patched: {target}")


def main() -> None:
    sinter_dir = find_sinter_dir()
    if not sinter_dir.is_dir():
        raise SystemExit(f"sinter directory not found: {sinter_dir}")
    print(f"sinter_dir: {sinter_dir}")
    patch_classify_discards_and_errors(sinter_dir)
    print("done.")


if __name__ == "__main__":
    main()
