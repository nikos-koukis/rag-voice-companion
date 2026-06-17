# 🚀 Deployment Guide — uh.ai

**Architecture:** Backend (FastAPI + ChromaDB) on a self-hosted **VPS (Contabo)** via Docker +
Caddy (auto-HTTPS); Frontend (Next.js) on **Vercel**. Ingestion runs **from your local machine**
(YouTube blocks datacenter IPs).

```
  Browser ──► Vercel (Next.js)  ──HTTPS──►  api.yourdomain.com (Caddy ─► FastAPI on VPS)
                                                   │
  Your laptop ──(ingest scripts, --api)────────────┘   (transcripts fetched from home IP)
```

---

## Prerequisites

- A domain (or subdomain) you control, e.g. `api.yourdomain.com`
- Contabo VPS (Ubuntu 22.04/24.04), SSH access
- Groq API key (recommended) and ElevenLabs key (optional, for voice)
- The repo pushed to GitHub

---

## PART A — Backend on the VPS

### 1. DNS
Create an **A record**: `api.yourdomain.com → <VPS_IP>`. Wait for it to resolve
(`ping api.yourdomain.com` shows the VPS IP). Caddy needs this for the TLS certificate.

### 2. SSH in & install Docker
```bash
ssh root@<VPS_IP>

apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh           # installs Docker + compose plugin
docker --version && docker compose version
```

### 3. Firewall
```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
```
> Do **not** expose port 8000 — Caddy proxies to it internally over the Docker network.

### 4. Clone the repo
```bash
cd /opt
git clone https://github.com/nikos-koukis/rag-voice-companion.git uh.ai
cd uh.ai
```

### 5. Configure secrets
```bash
cp backend/.env.example backend/.env
nano backend/.env
```
Set:
```ini
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_SAKIS=...
ELEVENLABS_VOICE_ALEKOS=...
# IMPORTANT: your Vercel URL(s), comma-separated (no trailing slash)
UH_ALLOWED_ORIGINS=https://uh-ai.vercel.app
```

### 6. Set your domain in the Caddyfile
```bash
nano Caddyfile      # replace api.yourdomain.com with your real subdomain
```

### 7. Launch
```bash
docker compose up -d --build
docker compose logs -f backend     # first boot downloads the embedding model (~450MB)
```
Wait until you see `Application startup complete.`

### 8. Verify
```bash
curl https://api.yourdomain.com/api/health
# {"status":"ok","llm_backend":"groq:...","groq":true,...}
```
HTTPS works automatically (Caddy issued the certificate). ✅

### 9. Index videos (run LOCALLY, not on the VPS)
On **your laptop** (datacenter IPs get YouTube-blocked):
```bash
cd backend
source .venv/bin/activate
python batch_ingest.py --playlist "https://www.youtube.com/@Unboxholics/videos" \
    --after 20260101 --delay 4 \
    --api https://api.yourdomain.com
```
Transcripts are fetched from your home IP; embeddings + storage happen on the VPS.
Check: `curl https://api.yourdomain.com/api/sources`

---

## PART B — Frontend on Vercel

### 1. Import the project
- [vercel.com](https://vercel.com) → **Add New → Project** → import the GitHub repo.
- **Root Directory:** `frontend`
- Framework preset: **Next.js** (auto-detected).

### 2. Environment variable
Add:
```
NEXT_PUBLIC_API_BASE = https://api.yourdomain.com
```

### 3. Deploy
Click **Deploy**. You'll get a URL like `https://uh-ai.vercel.app`.

### 4. Wire CORS back
Make sure that exact Vercel URL is in `UH_ALLOWED_ORIGINS` on the VPS (`backend/.env`),
then reload the backend:
```bash
cd /opt/uh.ai && docker compose restart backend
```

Open the Vercel URL → ask a question → it should hit your VPS backend. 🎉

---

## Updating after code changes

**Backend (VPS):**
```bash
cd /opt/uh.ai
git pull
docker compose up -d --build
```
Your data survives — `chroma_store` and the HF cache live in the `uh_data` Docker volume.

**Frontend (Vercel):** just `git push` — Vercel auto-deploys.

---

## Operations cheatsheet

| Task | Command (on VPS, in `/opt/uh.ai`) |
|------|-----------------------------------|
| Logs | `docker compose logs -f backend` |
| Restart | `docker compose restart backend` |
| Stop / start | `docker compose down` / `docker compose up -d` |
| Health | `curl https://api.yourdomain.com/api/health` |
| Indexed sources | `curl https://api.yourdomain.com/api/sources` |
| Find the data volume name | `docker volume ls` (look for `*_uh_data`) |
| Backup the vector store | `docker run --rm -v $(docker volume ls -q \| grep uh_data):/d -v $PWD:/b alpine tar czf /b/uh_data_backup.tgz /d` |

---

## Troubleshooting

- **CORS error in browser** → the Vercel URL isn't in `UH_ALLOWED_ORIGINS` (exact, no trailing slash). Fix `.env`, `docker compose restart backend`.
- **TLS / cert fails** → DNS A record not pointing to the VPS yet, or ports 80/443 blocked. Caddy needs both.
- **`IpBlocked` during ingest** → you're ingesting from the VPS. Run ingest **locally** with `--api`, and use `--delay 4`+.
- **Out of memory** → ensure the VPS has ≥2 GB RAM (embedding model needs ~1 GB). Contabo's base plans are well above this.
- **Health shows `groq:false`** → `GROQ_API_KEY` missing in `backend/.env`; it falls back to extractive answers.
