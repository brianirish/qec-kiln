"""
T1: tsim alone can sample a stim-built circuit.

Sanity gate. Confirms tsim is installed, importable, and can produce
detector samples from a stim.Circuit via from_stim_program(). Does NOT
yet involve sinter or check statistical correctness.

Run with:
    uv run --with bloqade-tsim --with stim --with pytest python -m pytest test_t1_tsim_sample.py -v
"""
import numpy as np
import stim
import tsim


def _build_small_repetition_code():
    """3-qubit repetition code, 3 rounds, depolarizing noise. Tiny but real."""
    return stim.Circuit.generated(
        "repetition_code:memory",
        distance=3,
        rounds=3,
        after_clifford_depolarization=0.05,
        after_reset_flip_probability=0.05,
        before_measure_flip_probability=0.05,
        before_round_data_depolarization=0.05,
    )


def test_tsim_can_load_a_stim_circuit():
    stim_c = _build_small_repetition_code()
    tsim_c = tsim.Circuit.from_stim_program(stim_c)
    # Sanity: tsim sees the same number of detectors and observables
    assert tsim_c.num_detectors == stim_c.num_detectors
    assert tsim_c.num_observables == stim_c.num_observables
    assert tsim_c.num_measurements == stim_c.num_measurements


def test_tsim_compile_detector_sampler_returns_a_sampler():
    stim_c = _build_small_repetition_code()
    tsim_c = tsim.Circuit.from_stim_program(stim_c)
    sampler = tsim_c.compile_detector_sampler(seed=42)
    assert sampler is not None
    assert hasattr(sampler, "sample")


def test_tsim_sample_returns_correct_shape_unpacked():
    stim_c = _build_small_repetition_code()
    tsim_c = tsim.Circuit.from_stim_program(stim_c)
    sampler = tsim_c.compile_detector_sampler(seed=42)

    shots = 1024
    dets = sampler.sample(
        shots=shots,
        use_detector_reference_sample=True,  # match stim convention
    )
    assert dets.shape == (shots, stim_c.num_detectors), \
        f"Expected ({shots}, {stim_c.num_detectors}), got {dets.shape}"
    assert dets.dtype == bool or dets.dtype == np.bool_, f"Expected bool, got {dets.dtype}"


def test_tsim_sample_returns_correct_shape_bit_packed_separate_obs():
    """The mode the sinter wrapper will actually use."""
    stim_c = _build_small_repetition_code()
    tsim_c = tsim.Circuit.from_stim_program(stim_c)
    sampler = tsim_c.compile_detector_sampler(seed=42)

    shots = 1024
    dets, obs = sampler.sample(
        shots=shots,
        bit_packed=True,
        separate_observables=True,
        use_detector_reference_sample=True,
        use_observable_reference_sample=True,
    )
    expected_det_bytes = (stim_c.num_detectors + 7) // 8
    expected_obs_bytes = (stim_c.num_observables + 7) // 8
    assert dets.shape == (shots, expected_det_bytes), \
        f"dets shape: expected ({shots}, {expected_det_bytes}), got {dets.shape}"
    assert obs.shape == (shots, expected_obs_bytes), \
        f"obs shape: expected ({shots}, {expected_obs_bytes}), got {obs.shape}"
    assert dets.dtype == np.uint8
    assert obs.dtype == np.uint8


if __name__ == "__main__":
    import sys
    test_tsim_can_load_a_stim_circuit()
    print("PASS test_tsim_can_load_a_stim_circuit")
    test_tsim_compile_detector_sampler_returns_a_sampler()
    print("PASS test_tsim_compile_detector_sampler_returns_a_sampler")
    test_tsim_sample_returns_correct_shape_unpacked()
    print("PASS test_tsim_sample_returns_correct_shape_unpacked")
    test_tsim_sample_returns_correct_shape_bit_packed_separate_obs()
    print("PASS test_tsim_sample_returns_correct_shape_bit_packed_separate_obs")
    print()
    print("T1 ALL GREEN")
