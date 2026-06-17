"""
youtube_ingest.py — Κατεβάζει το transcript ενός πραγματικού YouTube βίντεο,
το κόβει σε έξυπνα chunks και τα στέλνει στο /api/ingest του uh.ai backend.

Στρατηγική chunking (κατάλληλη για ομιλία/transcripts):
  • time-window: μαζεύουμε segments μέχρι ~WINDOW δευτερόλεπτα ομιλίας
  • sentence-aware: αν υπάρχει στίξη, κλείνουμε σε τέλος πρότασης (όχι στη μέση)
  • overlap: κάθε chunk «κουβαλάει» λίγα δευτερόλεπτα από το προηγούμενο, ώστε
    να μη χάνεται το νόημα στα όρια
Το `start` κάθε chunk δείχνει στην αρχή του ΝΕΟΥ περιεχομένου, οπότε το
seekTo στο frontend πέφτει στο σωστό σημείο.

Χρήση:
  python youtube_ingest.py <video_id_ή_URL>
  python youtube_ingest.py https://www.youtube.com/watch?v=XXXX --title "Τίτλος"
  python youtube_ingest.py XXXX --lang el --window 40 --overlap 10
"""

import argparse
import re
import sys
from typing import List, Optional

import requests

try:
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        NoTranscriptFound,
        TranscriptsDisabled,
    )
except ImportError:
    sys.exit(
        "Λείπει το youtube-transcript-api. Τρέξε: pip install -r requirements.txt"
    )

API = "http://localhost:8000"

# Τέλη προτάσεων στα Ελληνικά (το «;» είναι το ελληνικό ερωτηματικό).
SENTENCE_END = (".", "!", ";", "…", "?")

# Annotations που βάζει το YouTube και δεν είναι ομιλία.
ANNOTATION_RE = re.compile(r"\[[^\]]*\]")


