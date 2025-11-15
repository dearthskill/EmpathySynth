# mapper.py
# Module 1 -- deterministic rule engine: emotion_data -> music parameters
# Usage: from mapper import Module1State, map_emotion_to_params

import math
import hashlib
from collections import deque

# ---------- CONFIG ----------
SMOOTH_WINDOW = 2
CONFIDENCE_MICRO = 0.45
STRESS_INDEX_OVERRIDE = 0.65
PERSISTENCE_REQUIRED = 2
COOLDOWN_FULL_CYCLES = 1
JITTER_BPM = 6

BPM_LOW = (45, 60)
BPM_MID = (61, 80)
BPM_HIGH = (81, 110)

TIMBRE_VALENCE_WEIGHT = 0.6
TIMBRE_AROUSAL_WEIGHT = 0.3
TIMBRE_STRESS_WEIGHT = 0.5

DELTA_FULL_THRESHOLD = 0.25
DELTA_LAYER_THRESHOLD = 0.10

# ---------- UTILITIES ----------
def clamp(x, a, b):
    return max(a, min(b, x))

def deterministic_seed(user_id: str, cycle_index: int):
    h = hashlib.sha256(f"{user_id}:{cycle_index}".encode()).hexdigest()
    return int(h[:16], 16) & 0xFFFFFFFF

def jitter_bpm(base, seed, jitter=JITTER_BPM):
    r = (seed % 1000) / 1000.0
    return int(base + math.floor(r * jitter))

# ---------- STATE HOLDER ----------
class Module1State:
    def __init__(self, user_id="user", window=SMOOTH_WINDOW):
        self.user_id = user_id
        self.window = window
        self.valence_hist = deque(maxlen=window)
        self.arousal_hist = deque(maxlen=window)
        self.intensity_hist = deque(maxlen=window)
        self.aus_hist = deque(maxlen=window)
        self.last_params = None
        self.cycle_index = 0
        self.full_cooldown = 0
        self.intent_history = deque(maxlen=4)

    def push(self, emotion_data):
        self.valence_hist.append(emotion_data["valence"])
        self.arousal_hist.append(emotion_data["arousal"])
        self.intensity_hist.append(emotion_data.get("intensity", 0.0))
        self.aus_hist.append(emotion_data.get("aus", {}))
        self.cycle_index += 1
        if self.full_cooldown > 0:
            self.full_cooldown -= 1

    def smoothed(self):
        def mean_hist(dq):
            if not dq:
                return 0.0
            return sum(dq) / len(dq)
        aus_agg = {}
        if self.aus_hist:
            keys = set().union(*[set(a.keys()) for a in self.aus_hist if isinstance(a, dict)])
            for k in keys:
                vals = [a.get(k, 0.0) for a in self.aus_hist]
                aus_agg[k] = sum(vals) / len(vals)
        return {
            "valence": mean_hist(self.valence_hist),
            "arousal": mean_hist(self.arousal_hist),
            "intensity": mean_hist(self.intensity_hist),
            "aus": aus_agg
        }

