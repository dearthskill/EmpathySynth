# reward_engine.py
# Module 3 -- reward computation and profile updating (no heavy ML)
# Usage:
#   from reward_engine import RewardEngine
#   engine = RewardEngine()
#   R = engine.compute_reward(delta_valence, delta_arousal, behavior, intent)
#   engine.update_profile(profile, params_used, R)

import math
import json
from collections import defaultdict

# ---------- CONFIG ----------
W_VALENCE = 0.6
W_AROUSAL = 0.2
W_BEHAVIOR = 0.2

ALPHA = 0.25  # learning rate for score updates
EPSILON_START = 0.25
EPSILON_DECAY = 0.98
EPSILON_MIN = 0.05

NEGATIVE_BAN_THRESHOLD = -0.7  # if score falls below this after update mark as temp avoid
BAN_CYCLES = 6

# ---------- helper ----------
def clamp(x, a, b): return max(a, min(b, x))

# ---------- RewardEngine ----------
class RewardEngine:
    def __init__(self):
        self.epsilon = EPSILON_START
        # track attribute bans: name -> remaining cycles
        self.bans = {}

    def compute_reward(self, delta_valence, delta_arousal, behavior, intent="calming"):
        """
        delta_valence: valence_after - valence_before  (range roughly -1..1)
        delta_arousal: arousal_after - arousal_before  (range roughly -1..1)
        behavior: -1 (negative action: stop/mute), 0 (neutral), +1 (kept/listened)
        intent: if intent == 'calming', a decrease in arousal is beneficial (so we use -delta_arousal)
        """
        dv = clamp(delta_valence, -1.0, 1.0)
        da = clamp(delta_arousal, -1.0, 1.0)
        arousal_term = -da if intent == "calming" else -da  # for now, reduce arousal is always good for calming
        R = W_VALENCE * dv + W_AROUSAL * arousal_term + W_BEHAVIOR * behavior
        R = clamp(R, -1.0, 1.0)
        return R

    def update_profile(self, profile: dict, params_used: dict, reward: float):
        """
        profile structure (example):
        {
          "instrument_scores": {"piano": 0.0, ...},
          "timbre_scores": {"warm": 0.0, ...},
          "tempo_scores": {"low": 0.0, ...},
          "texture_scores": {"sparse": 0.0, ...},
          "avoid": [],
          "seed_bias": 0
        }
        params_used: dict returned from mapper (contains instruments, timbre, texture, bpm)
        reward: float in [-1,1]
        """
        # initialize dicts if missing
        for key in ["instrument_scores", "timbre_scores", "tempo_scores", "texture_scores"]:
            if key not in profile:
                profile[key] = defaultdict(float)

        # update instrument scores
        instruments = params_used.get("instruments", [])
        for inst in instruments:
            old = profile["instrument_scores"].get(inst, 0.0)
            profile["instrument_scores"][inst] = clamp(old * (1 - ALPHA) + ALPHA * reward, -1.0, 1.0)

        # update timbre score
        timbre = params_used.get("timbre", None)
        if timbre:
            old = profile["timbre_scores"].get(timbre, 0.0)
            profile["timbre_scores"][timbre] = clamp(old * (1 - ALPHA) + ALPHA * reward, -1.0, 1.0)

        # update texture
        texture = params_used.get("texture", None)
        if texture:
            old = profile["texture_scores"].get(texture, 0.0)
            profile["texture_scores"][texture] = clamp(old * (1 - ALPHA) + ALPHA * reward, -1.0, 1.0)

        # update tempo bucket (simple bucketization)
        bpm = params_used.get("bpm", 60)
        if bpm <= 60: bucket = "low"
        elif bpm <= 80: bucket = "mid"
        else: bucket = "high"
        old = profile["tempo_scores"].get(bucket, 0.0)
        profile["tempo_scores"][bucket] = clamp(old * (1 - ALPHA) + ALPHA * reward, -1.0, 1.0)

        # handle strong negatives -> temporary ban
        # compute average score across updated attributes to decide banning
        scores = []
        for inst in instruments:
            scores.append(profile["instrument_scores"].get(inst, 0.0))
        if timbre:
            scores.append(profile["timbre_scores"].get(timbre, 0.0))
        avg_score = sum(scores) / len(scores) if scores else 0.0
        if avg_score <= NEGATIVE_BAN_THRESHOLD:
            # ban instruments and timbre for BAN_CYCLES
            for inst in instruments:
                profile.setdefault("avoid", [])
                if inst not in profile["avoid"]:
                    profile["avoid"].append(inst)
            if timbre:
                profile.setdefault("avoid", [])
                if timbre not in profile["avoid"]:
                    profile["avoid"].append(timbre)

        # decay epsilon
        self.epsilon = max(EPSILON_MIN, self.epsilon * EPSILON_DECAY)
        return profile

    def should_explore(self):
        import random
        return random.random() < self.epsilon

# ---------- quick demo ----------
if __name__ == "__main__":
    # example
    engine = RewardEngine()
    profile = {
        "instrument_scores": {},
        "timbre_scores": {},
        "tempo_scores": {},
        "texture_scores": {},
        "avoid": [],
        "seed_bias": 0
    }
    params_used = {"instruments": ["soft_piano", "warm_pad"], "timbre": "warm", "texture": "sparse", "bpm": 56}
    R = engine.compute_reward(delta_valence=0.12, delta_arousal=-0.08, behavior=1, intent="calming")
    updated = engine.update_profile(profile, params_used, R)
    print("R=", R)
    print("profile after update:", json.dumps(updated, indent=2))
