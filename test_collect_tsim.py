"""
Tests for collect_tsim.py.

Verifies the end-to-end flow: generate circuits -> collect via sinter+tsim
-> produce CSV output with data rows.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching --with numpy \
      python test_collect_tsim.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).parent)


def test_collect_tsim_end_to_end():
    """Generate circuits, run collect_tsim.py, verify CSV output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        circuits_dir = os.path.join(tmpdir, "circuits")
        output_csv = os.path.join(tmpdir, "results.csv")

        # Step 1: Generate circuits
        subprocess.check_call(
            [sys.executable, "generate_tsim_circuits.py",
             "--output-dir", circuits_dir,
             "--noise-rates", "0.02"],
            cwd=PROJECT_ROOT,
        )
        circuit_files = [f for f in os.listdir(circuits_dir) if f.endswith(".circuit")]
        assert len(circuit_files) == 1, f"Expected 1 circuit file, got {len(circuit_files)}"

        # Step 2: Run collect_tsim.py
        subprocess.check_call(
            [sys.executable, "collect_tsim.py",
             "--circuits-dir", circuits_dir,
             "--output-csv", output_csv,
             "--max-shots", "100",
             "--max-errors", "100"],
            cwd=PROJECT_ROOT,
        )

        # Step 3: Verify CSV exists and has content
        assert os.path.exists(output_csv), f"Output CSV not found: {output_csv}"
        with open(output_csv) as f:
            lines = f.read().strip().split("\n")
        assert len(lines) >= 2, f"Expected header + data rows, got {len(lines)} lines"
        # First line should be the CSV header
        assert lines[0].startswith("shots"), f"Header doesn't start with 'shots': {lines[0][:50]}"
        # Data row should have nonzero shots
        data_line = lines[1]
        shots_val = int(data_line.split(",")[0])
        assert shots_val > 0, f"Expected nonzero shots in data, got {shots_val}"


def test_collect_tsim_no_circuits_exits_nonzero():
    """collect_tsim.py exits with code 1 if no .circuit files found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_dir = os.path.join(tmpdir, "empty")
        os.makedirs(empty_dir)
        output_csv = os.path.join(tmpdir, "results.csv")

        result = subprocess.run(
            [sys.executable, "collect_tsim.py",
             "--circuits-dir", empty_dir,
             "--output-csv", output_csv],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True,
        )
        assert result.returncode != 0, \
            f"Expected nonzero exit code for empty dir, got {result.returncode}"


def test_collect_tsim_creates_parent_dirs():
    """collect_tsim.py creates parent directories for output CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        circuits_dir = os.path.join(tmpdir, "circuits")
        output_csv = os.path.join(tmpdir, "nested", "deep", "results.csv")

        subprocess.check_call(
            [sys.executable, "generate_tsim_circuits.py",
             "--output-dir", circuits_dir,
             "--noise-rates", "0.02"],
            cwd=PROJECT_ROOT,
        )

        subprocess.check_call(
            [sys.executable, "collect_tsim.py",
             "--circuits-dir", circuits_dir,
             "--output-csv", output_csv,
             "--max-shots", "100",
             "--max-errors", "100"],
            cwd=PROJECT_ROOT,
        )
        assert os.path.exists(output_csv), f"Output CSV not created at {output_csv}"


if __name__ == "__main__":
    tests = [
        ("test_collect_tsim_end_to_end", test_collect_tsim_end_to_end),
        ("test_collect_tsim_no_circuits_exits_nonzero", test_collect_tsim_no_circuits_exits_nonzero),
        ("test_collect_tsim_creates_parent_dirs", test_collect_tsim_creates_parent_dirs),
    ]
    failed = []
    for name, fn in tests:
        print(f"{name}:")
        try:
            fn()
            print(f"  PASS\n")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  FAIL: {type(e).__name__}: {e}\n")
            failed.append(name)

    if failed:
        print(f"\n{len(failed)}/{len(tests)} tests FAILED: {failed}")
        sys.exit(1)
    else:
        print(f"\nALL {len(tests)} TESTS PASSED")
