FROM python:3.11-slim

# libgomp1: requerido por onnxruntime (backend de inferencia de Piper).
# curl: para descargar el modelo de voz en build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir piper-tts==1.2.0 flask

# Voces español LATAM (México). Piper no publica es_CO.
# - es_MX-ald-medium: voz original, sigue siendo la voz por defecto.
# - es_MX-claude-high: voz elegida en la comparación A/B de oct 2026.
ARG VOICE_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX
RUN mkdir -p /voices \
    && for v in ald/medium/es_MX-ald-medium claude/high/es_MX-claude-high; do \
         n="$(basename "$v")"; \
         curl -fsSL "${VOICE_BASE}/${v}.onnx" -o "/voices/${n}.onnx" \
         && curl -fsSL "${VOICE_BASE}/${v}.onnx.json" -o "/voices/${n}.onnx.json" || exit 1; \
       done

# piper-tts==1.2.0 (el paquete pip) no trae `piper.http_server` — solo expone
# la CLI y la clase PiperVoice. app.py es un wrapper Flask propio que lee
# `text` (y opcionalmente `voice`, `length_scale` y `sentence_silence`) del
# query (GET) o del cuerpo (POST) y responde audio/wav.
COPY app.py /app.py

EXPOSE 5000

CMD ["python", "/app.py"]
