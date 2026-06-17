# uh.ai backend — FastAPI + ChromaDB + local embeddings
FROM python:3.11-slim

# ffmpeg προαιρετικό (μόνο για prepare_voice_sample· δεν χρειάζεται στο serving)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) CPU-only torch (αποφεύγει τα τεράστια CUDA wheels — ιδανικό για VPS χωρίς GPU)
RUN pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu

# 2) Υπόλοιπες εξαρτήσεις (το torch είναι ήδη satisfied, δεν ξανακατεβαίνει)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Κώδικας
COPY . .

EXPOSE 8000

# Healthcheck στο /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
