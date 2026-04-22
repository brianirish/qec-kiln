"""
TsimThenDecodeSampler: a sinter.Sampler backend that samples detection
events using bloqade-tsim (QuEra's ZX-stabilizer-rank simulator), then
decodes with a sinter.Decoder.

Used by collect_tsim.py on GPU worker nodes. See spike_tsim/ for the
original spike investigation and validation tests.

Usage:
    import sinter
    from tsim_sampler import TsimThenDecodeSampler

    sampler = TsimThenDecodeSampler(decoder_name="pymatching")
    sinter.collect(
        tasks=[sinter.Task(circuit=stim_circuit, decoder="pymatching_tsim")],
        custom_decoders={"pymatching_tsim": sampler},
        ...
    )

Known limitations (see spike_tsim/SPIKE_VERDICT.md for detail):
- tsim's Clifford-circuit sampling shows a small (~2-5%) systematic
  disagreement with stim on surface code circuits. The root cause is
  unclear and unrelated to the sinter integration.
- This wrapper uses tsim.Circuit.from_stim_program, which copies the
  circuit into tsim's internal representation on each Task.
- count_observable_error_combos and count_detection_events are supported
  via the same machinery as sinter's default stim path.
- Lazy tsim import in compiled_sampler_for_task for spawn-safety.
"""
from __future__ import annotations

import collections
import pathlib
import time
from typing import Optional

import numpy as np

import sinter
from sinter import Sampler, CompiledSampler, Task, AnonTaskStats
# We reuse sinter's internal helpers verbatim. These live in a private
# module and their API is not stable, but they're the exact same helpers
# the default stim path uses, so behavior is identical modulo the sampler swap.
from sinter._decoding._stim_then_decode_sampler import (
    classify_discards_and_errors,
    _compile_decoder_with_disk_fallback,
)


class TsimThenDecodeSampler(Sampler):
    """Samples shots using bloqade-tsim, then decodes using the given decoder.

    Mirrors sinter's default StimThenDecodeSampler, with exactly one change:
    the sampler backend is tsim instead of stim.
    """
    def __init__(
        self,
        *,
        decoder_name: str = "pymatching",
        count_observable_error_combos: bool = False,
        count_detection_events: bool = False,
        tmp_dir: Optional[pathlib.Path] = None,
        use_reference_samples: bool = True,
    ):
        """
        Args:
            decoder_name: one of sinter's built-in decoders (pymatching, fusion_blossom, ...).
                The decoder is looked up from sinter.BUILT_IN_DECODERS at sample time.
            count_observable_error_combos: pass-through to the decoder behavior.
            count_detection_events: pass-through to the decoder behavior.
            tmp_dir: optional working directory for decoders that require disk.
            use_reference_samples: pass use_detector_reference_sample and
                use_observable_reference_sample to tsim.sample. Default True for
                stim-compat Clifford paths. Set False when detectors encode
                syndrome-vs-constant XORs directly (e.g. magic-state distillation
                with ancilla-encoded expected syndrome); in that case XORing
                against a noiseless reference shot would wash the syndrome
                selection out against a random reference branch.
        """
        if decoder_name not in sinter.BUILT_IN_DECODERS:
            raise ValueError(
                f"Unknown decoder {decoder_name!r}. "
                f"Expected one of {sorted(sinter.BUILT_IN_DECODERS.keys())}"
            )
        self.decoder_name = decoder_name
        self.count_observable_error_combos = count_observable_error_combos
        self.count_detection_events = count_detection_events
        self.tmp_dir = tmp_dir
        self.use_reference_samples = use_reference_samples

    def compiled_sampler_for_task(self, task: Task) -> CompiledSampler:
        # Lazy import of tsim so spawned workers don't pay the JAX import
        # cost before they actually need to sample.
        import tsim

        decoder = sinter.BUILT_IN_DECODERS[self.decoder_name]
        return _CompiledTsimThenDecodeSampler(
            decoder=decoder,
            task=task,
            count_detection_events=self.count_detection_events,
            count_observable_error_combos=self.count_observable_error_combos,
            tmp_dir=self.tmp_dir,
            tsim_module=tsim,
            use_reference_samples=self.use_reference_samples,
        )