def extract_video_id(value: str) -> str:
    """Δέχεται είτε σκέτο video_id είτε ολόκληρο YouTube URL."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([0-9A-Za-z_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, value)
        if m:
            return m.group(1)
    # Αν είναι ήδη καθαρό 11-χάρακτο ID
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", value):
        return value
    raise ValueError(f"Δεν αναγνώρισα video_id από: {value}")


def fetch_title(video_id: str) -> str:
    """Παίρνει τον τίτλο μέσω oEmbed (χωρίς API key). Fallback: το ίδιο το id."""
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("title", video_id)
    except Exception:
        return video_id


def clean_text(text: str) -> str:
    text = ANNOTATION_RE.sub("", text)        # αφαίρεση [Μουσική] κ.λπ.
    text = text.replace(">>", " ")            # σημάδια αλλαγής ομιλητή του YouTube
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_segments(video_id: str, languages: List[str]) -> List[dict]:
    """Κατεβάζει τα segments του transcript ({text, start, duration})."""
    ytt = YouTubeTranscriptApi()
    try:
        return ytt.fetch(video_id, languages=languages).to_raw_data()
    except NoTranscriptFound:
        # Fallback: ό,τι transcript υπάρχει διαθέσιμο.
        transcript_list = ytt.list(video_id)
        return next(iter(transcript_list)).fetch().to_raw_data()
    except TranscriptsDisabled:
        sys.exit(f"Το βίντεο {video_id} έχει απενεργοποιημένα τα transcripts.")


def chunk_segments(
    segments: List[dict], window: int, max_len: int, overlap: int
) -> List[dict]:
    """
    Ομαδοποιεί τα segments σε chunks. Κλείνει ένα chunk όταν περάσει το `window`
    ΚΑΙ τελειώνει πρόταση, ή όταν ξεπεράσει σκληρά το `max_len`.
    """
    chunks: List[dict] = []
    cur: List[dict] = []
    cur_start: Optional[float] = None

    def flush():
        nonlocal cur, cur_start
        if not cur:
            return
        text = clean_text(" ".join(s["text"] for s in cur))
        if text:
            # Overlap: προσθέτουμε ως «εισαγωγή» την ουρά του προηγούμενου chunk,
            # για συνέχεια νοήματος — χωρίς να αλλάξουμε το start (= σωστό seekTo).
            prefix = ""
            if chunks and overlap > 0:
                prev = chunks[-1]
                tail = [
                    s for s in prev["_segs"]
                    if s["start"] >= prev["_end"] - overlap
                ]
                prefix = clean_text(" ".join(s["text"] for s in tail))
            full = f"{prefix} {text}".strip() if prefix else text
            end = cur[-1]["start"] + cur[-1].get("duration", 0)
            chunks.append(
                {"text": full, "start": int(cur_start), "_segs": list(cur), "_end": end}
            )
        cur, cur_start = [], None

    for seg in segments:
        if cur_start is None:
            cur_start = seg["start"]
        cur.append(seg)
        duration = (seg["start"] + seg.get("duration", 0)) - cur_start
        ends_sentence = clean_text(seg["text"]).endswith(SENTENCE_END)
        if (duration >= window and ends_sentence) or duration >= max_len:
            flush()
    flush()

    # Καθαρισμός βοηθητικών πεδίων πριν το ingest.
    return [{"text": c["text"], "start": c["start"]} for c in chunks]


def ingest_one(
    video: str,
    api: str = API,
    title: Optional[str] = None,
    lang: str = "el",
    window: int = 40,
    max_len: int = 75,
    overlap: int = 10,
    verbose: bool = True,
) -> dict:
    """
    Κατεβάζει transcript, κόβει chunks και κάνει ingest ΕΝΑ βίντεο.
    Επιστρέφει dict με status: 'ok' | 'no_transcript' | 'error' (δεν πετάει exception).
    """
    video_id = extract_video_id(video)
    languages = [lang, "en"]  # fallback στα Αγγλικά αν δεν υπάρχει ελληνικό
    try:
        resolved_title = title or fetch_title(video_id)
        if verbose:
            print(f"📥 {video_id} ({resolved_title})")
        segments = fetch_segments(video_id, languages)
        chunks = chunk_segments(segments, window, max_len, overlap)
        if not chunks:
            return {"status": "no_transcript", "video_id": video_id}

        resp = requests.post(
            f"{api}/api/ingest",
            json={
                "source_id": video_id,
                "platform": "youtube",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": resolved_title,
                "chunks": chunks,
            },
            timeout=300,
        )
        resp.raise_for_status()
        if verbose:
            print(f"   ✅ {len(chunks)} chunks")
        return {"status": "ok", "video_id": video_id, "title": resolved_title,
                "chunks": len(chunks)}
    except SystemExit as exc:  # από το fetch_segments όταν λείπουν υπότιτλοι
        if verbose:
            print(f"   ⏭️  skip ({exc})")
        return {"status": "no_transcript", "video_id": video_id, "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        if verbose:
            print(f"   ❌ error: {exc}")
        return {"status": "error", "video_id": video_id, "reason": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest YouTube transcript στο uh.ai.")
    parser.add_argument("video", help="YouTube video ID ή URL")
    parser.add_argument("--title", default=None, help="Τίτλος (αλλιώς auto από YouTube)")
    parser.add_argument("--lang", default="el", help="Γλώσσα transcript (default: el)")
    parser.add_argument("--window", type=int, default=40, help="Στόχος δευτ./chunk")
    parser.add_argument("--max", type=int, default=75, help="Μέγιστα δευτ./chunk")
    parser.add_argument("--overlap", type=int, default=10, help="Δευτ. overlap")
    parser.add_argument("--api", default=API, help="URL του backend")
    args = parser.parse_args()

    result = ingest_one(
        args.video, api=args.api, title=args.title, lang=args.lang,
        window=args.window, max_len=args.max, overlap=args.overlap,
    )
    if result["status"] != "ok":
        raise SystemExit(f"Δεν έγινε ingest: {result}")


if __name__ == "__main__":
    main()
