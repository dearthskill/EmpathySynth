# loop_utils.py
"""
Utilities for processing generated audio loops:
- normalize
- apply fade-in/out to make loopable
- crossfade two loops
- save audio to file (soundfile)
"""

import numpy as np
import soundfile as sf
from typing import Tuple


def normalize_audio(audio: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Normalize audio to -1..1 range (peak normalization)."""
    peak = np.max(np.abs(audio)) + eps
    return audio / peak


def apply_fade_in_out(audio: np.ndarray, sr: int, fade_ms: int = 400) -> np.ndarray:
    """
    Apply fade-in and fade-out for smooth looping.
    fade_ms: milliseconds for fade at start and end.
    """
    fade_samples = int(sr * (fade_ms / 1000.0))
    if fade_samples <= 0 or fade_samples * 2 >= len(audio):
        return audio
    fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=audio.dtype)
    fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=audio.dtype)
    audio[:fade_samples] = audio[:fade_samples] * fade_in
    audio[-fade_samples:] = audio[-fade_samples:] * fade_out
    return audio


def crossfade_two_loops(loop_a: np.ndarray, loop_b: np.ndarray, sr: int, fade_time: float = 3.0) -> np.ndarray:
    """
    Crossfade from loop_a to loop_b over fade_time seconds.
    Returns concatenated audio that smoothly transitions from a->b.
    Both loops should be numpy arrays (1D or 2D with channels last).
    """
    fade_samples = int(fade_time * sr)
    # Ensure loops are at least fade length
    if fade_samples <= 0:
        return np.concatenate([loop_a, loop_b], axis=0)

    # If stereo shape handling
    def ensure_2d(x):
        if x.ndim == 1:
            return x.reshape(-1, 1)
        return x

    a = ensure_2d(loop_a)
    b = ensure_2d(loop_b)
    # If channel mismatch, reduce to mono (simple)
    if a.shape[1] != b.shape[1]:
        # convert both to mono
        a = np.mean(a, axis=1, keepdims=True)
        b = np.mean(b, axis=1, keepdims=True)

    # Prepare fade windows
    fade_in = np.linspace(0.0, 1.0, fade_samples)[:, None]
    fade_out = 1.0 - fade_in

    a_pre = a[:-fade_samples]
    a_tail = a[-fade_samples:] * fade_out
    b_head = b[:fade_samples] * fade_in
    b_rest = b[fade_samples:]

    middle = a_tail + b_head
    result = np.concatenate([a_pre, middle, b_rest], axis=0)

    # If originally mono, return 1D
    if loop_a.ndim == 1 and loop_b.ndim == 1:
        return result[:, 0]
    return result


def save_wav(path: str, audio: np.ndarray, sr: int):
    """Save audio to wav using soundfile. Accepts float32 numpy array."""
    # Ensure float32 type and normalized
    audio_out = normalize_audio(audio).astype('float32')
    sf.write(path, audio_out, sr)
    return path
