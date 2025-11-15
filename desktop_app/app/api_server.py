"""
api_server.py — Local API for Person D
Run this first:
    python api_server.py
"""

from flask import Flask, jsonify, render_template
import base64
import io
from pydub import AudioSegment

# Try to import CORS (optional)
try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False

app = Flask(__name__, template_folder="templates", static_folder="static")

# Enable CORS if available
if CORS_AVAILABLE:
    CORS(app)


# ---- STUBS (replace later with Person A/B/C) ----

def call_person_a():
    return {"emotion": "calm", "valence": 0.5, "arousal": 0.2}


def call_person_c(emotion):
    return {"prompt": "soft ambient pad", "seed": 42}


def call_person_b(prompt, seed):
    seg = AudioSegment.silent(duration=2000)
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    buf.seek(0)
    return buf.read()


@app.route("/")
def index_page():
    return render_template("ui.html")


@app.route("/api/process")
def process():
    try:
        emotion = call_person_a()
        gen = call_person_c(emotion)
        audio = call_person_b(gen["prompt"], gen["seed"])
        audio_b64 = base64.b64encode(audio).decode()

        return jsonify({
            "emotion": emotion,
            "prompt": gen["prompt"],
            "seed": gen["seed"],
            "audio_b64": audio_b64
        })
    except Exception as e:
        # Return error response instead of crashing
        return jsonify({
            "error": str(e),
            "emotion": None,
            "prompt": None,
            "seed": None,
            "audio_b64": None
        }), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)
