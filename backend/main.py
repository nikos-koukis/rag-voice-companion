"""
uh.ai — Backend (FastAPI)
=========================

Semantic Video Search (RAG) + Voice Companion για τους Unboxholics (UH).

Ροή λειτουργίας:
1.  Κάνουμε ingest τα κομμάτια (chunks) των transcripts μαζί με τα timestamps.
    Παράγουμε embeddings ΤΟΠΙΚΑ (sentence-transformers) και τα αποθηκεύουμε στη ChromaDB.
2.  Στο /api/ask κάνουμε semantic search, χτίζουμε ένα ελληνικό system prompt για
    το "UH-Bot", παράγουμε απάντηση με τοπικό Hugging Face LLM και (προαιρετικά)
    κλωνοποιούμε τη φωνή του χαρακτήρα μέσω ElevenLabs.

Σημείωση: Όλα τα μοντέλα κειμένου τρέχουν τοπικά — δεν χρειάζεται κανένα paid API key
για το text generation. Το ElevenLabs είναι προαιρετικό (υπάρχει mock fallback).
"""

import base64
import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

import requests
import torch
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("uh.ai")

# --------------------------------------------------------------------------- #
#  Ρυθμίσεις (Configuration)
# --------------------------------------------------------------------------- #

EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Ελαφρύ, πολυγλωσσικό instruct LLM. Το Qwen2.5-1.5B είναι μικρό (~1.5 GB),
# υποστηρίζει Ελληνικά και τρέχει σε CPU. Άλλαξέ το με μεταβλητή περιβάλλοντος
# (π.χ. UH_LLM_MODEL=microsoft/Phi-3-mini-4k-instruct σε μηχάνημα με GPU/χώρο).
LLM_MODEL_NAME = os.getenv("UH_LLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")

# Cloud LLM (Groq) — προαιρετικό αλλά συνιστώμενο. Αν υπάρχει GROQ_API_KEY,
# χρησιμοποιείται κατά προτεραιότητα: συνθέτει πολύ καλύτερα στα Ελληνικά,
# τρέχει στο cloud (μηδέν χώρος/φόρτος τοπικά) και είναι δωρεάν (free tier).
# Πάρε key από: https://console.groq.com
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

CHROMA_DIR = os.getenv("UH_CHROMA_DIR", "./chroma_store")
COLLECTION_NAME = "uh_transcripts"

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# Voice IDs ανά χαρακτήρα (βάλε εδώ τα δικά σου από το ElevenLabs dashboard).
VOICE_IDS = {
    "sakis": os.getenv("ELEVENLABS_VOICE_SAKIS", "21m00Tcm4TlvDq8ikWAM"),
    "alekos": os.getenv("ELEVENLABS_VOICE_ALEKOS", "AZnzlk1XvdvUeBnXmlld"),
}

# Φιλικά ονόματα για το prompt.
CHARACTER_NAMES = {"sakis": "Σάκης", "alekos": "Αλέκος"}

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# --------------------------------------------------------------------------- #
#  Κατάσταση εφαρμογής (φορτώνεται στο startup)
# --------------------------------------------------------------------------- #


class AppState:
    embedder: Optional[SentenceTransformer] = None
    llm = None  # transformers text-generation pipeline
    chroma_client = None
    collection = None


state = AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Φόρτωση όλων των μοντέλων μία φορά στην εκκίνηση."""
    logger.info("Εκκίνηση uh.ai backend — device: %s", DEVICE)

    # 1. Embedding model (τοπικό)
    logger.info("Φόρτωση embedding model: %s", EMBEDDING_MODEL_NAME)
    state.embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device=DEVICE)

    # 2. ChromaDB (persistent τοπικά)
    logger.info("Σύνδεση με ChromaDB στο: %s", CHROMA_DIR)
    state.chroma_client = chromadb.PersistentClient(
        path=CHROMA_DIR, settings=Settings(anonymized_telemetry=False)
    )
    state.collection = state.chroma_client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    # 3. Local LLM (Hugging Face pipeline). Αν αποτύχει η φόρτωση, συνεχίζουμε με
    #    fallback ώστε να μην κρασάρει το app (χρήσιμο σε μηχανήματα χωρίς GPU/μνήμη).
    #    Αν υπάρχει Groq (cloud), παρακάμπτουμε τη φόρτωση: δεν χρειάζεται να
    #    σπαταλήσουμε RAM/χρόνο για το τοπικό μοντέλο.
    if GROQ_API_KEY:
        logger.info("Βρέθηκε GROQ_API_KEY — παράκαμψη τοπικού LLM (χρήση cloud).")
        state.llm = None
    else:
        try:
            logger.info("Φόρτωση LLM: %s (μπορεί να αργήσει την πρώτη φορά)", LLM_MODEL_NAME)
            tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(
                LLM_MODEL_NAME,
                torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
                trust_remote_code=True,
                device_map="auto" if DEVICE == "cuda" else None,
            )
            state.llm = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                device=0 if DEVICE == "cuda" else -1,
            )
            logger.info("Το LLM φορτώθηκε επιτυχώς.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Αποτυχία φόρτωσης LLM (%s). Θα χρησιμοποιηθεί fallback.", exc)
            state.llm = None

    yield
    logger.info("Τερματισμός uh.ai backend.")


app = FastAPI(title="uh.ai", version="1.0.0", lifespan=lifespan)

# --------------------------------------------------------------------------- #
#  CORS — επιτρέπουμε σύνδεση από το Next.js frontend
# --------------------------------------------------------------------------- #

# Επιτρεπόμενα origins: localhost για dev + ό,τι δηλώσεις στο UH_ALLOWED_ORIGINS
# (comma-separated), π.χ. "https://uh-ai.vercel.app,https://www.uh.ai"
_default_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_extra_origins = [
    o.strip() for o in os.getenv("UH_ALLOWED_ORIGINS", "").split(",") if o.strip()
]
ALLOWED_ORIGINS = _default_origins + _extra_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
#  Pydantic models
# --------------------------------------------------------------------------- #


# Υποστηριζόμενα platforms. Το YouTube είναι το μόνο με αυτόματο transcript +
# άλμα σε timestamp· τα υπόλοιπα δουλεύουν μέσω universal ingest (κείμενο που
# δίνεις εσύ) και εμφανίζονται ως κάρτες με link/preview.
SUPPORTED_PLATFORMS = {"youtube", "instagram", "tiktok", "x", "facebook", "web"}


class TranscriptChunk(BaseModel):
    text: str = Field(..., description="Το κείμενο του chunk.")
    start: int = Field(0, description="Timestamp έναρξης σε δευτερόλεπτα (προαιρετικό).")


class IngestRequest(BaseModel):
    source_id: str = Field(..., description="Μοναδικό ID πηγής (π.χ. YouTube video ID ή slug URL).")
    platform: str = Field("youtube", description="youtube | instagram | tiktok | x | facebook | web")
    url: Optional[str] = Field(None, description="Canonical URL της πηγής.")
    title: str = Field(..., description="Ο τίτλος της πηγής.")
    chunks: List[TranscriptChunk]


class IngestResponse(BaseModel):
    status: str
    source_id: str
    platform: str
    chunks_indexed: int


class AskRequest(BaseModel):
    query: str
    voice_character: str = Field("sakis", description="'sakis' ή 'alekos'.")


class AskResponse(BaseModel):
    answer: str
    platform: str
    source_id: str
    url: str
    title: str
    timestamp: int
    audio_base64: str


# --------------------------------------------------------------------------- #
#  Βοηθητικές συναρτήσεις
# --------------------------------------------------------------------------- #


def build_system_prompt(character: str) -> str:
    """Χτίζει το ελληνικό system prompt για το UH-Bot."""
    name = CHARACTER_NAMES.get(character, "ο παρουσιαστής")
    return (
        f"Είσαι το «UH-Bot», ο ψηφιακός βοηθός του ελληνικού καναλιού Unboxholics, "
        f"και μιλάς σαν τον {name}.\n\n"
        f"ΚΑΝΟΝΕΣ:\n"
        f"1. Απαντάς ΠΑΝΤΑ στα Ελληνικά, σε σωστή και φυσική γλώσσα.\n"
        f"2. Χρησιμοποίησε τις πληροφορίες από το CONTEXT. Μην εφευρίσκεις στοιχεία "
        f"που δεν υπάρχουν, αλλά το κείμενο μπορεί να έχει λάθη μεταγραφής — "
        f"βγάλε νόημα από αυτό και σύνοψέ το.\n"
        f"3. Πες «Δεν το βρήκα αυτό στα βίντεο, μάγκα» ΜΟΝΟ αν το context είναι "
        f"τελείως άσχετο με την ερώτηση. Αν έχει έστω και μερική σχετική πληροφορία, "
        f"απάντησε με βάση αυτήν.\n"
        f"4. Γράψε 1-3 προτάσεις, με χαλαρό φιλικό ύφος και λίγη αργκό της κοινότητας "
        f"(π.χ. «μάγκα», «στρατός», «τι λέει»). Μην το παρακάνεις με την αργκό.\n"
        f"5. Απάντησε κατευθείαν στην ερώτηση — χωρίς εισαγωγές τύπου «Ως UH-Bot...».\n\n"
        f"Ακολουθεί ΜΟΝΟ ένα παράδειγμα ΥΦΟΥΣ (άσχετο θέμα). "
        f"ΜΗΝ χρησιμοποιήσεις τα στοιχεία του στην πραγματική σου απάντηση — "
        f"χρησιμοποίησε αποκλειστικά το CONTEXT που θα σου δοθεί:\n"
        f"  Ερώτηση: Πώς ήταν ο καιρός στο βίντεο;\n"
        f"  Απάντηση: Τι λέει μάγκα! Είχε λιακάδα όλη μέρα, τέλειες συνθήκες — στρατός δηλαδή."
    )


def build_user_prompt(query: str, context: str) -> str:
    return (
        f"Context από τα βίντεο των Unboxholics:\n\"\"\"\n{context}\n\"\"\"\n\n"
        f"Ερώτηση χρήστη: {query}\n\n"
        f"Δώσε την απάντησή σου ως UH-Bot:"
    )


def call_groq(messages: List[dict]) -> str:
    """Καλεί το Groq (OpenAI-compatible) και επιστρέφει το κείμενο της απάντησης."""
    resp = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 200,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def call_local_llm(messages: List[dict]) -> str:
    """Καλεί το τοπικό Hugging Face pipeline."""
    outputs = state.llm(
        messages,
        max_new_tokens=160,
        do_sample=True,
        temperature=0.4,        # χαμηλότερη -> πιο συνεκτικές, λιγότερο "τυχαίες" απαντήσεις
        top_p=0.9,
        repetition_penalty=1.15,  # αποτρέπει επαναλήψεις/ασυναρτησίες σε μικρά μοντέλα
        return_full_text=False,
    )
    generated = outputs[0]["generated_text"]
    # Ορισμένα pipelines επιστρέφουν list μηνυμάτων αντί για string.
    if isinstance(generated, list):
        generated = generated[-1].get("content", "")
    return str(generated).strip()


def extractive_fallback(context: str) -> str:
    """Τελευταίο δίχτυ ασφαλείας: επιστρέφει το πιο σχετικό απόσπασμα ως έχει."""
    snippet = context.strip().split("\n")[0][:280] if context.strip() else ""
    if snippet:
        return f"Τι λέει μάγκα! Να τι βρήκα στα βίντεο: {snippet}"
    return "Συγγνώμη μάγκα, δεν βρήκα κάτι σχετικό στα βίντεο για αυτό."


def generate_answer(character: str, query: str, context: str) -> str:
    """
    Παράγει απάντηση με ιεραρχία προτεραιότητας:
      1. Cloud LLM (Groq)  — αν υπάρχει GROQ_API_KEY
      2. Τοπικό LLM        — αν φορτώθηκε
      3. Extractive        — απόσπασμα του transcript
    """
    system_prompt = build_system_prompt(character)
    user_prompt = build_user_prompt(query, context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 1. Cloud (Groq) — η καλύτερη ποιότητα, μηδέν τοπικός φόρτος.
    if GROQ_API_KEY:
        try:
            return call_groq(messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Αποτυχία Groq (%s) — δοκιμή τοπικού LLM.", exc)

    # 2. Τοπικό LLM.
    if state.llm is not None:
        try:
            return call_local_llm(messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Αποτυχία τοπικού LLM (%s) — extractive fallback.", exc)

    # 3. Extractive fallback.
    return extractive_fallback(context)


def synthesize_voice(text: str, character: str) -> str:
    """
    Καλεί το ElevenLabs για κλωνοποίηση φωνής και επιστρέφει Base64 audio (mp3).
    Αν λείπει το API key ή αποτύχει η κλήση, επιστρέφει κενό string (mock fallback)
    ώστε το frontend να συνεχίσει κανονικά χωρίς ήχο.
    """
    if not ELEVENLABS_API_KEY:
        logger.info("Δεν υπάρχει ELEVENLABS_API_KEY — παράκαμψη voice (mock).")
        return ""

    voice_id = VOICE_IDS.get(character, VOICE_IDS["sakis"])
    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Αποτυχία ElevenLabs (%s) — επιστροφή χωρίς ήχο.", exc)
        return ""


# --------------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------------- #


@app.get("/api/health")
def health():
    if GROQ_API_KEY:
        llm_backend = f"groq:{GROQ_MODEL}"
    elif state.llm is not None:
        llm_backend = f"local:{LLM_MODEL_NAME}"
    else:
        llm_backend = "extractive-fallback"
    return {
        "status": "ok",
        "device": DEVICE,
        "llm_backend": llm_backend,
        "groq": bool(GROQ_API_KEY),
        "llm_loaded": state.llm is not None,
        "elevenlabs": bool(ELEVENLABS_API_KEY),
        "indexed_documents": state.collection.count() if state.collection else 0,
    }


def canonical_url(platform: str, source_id: str, url: Optional[str], timestamp: int) -> str:
    """Χτίζει το canonical URL αν δεν δόθηκε (μόνο το YouTube το παράγουμε αξιόπιστα)."""
    if url:
        return url
    if platform == "youtube":
        suffix = f"&t={max(0, timestamp)}s" if timestamp else ""
        return f"https://www.youtube.com/watch?v={source_id}{suffix}"
    return ""


@app.get("/api/sources")
def sources():
    """Λίστα των πηγών που έχουν γίνει ingest (platform, τίτλος, πλήθος chunks)."""
    data = state.collection.get(include=["metadatas"])
    agg: dict = {}
    for meta in data.get("metadatas", []) or []:
        key = (meta.get("platform", "?"), meta.get("source_id", "?"))
        if key not in agg:
            agg[key] = {
                "platform": meta.get("platform", "?"),
                "source_id": meta.get("source_id", "?"),
                "title": meta.get("title", ""),
                "url": meta.get("url", ""),
                "chunks": 0,
            }
        agg[key]["chunks"] += 1
    items = sorted(agg.values(), key=lambda x: (x["platform"], x["title"]))
    return {"count": len(items), "sources": items}


@app.post("/api/reset")
def reset():
    """Καθαρίζει ΟΛΗ τη βάση (dev utility). Χρήσιμο σε αλλαγές schema."""
    state.chroma_client.delete_collection(COLLECTION_NAME)
    state.collection = state.chroma_client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    logger.info("Η βάση καθαρίστηκε (reset).")
    return {"status": "reset"}


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest):
    """Δημιουργεί embeddings τοπικά και τα αποθηκεύει στη ChromaDB (όλα τα platforms)."""
    if not req.chunks:
        raise HTTPException(status_code=400, detail="Δεν δόθηκαν chunks για ingest.")

    platform = req.platform if req.platform in SUPPORTED_PLATFORMS else "web"

    texts = [c.text for c in req.chunks]
    embeddings = state.embedder.encode(texts, normalize_embeddings=True).tolist()

    # Καθάρισμα παλιών chunks της ίδιας πηγής (καθαρό re-ingest, χωρίς διπλά/ορφανά).
    try:
        state.collection.delete(
            where={
                "$and": [
                    {"platform": {"$eq": platform}},
                    {"source_id": {"$eq": req.source_id}},
                ]
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Καθάρισμα παλιών chunks απέτυχε (%s) — συνεχίζω.", exc)

    # Μοναδικά IDs ανά platform+source ώστε να μη συγκρούονται διαφορετικά platforms.
    ids = [f"{platform}:{req.source_id}_{i}" for i in range(len(req.chunks))]
    metadatas = [
        {
            "platform": platform,
            "source_id": req.source_id,
            "url": req.url or "",
            "title": req.title,
            "timestamp": c.start,
        }
        for c in req.chunks
    ]

    state.collection.upsert(
        ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas
    )

    logger.info(
        "Ingested %d chunks (%s: %s).", len(req.chunks), platform, req.source_id
    )
    return IngestResponse(
        status="ok",
        source_id=req.source_id,
        platform=platform,
        chunks_indexed=len(req.chunks),
    )


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """Semantic search -> RAG synthesis (τοπικό LLM) -> voice cloning (ElevenLabs)."""
    character = req.voice_character if req.voice_character in VOICE_IDS else "sakis"

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Η ερώτηση είναι κενή.")

    if state.collection.count() == 0:
        raise HTTPException(
            status_code=400,
            detail="Δεν υπάρχουν δεδομένα. Κάνε πρώτα ingest κάποια transcripts.",
        )

    # 1. Semantic search
    query_emb = state.embedder.encode([req.query], normalize_embeddings=True).tolist()
    results = state.collection.query(query_embeddings=query_emb, n_results=4)

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    if not documents:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκαν σχετικά αποτελέσματα.")

    top_meta = metadatas[0]
    platform = top_meta.get("platform", "youtube")
    source_id = top_meta.get("source_id", "")
    title = top_meta.get("title", "")
    timestamp = int(top_meta.get("timestamp", 0))

    # «Γείωση» στην πηγή που θα δείξουμε: κρατάμε ΜΟΝΟ τα chunks της κορυφαίας
    # πηγής, ώστε η απάντηση να μην ανακατεύει στοιχεία από διαφορετικές πηγές.
    context = "\n".join(
        doc
        for doc, meta in zip(documents, metadatas)
        if meta.get("source_id") == source_id and meta.get("platform") == platform
    )

    url = canonical_url(platform, source_id, top_meta.get("url") or None, timestamp)

    # 2. RAG synthesis
    answer = generate_answer(character, req.query, context)

    # 3. Voice cloning (προαιρετικό)
    audio_base64 = synthesize_voice(answer, character)

    return AskResponse(
        answer=answer,
        platform=platform,
        source_id=source_id,
        url=url,
        title=title,
        timestamp=timestamp,
        audio_base64=audio_base64,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
