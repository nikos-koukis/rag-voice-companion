<div align="center">

# 🎙️ uh.ai

### Semantic Video Search (RAG) + Voice Companion for the Unboxholics

**Ask anything about a creator's videos in natural Greek — get a grounded answer, in the host's cloned voice, and jump straight to the exact second it was said.**

[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js%2014-black)](https://nextjs.org/)
[![Vector DB](https://img.shields.io/badge/Vector%20DB-ChromaDB-ff6b6b)](https://www.trychroma.com/)
[![LLM](https://img.shields.io/badge/LLM-Llama%203.3%2070B%20(Groq)-f55036)](https://groq.com/)
[![Voice](https://img.shields.io/badge/Voice-ElevenLabs-5a31f4)](https://elevenlabs.io/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](#license)

</div>

---

## 📖 Overview

**uh.ai** is a full-stack, retrieval-augmented AI application built around the content of
[**Unboxholics**](https://www.youtube.com/@Unboxholics) — one of the largest Greek
gaming/entertainment YouTube channels. It turns a back-catalogue of long-form videos into a
**conversational, voice-driven knowledge base**.

You ask a question in everyday Greek. The system:

1. **Finds** the most relevant moments across all indexed videos via semantic (vector) search.
2. **Synthesises** a grounded answer in the channel's signature, casual tone ("UH-Bot").
3. **Speaks** the answer back in the **cloned voice** of the host you picked (Σάκης or Αλέκος).
4. **Plays** the source video and **seeks to the exact timestamp** the answer came from.

> The project was built and tested end-to-end against real Unboxholics videos (2026 catalogue,
> 23+ videos / 3,000+ transcript chunks indexed). It is an independent fan/portfolio project and
> is **not affiliated with or endorsed by Unboxholics** — see [Disclaimer](#-disclaimer).

---

## ✨ Key Features

- 🔎 **Semantic video search** — multilingual embeddings over auto-transcribed YouTube content; finds the *right moment* even when it's buried deep inside a 90-minute video.
- 🧠 **Grounded RAG answers** — a custom Greek system prompt makes the model answer **only** from retrieved context, in the community's voice and slang.
- 🗣️ **Voice cloning** — answers are spoken in the host's own (consented, instantly-cloned) voice via ElevenLabs, returned as Base64 and auto-played in the browser.
- ⏱️ **Timestamp deep-linking** — the player opens the source video and jumps to the exact second (with a configurable lead-in).
- 🎭 **Multi-character** — switch between hosts; the answer's tone, avatar, and voice change while the source stays consistent.
- 🧩 **Platform-agnostic core** — YouTube is fully automated today; Instagram / TikTok / X / Facebook are wired into the data model and shown as *"Coming soon"* in the UI.
- 🛡️ **Graceful degradation** — every external dependency (cloud LLM, local LLM, voice) has a fallback, so the app never hard-crashes.
- 🎨 **Premium UI** — dark, cinematic Unboxholics-inspired theme with glassmorphism, animated states, and an in-chat video preview modal.

---

## 🏗️ Architecture

```
                          ┌──────────────────────────────────────────────┐
                          │                FRONTEND (Next.js 14)           │
                          │  Chat UI · character switch · audio autoplay   │
                          │  platform-aware source cards · preview modal   │
                          └───────────────┬──────────────────────────────┘
                                          │  POST /api/ask  { query, voice_character }
                                          ▼
   ┌───────────────────────────────────────────────────────────────────────────────┐
   │                              BACKEND (FastAPI)                                    │
   │                                                                                  │
   │   1. Embed query ─────────────► ChromaDB  (cosine, persistent)                   │
   │      (MiniLM, local)            top-k chunks  ──► ground to single top source     │
   │                                                                                  │
   │   2. RAG synthesis (priority chain):                                             │
   │        Groq Llama-3.3-70B  ──►  local Qwen2.5-1.5B  ──►  extractive fallback      │
   │                                                                                  │
   │   3. Voice: ElevenLabs (multilingual v2, cloned voice) ──► mp3 ──► Base64         │
   └───────────────────────────────────────────────────────────────────────────────┘
                                          ▲
                                          │  INGESTION (offline, one-time per video)
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │  youtube_ingest.py  · batch_ingest.py (channel/playlist, date-filtered)         │
   │  → fetch transcript → smart chunking (time-window + sentence-aware + overlap)    │
   │  → local embeddings → ChromaDB                                                   │
   └──────────────────────────────────────────────────────────────────────────────┘
```

### The RAG pipeline in detail

| Stage | What happens | Why it matters |
|-------|--------------|----------------|
| **Chunking** | Transcripts are split into ~40s windows, never mid-sentence, with 10s overlap. YouTube speaker markers (`>>`) and `[annotations]` are stripped. | Preserves meaning at boundaries and keeps each embedding semantically focused. |
| **Embedding** | `paraphrase-multilingual-MiniLM-L12-v2`, run **locally** (CPU-friendly). | Strong Greek support, zero per-query cost. |
| **Retrieval** | Cosine top-k in ChromaDB, then **grounded to the single best-matching video** so answers never blend two sources. | Eliminates a whole class of "mixed context" hallucinations. |
| **Synthesis** | Greek "UH-Bot" system prompt with strict grounding rules + a style-only one-shot example. | Coherent, on-brand answers from noisy auto-caption text. |
| **Voice** | Text → ElevenLabs (`eleven_multilingual_v2`) → mp3 → Base64 → browser autoplay. | Natural Greek TTS in the host's actual voice. |

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python · FastAPI · Uvicorn · Pydantic |
| **Vector DB** | ChromaDB (local, persistent, cosine) |
| **Embeddings** | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (local) |
| **LLM (synthesis)** | Groq `llama-3.3-70b-versatile` (primary) → local `Qwen2.5-1.5B-Instruct` → extractive fallback |
| **Voice** | ElevenLabs API (instant voice cloning, multilingual v2) |
| **Frontend** | Next.js 14 (App Router) · TypeScript · TailwindCSS · lucide-react |
| **Media** | YouTube IFrame embed with timestamp seeking |
| **Ingestion** | `youtube-transcript-api` · `yt-dlp` + `ffmpeg` (voice-sample prep) |

---

## 🤖 AI Engineering Highlights

These are the design decisions that make the project interesting beyond "calling an LLM":

- **Hybrid local + cloud inference.** Embeddings and an optional fallback LLM run locally; the heavy synthesis runs on a 70B cloud model. When a cloud key is present, the local model isn't even loaded — saving RAM and startup time.
- **Three-tier answer fallback** (`cloud → local → extractive`) means the app produces *something* truthful even with no GPU, no disk, or no API keys.
- **Retrieval grounding** to a single source prevents cross-video contamination — a subtle but high-impact correctness fix discovered through iterative testing.
- **Prompt hardening** against few-shot leakage: an early version copied facts from the in-prompt example; the fix uses a deliberately off-topic, style-only example plus explicit anti-copy instructions.
- **Transcription realism.** Greek auto-captions are noisy; the chunker cleans them and the prompt is tuned to "make sense of imperfect text" rather than refuse.
- **Polite, resilient ingestion.** Batch ingestion handles channel/playlist expansion, date filtering (newest-first early-stop), rate-limit backoff via delays, and persists failed IDs for one-command retry.

---

## 📂 Project Structure

```
uh.ai/
├── backend/
│   ├── main.py                  # FastAPI app: /api/ask, /api/ingest, /api/sources, /api/reset, /api/health
│   ├── youtube_ingest.py        # Single-video transcript ingestion + smart chunker
│   ├── batch_ingest.py          # Channel/playlist batch ingest (date filter, delays, retry file)
│   ├── ingest_text.py           # Universal ingester for any platform from raw text
│   ├── prepare_voice_sample.py  # yt-dlp + ffmpeg → clean voice-clone samples
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── page.tsx             # Full chat UI, character switch, audio, preview modal
    │   ├── layout.tsx
    │   └── globals.css          # Cinematic theme + animations
    ├── public/images/          # Character avatars (sakis.jpg, alekos.jpg)
    └── package.json
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+ · Node.js 18+
- (Optional) [Groq API key](https://console.groq.com) — recommended for best answer quality
- (Optional) [ElevenLabs API key](https://elevenlabs.io) — for voice
- (Optional) `ffmpeg` — only for preparing voice-clone samples

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # fish: source .venv/bin/activate.fish
pip install -r requirements.txt

cp .env.example .env                 # add your keys (all optional)
uvicorn main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/api/health`

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local     # points to http://localhost:8000
npm run dev                          # http://localhost:3000
```

### 3. Index some videos

```bash
# A single video
python youtube_ingest.py "https://www.youtube.com/watch?v=VIDEO_ID"

# A whole channel, only 2026 uploads, politely rate-limited
python batch_ingest.py --playlist "https://www.youtube.com/@Unboxholics/videos" \
    --after 20260101 --delay 4

# See what's indexed
curl http://localhost:8000/api/sources
```

---

## 🔧 Configuration (`backend/.env`)

```ini
# Cloud LLM (recommended) — free tier at console.groq.com
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

# Voice (optional) — instant voice cloning at elevenlabs.io
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_SAKIS=
ELEVENLABS_VOICE_ALEKOS=

# Local model / storage
UH_LLM_MODEL=Qwen/Qwen2.5-1.5B-Instruct
UH_CHROMA_DIR=./chroma_store
```

Everything is optional. With **no keys**, the app still runs: local embeddings + local/extractive
answers + silent (no-audio) mode.

---

## 🎙️ Voice Cloning Workflow

```bash
# 1. Extract a clean 1–3 min sample of a single speaker
python prepare_voice_sample.py "https://youtu.be/VIDEO_ID" --start 02:09 --end 04:00 --out sakis

# 2. Upload backend/voice_samples/sakis.mp3 to ElevenLabs → Instant Voice Cloning
# 3. Copy the Voice ID into .env (ELEVENLABS_VOICE_SAKIS=...) and restart
```

> ⚠️ Clone voices **only with the consent of the person** — ElevenLabs requires this, and so should you.

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/ask` | `{ query, voice_character }` → `{ answer, platform, source_id, url, title, timestamp, audio_base64 }` |
| `POST` | `/api/ingest` | Platform-agnostic ingest of `{ source_id, platform, url, title, chunks[] }` |
| `GET`  | `/api/sources` | Lists indexed sources with chunk counts |
| `POST` | `/api/reset` | Wipes the vector store (dev utility) |
| `GET`  | `/api/health` | Status: active LLM backend, voice availability, indexed docs |

---

## ⚖️ Honest Limitations

- **Transcripts:** only YouTube provides automatic captions. Other platforms require you to supply text (or use speech-to-text). Many videos may have subtitles disabled.
- **Timestamp seek** is a YouTube feature; other platforms' embeds open without seeking.
- **Small local model** struggles with noisy Greek auto-captions — this is exactly why the cloud 70B path exists and is recommended.
- **Rate limits:** bulk transcript fetching can trigger temporary IP throttling from YouTube; the batch tool mitigates this with delays and retry files.
- **Voice** requires an active ElevenLabs plan to *generate* audio (the cloned voice ID itself is permanent).

---

## 🗺️ Roadmap

- [ ] Whisper-based transcription for caption-less / non-YouTube content
- [ ] Official Instagram / TikTok API ingestion (owner content)
- [ ] Streaming answers + streaming TTS
- [ ] Source citations with multiple timestamps per answer
- [ ] Deployment (containerized backend + hosted frontend)

---

## 🙏 Acknowledgements

- **[Unboxholics](https://www.youtube.com/@Unboxholics)** — the Greek YouTube channel whose content this project was built and tested on. All video content and the hosts' voices/likenesses belong to them.
- [Groq](https://groq.com/), [ElevenLabs](https://elevenlabs.io/), [ChromaDB](https://www.trychroma.com/), [Hugging Face](https://huggingface.co/), [yt-dlp](https://github.com/yt-dlp/yt-dlp), and [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api).

---

## ⚠️ Disclaimer

This is an **independent, non-commercial portfolio project** and is **not affiliated with,
sponsored by, or endorsed by Unboxholics**. It is intended as a technical demonstration of
RAG, semantic search, and voice AI. All third-party video content, trademarks, names, and
voice likenesses remain the property of their respective owners. Voice cloning was performed
for demonstration purposes and should only ever be done with explicit consent.

## License

[MIT](LICENSE) — code only. Third-party content and likenesses are excluded.

---

<div align="center">
Built with ❤️ as a full-stack AI engineering showcase.
</div>
