# riffusion_engine.py
"""
Riffusion-style ambient generator wrapper.

This is a pragmatic, minimal wrapper to run an ambient spectrogram diffusion pipeline where:
- text prompt -> spectrogram image -> griffin-lim / vocoder -> audio
- Depending on your available Riffusion model, you may need to adapt model names.

This file aims to be a practical starting point; you may replace the 'generate' internals
with a more optimized Riffusion repo clone if you have one.
"""

import os
import time
import numpy as np
from typing import Tuple

try:
    from diffusers import DiffusionPipeline
    DIFFUSERS_AVAILABLE = True
except Exception:
    DIFFUSERS_AVAILABLE = False

import torch
from loop_utils import apply_fade_in_out, save_wav, normalize_audio

# Griffin-Lim from librosa for spectrogram inversion
try:
    import librosa
    LIBROSA_AVAILABLE = True
except Exception:
    LIBROSA_AVAILABLE = False


class RiffusionEngine:
    def __init__(self, model_id: str = "riffusion/riffusion-model-v1", device: str = None):
        if not DIFFUSERS_AVAILABLE:
            raise RuntimeError("diffusers not available. Install 'diffusers' to use Riffusion engine.")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_id = model_id
        print(f"[Riffusion] Using device: {self.device}, model: {model_id}")
        # Load a text-to-spectrogram pipeline — model must exist on HF or local.
        self.pipe = DiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16 if self.device.startswith("cuda") else torch.float32)
        self.pipe.to(self.device)
        # Default sample rate / n_fft chosen as used by riffusion variants
        self.sr = 32000
        self.n_fft = 2048

    def generate_spectrogram(self, prompt: str, seed: int = 42, num_inference_steps: int = 25) -> np.ndarray:
        torch.manual_seed(seed)
        # Many riffusion pipelines return a spectrogram image or tensor; here we call the pipeline
        result = self.pipe(prompt, num_inference_steps=num_inference_steps)
        # result may include .images or .spectrograms depending on implementation
        if hasattr(result, "images") and len(result.images) > 0:
            # Convert PIL image to spectrogram array
            img = result.images[0]
            arr = np.asarray(img).astype(np.float32) / 255.0
            # convert RGB -> mono luminance
            spec = arr.mean(axis=2)
            # scale to expected magnitude range
            return spec
        elif hasattr(result, "spectrogram"):
            return result.spectrogram
        else:
            raise RuntimeError("Unexpected pipeline output. Inspect the diffusers pipeline used for Riffusion.")

    def spectrogram_to_audio(self, spec: np.ndarray) -> np.ndarray:
        """
        Simple spectrogram->audio via Griffin-Lim (librosa).
        spec expected to be in range 0..1; we'll map to magnitude and do inverse stft.
        """
        if not LIBROSA_AVAILABLE:
            raise RuntimeError("librosa required for spectrogram inversion. Install librosa.")
        # Rough mapping: spec -> magnitude
        # Resize spectrogram to expected shape (freq_bins, time_frames)
        # This mapping is dependent on how the pipeline encodes spectrograms; this is an approximate method.
        spec_resized = librosa.util.fix_length(spec.T, size=spec.T.shape[1], axis=1)
        # Create magnitude spectrogram with log scaling inverse approximation
        magnitude = np.maximum(1e-6, spec_resized)
        # Griffin-Lim inversion
        audio = librosa.griffinlim(magnitude, n_iter=32, hop_length=256, win_length=1024)
        return audio.astype("float32")

    def generate(self, prompt: str, seed: int = 42, duration: int = 12) -> Tuple[np.ndarray, int]:
        """
        Generate audio by producing a spectrogram and converting to audio.
        Duration control is limited; you may generate a spectrogram whose length corresponds to desired duration.
        """
        # Generate spectrogram (model-dependent)
        spec = self.generate_spectrogram(prompt, seed=seed, num_inference_steps=25)
        audio = self.spectrogram_to_audio(spec)
        # Normalize, trim/pad to approximate duration (sr * duration)
        target_len = int(duration * self.sr)
        if len(audio) < target_len:
            # pad
            pad = np.zeros(target_len - len(audio), dtype=audio.dtype)
            audio = np.concatenate([audio, pad])
        else:
            audio = audio[:target_len]
        audio = normalize_audio(audio)
        return audio, self.sr


def generate_riffusion_loop(prompt: str, seed: int, duration: int = 12, out_path: str = "riffusion_loop.wav", model_id: str = "riffusion/riffusion-model-v1") -> str:
    start = time.time()
    engine = RiffusionEngine(model_id=model_id)
    audio, sr = engine.generate(prompt=prompt, seed=seed, duration=duration)
    audio = apply_fade_in_out(audio, sr, fade_ms=400)
    save_wav(out_path, audio, sr)
    elapsed = time.time() - start
    print(f"[Riffusion] Generated {duration}s loop in {elapsed:.2f}s -> {out_path}")
    return out_path
