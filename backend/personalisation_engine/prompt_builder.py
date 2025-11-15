# prompt_builder.py
# Module 2 -- builds a natural-language prompt string for MusicGen / Riffusion
# Usage: from prompt_builder import build_prompt

import json

# ---------- helper mappings ----------
INSTRUMENT_TO_TEXT = {
    "warm_pad": "warm ambient pad",
    "soft_piano": "soft felt piano",
    "ethereal_pad": "ethereal synth pad",
    "bright_pluck": "bright plucked synth",
    "pad": "soft ambient pad",
    "soft_pluck": "soft plucked motif",
    "low_sub_bass": "subtle low bass",
}

TEXTURE_TO_DESC = {
    "sparse": "very sparse texture, minimal melodic motion",
    "medium": "moderately textured arrangement",
    "rich": "rich layered textures with gentle movement",
}

TIMBRE_TO_DESC = {
    "dark": "dark, low-frequency-focused timbre",
    "warm": "warm, rounded timbre with soft high-end",
    "bright": "bright timbre with clear high-end presence",
}

INTENT_TO_GUIDE = {
    "calming": "emphasize de-escalating, grounding qualities; avoid sudden attacks; slow evolution",
    "comforting": "soft, comforting, slow harmonic motion; emphasize sustain",
    "uplifting": "gentle uplift—positive harmonic colors, gentle rhythmic drive",
    "stabilizing": "neutral, stable, unobtrusive background support",
}

# ---------- CORE FUNCTION ----------
def build_prompt(params: dict, user_profile: dict = None) -> str:
    """
    params: output from mapper.map_emotion_to_params
    user_profile: optional (to push avoid/emphasize lists)
    returns: string prompt ready to pass to a generative model
    """
    intent = params.get("intent", "stabilizing")
    bpm = params.get("bpm", 60)
    timbre = params.get("timbre", "warm")
    texture = params.get("texture", "sparse")
    instruments = params.get("instruments", [])
    avoid_instruments = set(params.get("avoid_instruments", []))
    mode = params.get("mode", "modal")
    tension = params.get("harmonic_tension", 0.1)
    seed = params.get("seed", None)

    # incorporate user_profile hints
    if user_profile:
        # user_profile may contain 'avoid' and 'prefer' lists
        avoid_instruments.update(user_profile.get("avoid", []))
        preferred = user_profile.get("preferred_instruments", [])
    else:
        preferred = []

    # textual instrument list (prioritize preferred)
    inst_order = preferred + [i for i in instruments if i not in preferred]
    inst_desc = []
    for inst in inst_order:
        if inst in avoid_instruments:
            continue
        inst_desc.append(INSTRUMENT_TO_TEXT.get(inst, inst.replace("_", " ")))

    inst_str = ", ".join(inst_desc) if inst_desc else "soft ambient pad"

    # build prompt
    prompt_parts = []
    prompt_parts.append(f"{INTENT_TO_GUIDE.get(intent)}.")
    prompt_parts.append(f"Create a {intent} loop at {bpm} bpm, {TIMBRE_TO_DESC.get(timbre)}.")
    prompt_parts.append(f"{TEXTURE_TO_DESC.get(texture)}.")
    prompt_parts.append(f"Instrumentation: {inst_str}.")
    prompt_parts.append(f"Harmonic mode: {mode}, harmonic tension: {tension:.2f}.")
    if avoid_instruments:
        prompt_parts.append(f"Avoid: {', '.join(avoid_instruments)}.")
    # seed hint (useful for deterministic generators)
    if seed is not None:
        prompt_parts.append(f"Use seed {seed} for reproducibility.")
    # final polishing
    prompt = " ".join(prompt_parts)
    # keep prompt short and clear (generators prefer 1-3 sentences)
    return prompt

# ---------- demo ----------
if __name__ == "__main__":
    example_params = {
        "intent": "calming",
        "bpm": 58,
        "timbre": "warm",
        "texture": "sparse",
        "instruments": ["warm_pad", "soft_piano"],
        "avoid_instruments": ["bright_synth"],
        "mode": "modal",
        "harmonic_tension": 0.12,
        "seed": 12345
    }
    print(build_prompt(example_params))
