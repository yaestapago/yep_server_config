import io
import os
import wave

from flask import Flask, Response, request
from piper.voice import PiperVoice

VOICES_DIR = "/voices"
# Sin `voice` en la petición se usa esta voz: así los backends que no la envían
# (prod hoy) siguen oyendo exactamente lo mismo que antes.
DEFAULT_VOICE = os.environ.get("PIPER_DEFAULT_VOICE", "es_MX-ald-medium")
LENGTH_SCALE_RANGE = (0.5, 2.0)
SENTENCE_SILENCE_MAX = 1.0


def load_voices():
    voices = {}
    for name in sorted(os.listdir(VOICES_DIR)):
        if name.endswith(".onnx"):
            voice_id = name[: -len(".onnx")]
            path = os.path.join(VOICES_DIR, name)
            voices[voice_id] = PiperVoice.load(path, path + ".json")
    return voices


app = Flask(__name__)
voices = load_voices()
if DEFAULT_VOICE not in voices:
    raise RuntimeError(f"Voz por defecto '{DEFAULT_VOICE}' no está en {VOICES_DIR}")


@app.route("/", methods=["GET", "POST"])
def synthesize():
    text = request.values.get("text", "")
    if not text.strip():
        return "Missing 'text' parameter", 400

    voice_id = request.values.get("voice") or DEFAULT_VOICE
    voice = voices.get(voice_id)
    if voice is None:
        return f"Unknown voice '{voice_id}'", 400

    length_scale = None
    raw_scale = request.values.get("length_scale")
    if raw_scale:
        try:
            length_scale = float(raw_scale)
        except ValueError:
            return "Invalid 'length_scale'", 400
        if not LENGTH_SCALE_RANGE[0] <= length_scale <= LENGTH_SCALE_RANGE[1]:
            return "Out of range 'length_scale'", 400

    sentence_silence = 0.0
    raw_silence = request.values.get("sentence_silence")
    if raw_silence:
        try:
            sentence_silence = float(raw_silence)
        except ValueError:
            return "Invalid 'sentence_silence'", 400
        if not 0.0 <= sentence_silence <= SENTENCE_SILENCE_MAX:
            return "Out of range 'sentence_silence'", 400

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize(
            text,
            wav_file,
            length_scale=length_scale,
            sentence_silence=sentence_silence,
        )

    return Response(buf.getvalue(), mimetype="audio/wav")


@app.route("/health")
def health():
    return "ok"


@app.route("/voices")
def list_voices():
    return {"default": DEFAULT_VOICE, "voices": sorted(voices)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
