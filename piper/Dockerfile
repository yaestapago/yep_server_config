FROM python:3.11-slim

# libgomp1: requerido por onnxruntime (backend de inferencia de Piper).
# curl: para descargar el modelo de voz en build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir piper-tts==1.2.0 flask

# Voz español LATAM (México, calidad media). Piper no publica es_CO.
ARG VOICE=es_MX-ald-medium
ARG VOICE_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium
RUN mkdir -p /voices \
    && curl -fsSL "${VOICE_BASE}/${VOICE}.onnx" -o "/voices/${VOICE}.onnx" \
    && curl -fsSL "${VOICE_BASE}/${VOICE}.onnx.json" -o "/voices/${VOICE}.onnx.json"

# piper-tts==1.2.0 (el paquete pip) no trae `piper.http_server` — solo expone
# la CLI y la clase PiperVoice. app.py es un wrapper Flask propio que lee
# `text` del query (GET) o del cuerpo (POST) y responde audio/wav.
COPY app.py /app.py

EXPOSE 5000

CMD ["python", "/app.py"]
