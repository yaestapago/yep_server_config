import io
import wave

from flask import Flask, Response, request
from piper.voice import PiperVoice

MODEL_PATH = "/voices/es_MX-ald-medium.onnx"
CONFIG_PATH = "/voices/es_MX-ald-medium.onnx.json"

app = Flask(__name__)
voice = PiperVoice.load(MODEL_PATH, CONFIG_PATH)


@app.route("/", methods=["GET", "POST"])
def synthesize():
    text = request.values.get("text", "")
    if not text.strip():
        return "Missing 'text' parameter", 400

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize(text, wav_file)

    return Response(buf.getvalue(), mimetype="audio/wav")


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