class _CompiledTsimThenDecodeSampler(CompiledSampler):
    """Mirrors sinter's _CompiledStimThenDecodeSampler with the sampler swap."""

    def __init__(
        self,
        *,
        decoder,
        task: Task,
        count_observable_error_combos: bool,
        count_detection_events: bool,
        tmp_dir: Optional[pathlib.Path],
        tsim_module,
        use_reference_samples: bool = True,
    ):
        self.task = task
        self.use_reference_samples = use_reference_samples
        self.compiled_decoder = _compile_decoder_with_disk_fallback(decoder, task, tmp_dir)

        # THE WHOLE POINT: replace stim's sampler with tsim's.
        #
        # Two cases for task.circuit:
        # (a) stim.Circuit (Clifford-only): convert to tsim via from_stim_program.
        # (b) tsim.Circuit (non-Clifford, built via tsim.Circuit("... T 0 ...")):
        #     use directly. This is the target path for the qec-kiln tsim extension,
        #     since only tsim's own text format supports T, R_X/Y/Z, U3.
        #
        # Sinter's Task.circuit is type-annotated as stim.Circuit but not enforced
        # at runtime. Passing a tsim.Circuit via duck typing works as long as
        # sinter's downstream code only touches methods both classes implement
        # (num_detectors, num_observables, detector_error_model). Spike tested as
        # of 2026-04-07 against sinter 1.15.0.
        if isinstance(task.circuit, tsim_module.Circuit):
            tsim_circuit = task.circuit
        else:
            tsim_circuit = tsim_module.Circuit.from_stim_program(task.circuit)
        self._tsim_sampler = tsim_circuit.compile_detector_sampler()

        self.count_observable_error_combos = count_observable_error_combos
        self.count_detection_events = count_detection_events
        self.num_det = task.circuit.num_detectors
        self.num_obs = task.circuit.num_observables

    def sample(self, max_shots: int) -> AnonTaskStats:
        t0 = time.monotonic()

        # THE WHOLE POINT (other half): sample from tsim, not stim.
        # The two `use_*_reference_sample=True` flags align tsim's detection
        # convention with stim's (tsim reports absolute detector bits by default;
        # stim reports XOR against a noiseless reference). See tsim README.
        # Pin batch_size to max_shots so results are reproducible given
        # the same seed. Without this, tsim auto-selects batch_size based
        # on available memory, and the seed/batch-size coupling (tsim#104)
        # means the same seed can produce different samples.
        dets, actual_obs = self._tsim_sampler.sample(
            shots=max_shots,
            batch_size=max_shots,
            bit_packed=True,
            separate_observables=True,
            use_detector_reference_sample=self.use_reference_samples,
            use_observable_reference_sample=self.use_reference_samples,
        )
        num_shots = dets.shape[0]

        # Everything below this line is byte-for-byte copied from sinter's
        # _CompiledStimThenDecodeSampler.sample, because the post-sampling
        # logic is identical regardless of which simulator produced the bits.

        custom_counts = collections.Counter()
        if self.count_detection_events:
            custom_counts['detectors_checked'] += self.num_det * num_shots
            for b in range(8):
                custom_counts['detection_events'] += int(np.count_nonzero(dets & (1 << b)))

        # Decode BEFORE post-selection so the shape check below compares
        # against the true sampled shot count. (sinter's upstream
        # _CompiledStimThenDecodeSampler decodes after post-selection but then
        # asserts predictions.shape[0] == num_shots, which spuriously fires
        # whenever any shot is discarded via postselection_mask. We do it in
        # the safe order.)
        predictions = self.compiled_decoder.decode_shots_bit_packed(
            bit_packed_detection_event_data=dets
        )
        if not isinstance(predictions, np.ndarray):
            raise ValueError("decoder returned non-ndarray predictions")
        if predictions.dtype != np.uint8:
            raise ValueError(f"decoder predictions.dtype == {predictions.dtype}, expected uint8")
        if len(predictions.shape) != 2:
            raise ValueError("decoder predictions are not 2D")
        if predictions.shape[0] != num_shots:
            raise ValueError("decoder predictions.shape[0] != num_shots")
        if predictions.shape[1] < actual_obs.shape[1]:
            raise ValueError("decoder predictions.shape[1] < num observable bytes")
        if predictions.shape[1] > actual_obs.shape[1] + 1:
            raise ValueError("decoder predictions.shape[1] > num observable bytes + 1")

        # Now apply post-selection to dets + predictions + actual_obs together.
        if self.task.postselection_mask is not None:
            discarded_flags = np.any(dets & self.task.postselection_mask, axis=1)
            num_discards_1 = int(np.count_nonzero(discarded_flags))
            if num_discards_1:
                keep = ~discarded_flags
                dets = dets[keep, :]
                actual_obs = actual_obs[keep, :]
                predictions = predictions[keep, :]
        else:
            num_discards_1 = 0

        num_discards_2, num_errors = classify_discards_and_errors(
            actual_obs=actual_obs,
            predictions=predictions,
            postselected_observables_mask=self.task.postselected_observables_mask,
            out_count_observable_error_combos=(
                custom_counts if self.count_observable_error_combos else None
            ),
            num_obs=self.num_obs,
        )
        t1 = time.monotonic()

        # numpy 2.x: classify_discards_and_errors returns numpy.intp, which is
        # no longer a subclass of int and fails AnonTaskStats' isinstance() check.
        # Same root cause as qec-kiln BENCHMARK.md lesson learned #7.
        return AnonTaskStats(
            shots=int(num_shots),
            errors=int(num_errors),
            discards=int(num_discards_1) + int(num_discards_2),
            seconds=float(t1 - t0),
            custom_counts=custom_counts,
        )
