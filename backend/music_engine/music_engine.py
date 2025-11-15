# music_engine.py
"""
Stable MusicGen engine wrapper.
Works with latest HuggingFace Transformers.
Does NOT use 'duration=' → uses max_new_tokens instead.
"""

import os
import time
import numpy as np
from typing import Tuple

import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

from loop_utils import apply_fade_in_out, save_wav, normalize_audio


class MusicGenEngine:
    def __init__(self, model_name: str = "facebook/musicgen-small", device: str = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[MusicGen] Using device: {self.device}")

        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = MusicgenForConditionalGeneration.from_pretrained(
            model_name, torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
        ).to(self.device)

        # Sampling rate from config
        self.sr = getattr(self.model.config, "sample_rate", 32000)

        # MusicGen has a fixed audio frame rate: 50 Hz (20ms per frame)
        # Meaning: each token = ~20ms of audio
        self.tokens_per_second = 50  # Safe default for MusicGen

    def generate(self, prompt: str, seed: int = 42, duration: int = 10) -> Tuple[np.ndarray, int]:
        """
        Generate raw audio based on prompt.
        Duration in seconds → convert to max_new_tokens.
        """

        torch.manual_seed(seed)

        # Convert prompt into input tokens
        inputs = self.processor(
            text=[prompt],
            padding=True,
            return_tensors="pt"
        ).to(self.device)

        # Convert duration → number of tokens MusicGen needs
        max_new_tokens = duration * self.tokens_per_second

        with torch.inference_mode():
            audio_values = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                guidance_scale=3.0,
            )

        audio = audio_values[0, 0].cpu().numpy().astype(np.float32)
        audio = normalize_audio(audio)

        return audio, self.sr


def generate_musicgen_loop(
        prompt: str,
        seed: int,
        duration: int = 12,
        out_path: str = "musicgen_loop.wav",
        model_name: str = "facebook/musicgen-small"
) -> str:

    start = time.time()

    engine = MusicGenEngine(model_name=model_name)
    audio, sr = engine.generate(prompt=prompt, seed=seed, duration=duration)

    # Add fade-in/out for smooth looping
    audio = apply_fade_in_out(audio, sr, fade_ms=400)

    save_wav(out_path, audio, sr)

    print(f"[MusicGen] Generated {duration}s loop -> {out_path} in {time.time() - start:.2f}s")

    return out_path
