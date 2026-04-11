"""
Tests for generate_tsim_circuits.py.

Verifies that the generator produces valid tsim .circuit files
containing real non-Clifford distillation circuits that work
end-to-end through sinter + TsimThenDecodeSampler.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching --with numpy \
      python test_generate_circuits.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tsim
import sinter

from tsim_sampler import TsimThenDecodeSampler


def test_generates_circuit_files():
    """Generator creates .circuit files (not .stim)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.check_call(
            [sys.executable, "generate_tsim_circuits.py", "--output-dir", tmpdir],
            cwd=str(Path(__file__).parent),
        )
        files = os.listdir(tmpdir)
        assert len(files) > 0, "No files generated"
        for f in files:
            assert f.endswith(".circuit"), f"Expected .circuit extension, got {f}"
        # Default noise rates should produce 5 files
        assert len(files) == 5, f"Expected 5 files, got {len(files)}: {files}"


def test_circuits_are_valid_tsim_with_t_gates():
    """Generated circuits load as tsim.Circuit objects with T gates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.check_call(
            [sys.executable, "generate_tsim_circuits.py", "--output-dir", tmpdir],
            cwd=str(Path(__file__).parent),
        )
        for fname in os.listdir(tmpdir):
            path = os.path.join(tmpdir, fname)
            text = open(path).read()
            c = tsim.Circuit(text)
            assert c.tcount() >= 1, f"{fname}: tcount={c.tcount()}, expected >= 1"
            assert not c.is_clifford, f"{fname}: circuit is Clifford, expected non-Clifford"


def test_circuits_have_detectors_and_observables():
    """Generated circuits have detectors and observables (required for sinter)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.check_call(
            [sys.executable, "generate_tsim_circuits.py", "--output-dir", tmpdir],
            cwd=str(Path(__file__).parent),
        )
        for fname in os.listdir(tmpdir):
            path = os.path.join(tmpdir, fname)
            text = open(path).read()
            c = tsim.Circuit(text)
            assert c.num_detectors >= 1, f"{fname}: no detectors"
            assert c.num_observables >= 1, f"{fname}: no observables"


def test_circuits_sample_through_sinter():
    """Generated circuits can be sampled through sinter + TsimThenDecodeSampler."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.check_call(
            [sys.executable, "generate_tsim_circuits.py", "--output-dir", tmpdir],
            cwd=str(Path(__file__).parent),
        )
        # Test with one circuit (the lowest noise rate, fastest to sample)
        files = sorted(os.listdir(tmpdir))
        path = os.path.join(tmpdir, files[0])
        text = open(path).read()
        c = tsim.Circuit(text)

        task = sinter.Task(
            circuit=c,
            decoder="pymatching_tsim",
            skip_validation=True,
        )

        results = sinter.collect(
            num_workers=1,
            tasks=[task],
            max_shots=100,
            max_errors=100,
            custom_decoders={
                "pymatching_tsim": TsimThenDecodeSampler(
                    decoder_name="pymatching",
                )
            },
            print_progress=False,
        )

        assert len(results) == 1
        stat = results[0]
        assert stat.shots == 100, f"Expected 100 shots, got {stat.shots}"
        error_rate = stat.errors / stat.shots
        assert 0.0 <= error_rate <= 1.0, f"Error rate {error_rate:.4f} out of range"


if __name__ == "__main__":
    tests = [
        ("test_generates_circuit_files", test_generates_circuit_files),
        ("test_circuits_are_valid_tsim_with_t_gates", test_circuits_are_valid_tsim_with_t_gates),
        ("test_circuits_have_detectors_and_observables", test_circuits_have_detectors_and_observables),
        ("test_circuits_sample_through_sinter", test_circuits_sample_through_sinter),
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