# ---------- CORE FUNCTION ----------
def map_emotion_to_params(emotion_data: dict, state: Module1State, user_profile=None):
    """
    Input (emotion_data):
      - emotion (label)
      - valence (-1..1)
      - arousal (0..1)
      - intensity (0..1)
      - aus: dict (AU floats 0..1)
      - confidence (0..1)
    Returns parameter dict:
      {
        "decision_level": "micro|layer|full",
        "intent": ...,
        "bpm": int,
        "mode": "major|minor|modal",
        "timbre": "dark|warm|bright",
        "texture": "sparse|medium|rich",
        "instruments": [...],
        "avoid_instruments": [...],
        "harmonic_tension": float,
        "seed": int,
        "meta": {...}
      }
    """
    # clamp & read
    valence = clamp(float(emotion_data.get("valence", 0.0)), -1.0, 1.0)
    arousal = clamp(float(emotion_data.get("arousal", 0.0)), 0.0, 1.0)
    intensity = clamp(float(emotion_data.get("intensity", 0.0)), 0.0, 1.0)
    aus = emotion_data.get("aus", {}) or {}
    confidence = clamp(float(emotion_data.get("confidence", 1.0)), 0.0, 1.0)
    label = emotion_data.get("emotion", "neutral")

    # smoothing state
    state.push({"valence": valence, "arousal": arousal, "intensity": intensity, "aus": aus})
    sm = state.smoothed()
    svalence, sarousal, sintensity, saus = sm["valence"], sm["arousal"], sm["intensity"], sm["aus"]

    # AU indicators
    au4 = saus.get("AU4", aus.get("AU4", 0.0))
    au7 = saus.get("AU7", aus.get("AU7", 0.0))
    au12 = saus.get("AU12", aus.get("AU12", 0.0))
    stress_index = max(au4, au7)
    genuine_smile = au12 > 0.4

    # confidence short-circuit
    if confidence < CONFIDENCE_MICRO:
        decision_level = "micro"
        params = {
            "decision_level": decision_level,
            "intent": "stabilizing",
            "bpm": jitter_bpm(56, deterministic_seed(state.user_id, state.cycle_index)),
            "timbre": "warm",
            "texture": "sparse",
            "instruments": ["warm_pad"],
            "avoid_instruments": [],
            "mode": "modal",
            "harmonic_tension": 0.1,
            "seed": deterministic_seed(state.user_id, state.cycle_index),
            "meta": {"reason": "low_confidence", "confidence_used": confidence}
        }
        state.last_params = params
        return params

    # intent decision (priority)
    if stress_index > STRESS_INDEX_OVERRIDE or (svalence < -0.25 and sarousal > 0.5):
        intent = "calming"
    elif svalence > 0.4 and sarousal > 0.5:
        intent = "uplifting"
    elif svalence < -0.4 and sarousal <= 0.5:
        intent = "comforting"
    else:
        intent = "stabilizing"

    # BPM mapping
    if sarousal <= 0.25:
        base_bpm = int((BPM_LOW[0] + BPM_LOW[1]) / 2)
    elif sarousal <= 0.55:
        base_bpm = 60
    else:
        base_bpm = 78
    if intent == "calming" and base_bpm > 70:
        base_bpm = int((base_bpm + 60) / 2)

    seed = deterministic_seed(state.user_id, state.cycle_index)
    bpm = jitter_bpm(base_bpm, seed)

    # timbre mapping
    timbre_score = svalence * TIMBRE_VALENCE_WEIGHT - sarousal * TIMBRE_AROUSAL_WEIGHT - stress_index * TIMBRE_STRESS_WEIGHT
    if timbre_score <= -0.3:
        timbre = "dark"
    elif timbre_score <= 0.1:
        timbre = "warm"
    else:
        timbre = "bright"
    if stress_index > 0.6 and timbre == "bright":
        timbre = "warm"

    # texture mapping
    density_score = sarousal * 0.7 + sintensity * 0.3
    if density_score <= 0.25:
        texture = "sparse"
    elif density_score <= 0.6:
        texture = "medium"
    else:
        texture = "rich"
    if intent == "calming" and texture == "rich":
        texture = "medium"

    # instruments selection
    avoid_instruments = set()
    instruments = []
    if intent == "calming":
        instruments = ["warm_pad", "soft_piano"]
        avoid_instruments.update(["bright_synth", "aggressive_drums"])
    elif intent == "comforting":
        instruments = ["piano", "ethereal_pad"]
        avoid_instruments.update(["bright_synth"])
    elif intent == "uplifting":
        instruments = ["bright_pluck", "warm_pad"]
    else:
        instruments = ["pad", "soft_pluck"]

    # AU overrides
    if au4 > 0.6:
        timbre = "warm" if timbre == "bright" else timbre
    if au7 > 0.6:
        avoid_instruments.update(["drums", "aggressive_drums"])
    if au12 > 0.55 and svalence < 0:
        if timbre == "bright":
            timbre = "warm"

    # harmonic mode & tension
    if svalence >= 0.2:
        mode = "major"
    elif svalence <= -0.2:
        mode = "minor"
    else:
        mode = "modal"
    harmonic_tension = clamp((1 - svalence) * sintensity, 0.0, 1.0)

    # decision level (compare with last history)
    decision_level = "micro"
    reason = ""
    if state.last_params:
        last_val = state.valence_hist[-2] if len(state.valence_hist) >= 2 else None
        last_aro = state.arousal_hist[-2] if len(state.arousal_hist) >= 2 else None
        if last_val is not None and last_aro is not None:
            delta_val = abs(svalence - last_val)
            delta_aro = abs(sarousal - last_aro)
            max_delta = max(delta_val, delta_aro)
            if max_delta > DELTA_FULL_THRESHOLD and state.full_cooldown == 0:
                state.intent_history.append(intent)
                if list(state.intent_history).count(intent) >= PERSISTENCE_REQUIRED:
                    decision_level = "full"
                    state.full_cooldown = COOLDOWN_FULL_CYCLES
                    reason = "large_delta_with_persistence"
                else:
                    decision_level = "layer"
                    reason = "large_delta_no_persistence"
            elif max_delta > DELTA_LAYER_THRESHOLD:
                decision_level = "layer"
                reason = "moderate_delta"
            else:
                decision_level = "micro"
                reason = "small_delta"
        else:
            decision_level = "micro"
            reason = "no_history"
    else:
        if stress_index > STRESS_INDEX_OVERRIDE:
            decision_level = "layer"
            reason = "initial_stress"
        else:
            decision_level = "layer"
            reason = "initial_cycle"

    params = {
        "decision_level": decision_level,
        "intent": intent,
        "bpm": bpm,
        "mode": mode,
        "timbre": timbre,
        "texture": texture,
        "instruments": instruments,
        "avoid_instruments": list(avoid_instruments),
        "harmonic_tension": round(harmonic_tension, 3),
        "seed": seed,
        "meta": {"reason": reason, "confidence_used": confidence, "stress_index": round(stress_index, 3)}
    }

    state.last_params = params
    return params

# ---------- quick demo ----------
if __name__ == "__main__":
    s = Module1State(user_id="demo_user")
    sample = {"emotion": "angry", "valence": -0.63, "arousal": 0.74, "intensity": 0.55, "aus": {"AU4": 0.78, "AU7": 0.60, "AU12": 0.10}, "confidence": 0.9}
    print(map_emotion_to_params(sample, s))
