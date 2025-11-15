# engine_api.py
"""
Public API for Person B.
Call generate_loop(prompt, seed, engine='musicgen'|'riffusion', duration=12, out_path='loop.wav')
"""

import os
from typing import Optional

# Import the engine functions; if modules are missing, the import will raise when called.
from music_engine import generate_musicgen_loop
from riffusion_engine import generate_riffusion_loop


def generate_loop(prompt: str, seed: int = 42, engine: str = "musicgen", duration: int = 12, out_path: Optional[str] = None) -> str:
    """
    Generate a loop using the chosen engine.
    engine: 'musicgen' or 'riffusion'
    duration: seconds
    out_path: path to write the wav file (defaults to ./generated_{engine}.wav)
    Returns: path to output wav
    """
    if out_path is None:
        out_path = f"generated_{engine}.wav"

    engine = engine.lower()
    if engine == "musicgen":
        return generate_musicgen_loop(prompt=prompt, seed=seed, duration=duration, out_path=out_path)
    elif engine == "riffusion":
        return generate_riffusion_loop(prompt=prompt, seed=seed, duration=duration, out_path=out_path)
    else:
        raise ValueError(f"Unknown engine '{engine}'. Choose 'musicgen' or 'riffusion'.")


if __name__ == "__main__":
    # Quick smoke test (edit prompt as needed). This requires the models and dependencies installed.
    demo_prompt = "Calming ambient pad with warm piano, low tempo, soft texture, supportive, no harsh percussion."
    print("Generating demo loop (this will take GPU/CPU time)...")
    out = generate_loop(demo_prompt, seed=1234, engine="musicgen", duration=12, out_path="demo_musicgen.wav")
    print("Wrote:", out)
