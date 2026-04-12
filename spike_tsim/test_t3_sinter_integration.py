"""
T3: sinter.collect() works with TsimThenDecodeSampler.

This is the actual integration test the spike was commissioned to answer.
We register our wrapper as a `Sampler` via `custom_decoders` and run a real
sinter collection on a small circuit. If sinter accepts the wrapper and
returns valid TaskStats, the integration is mechanically real.

Note: this test does NOT require statistical equivalence with stim. It just
proves the API plumbing works. T4 covers the equivalence question.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching python test_t3_sinter_integration.py
"""
import sys
from pathlib import Path

import sinter
import stim

# Add this directory to the path so we can import the wrapper
sys.path.insert(0, str(Path(__file__).parent))
from tsim_sampler import TsimThenDecodeSampler


def _build_small_repetition_code():
    return stim.Circuit.generated(
        "repetition_code:memory",
        distance=3,
        rounds=3,
        after_clifford_depolarization=0.05,
        after_reset_flip_probability=0.05,
        before_measure_flip_probability=0.05,
        before_round_data_depolarization=0.05,
    )


def test_sinter_collect_with_tsim_wrapper_returns_stats():
    """Smoke test: sinter accepts the wrapper and produces TaskStats."""
    circuit = _build_small_repetition_code()
    task = sinter.Task(
        circuit=circuit,
        decoder="pymatching_tsim",  # the key under which we register our sampler
    )

    results = sinter.collect(
        num_workers=1,
        tasks=[task],
        max_shots=2_000,
        max_errors=2_000,  # high to ensure we exhaust max_shots
        custom_decoders={"pymatching_tsim": TsimThenDecodeSampler(decoder_name="pymatching")},
        print_progress=False,
    )

    # Validate the basic shape of the result
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    stat = results[0]
    print(f"  Result: shots={stat.shots}, errors={stat.errors}, discards={stat.discards}, seconds={stat.seconds:.3f}")
    assert stat.shots > 0, f"Expected nonzero shots, got {stat.shots}"
    assert stat.shots <= 2_000, f"shot count exceeded budget: {stat.shots}"
    assert stat.errors >= 0
    # error rate should be in a sane range for distance-3 rep at p=0.05
    error_rate = stat.errors / stat.shots
    print(f"  Error rate: {error_rate:.4f}")
    assert 0.01 < error_rate < 0.5, \
        f"Error rate {error_rate:.4f} is wildly out of expected range for d=3 rep at p=0.05"
    # strong_id should be valid
    assert stat.strong_id is not None
    print(f"  strong_id: {stat.strong_id[:16]}...")


def test_sinter_combine_works_on_tsim_output():
    """Verify the output of a tsim-via-sinter run works with sinter combine."""
    circuit = _build_small_repetition_code()
    task = sinter.Task(circuit=circuit, decoder="pymatching_tsim")

    results = sinter.collect(
        num_workers=1,
        tasks=[task],
        max_shots=2_000,
        max_errors=2_000,
        custom_decoders={"pymatching_tsim": TsimThenDecodeSampler(decoder_name="pymatching")},
        print_progress=False,
    )

    # Convert to CSV and try to combine
    import io
    csv_lines = [sinter.CSV_HEADER]
    for stat in results:
        csv_lines.append(stat.to_csv_line())
    csv_text = "\n".join(csv_lines) + "\n"

    # Round-trip through sinter.read_stats_from_csv_files (use tmp file)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write(csv_text)
        tmp_path = f.name
    try:
        round_tripped = sinter.read_stats_from_csv_files(tmp_path)
        assert len(round_tripped) == 1
        assert round_tripped[0].shots == results[0].shots
        assert round_tripped[0].errors == results[0].errors
        print(f"  Round-trip OK: {round_tripped[0].shots} shots, {round_tripped[0].errors} errors")
    finally:
        Path(tmp_path).unlink()


if __name__ == "__main__":
    print("=== T3: sinter+tsim integration ===\n")
    print("test_sinter_collect_with_tsim_wrapper_returns_stats:")
    try:
        test_sinter_collect_with_tsim_wrapper_returns_stats()
        print("  PASS\n")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  FAIL: {e}\n")
        sys.exit(1)

    print("test_sinter_combine_works_on_tsim_output:")
    try:
        test_sinter_combine_works_on_tsim_output()
        print("  PASS\n")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  FAIL: {e}\n")
        sys.exit(1)

    print("T3 ALL GREEN")
