"""
ingest_text.py — Universal ingester για ΟΠΟΙΟΔΗΠΟΤΕ platform.

Επειδή τα Instagram / TikTok / X / Facebook δεν δίνουν αυτόματο transcript,
εδώ δίνεις εσύ το κείμενο (caption, απομαγνητοφώνηση, περιγραφή) και το script
το κόβει σε chunks και το στέλνει στο /api/ingest με το σωστό platform + URL.

Παραδείγματα:
  # Από αρχείο κειμένου:
  python ingest_text.py --platform instagram \\
      --url "https://www.instagram.com/reel/ABC123/" \\
      --title "Reel: Unboxing PS5" --file reel.txt

  # Από stdin:
  echo "Το κείμενο εδώ..." | python ingest_text.py --platform tiktok \\
      --url "https://www.tiktok.com/@uh/video/123" --title "TikTok clip"
"""

import argparse
import re
import sys
from typing import List

import requests

API = "http://localhost:8000"
PLATFORMS = {"youtube", "instagram", "tiktok", "x", "facebook", "web"}

SENTENCE_SPLIT = re.compile(r"(?<=[.!;…?])\s+")


def chunk_text(text: str, max_chars: int = 600, overlap_sentences: int = 1) -> List[dict]:
    """
    Κόβει απλό κείμενο (χωρίς timestamps) σε chunks ανά πρόταση, μέχρι ~max_chars,
    με μικρό overlap προτάσεων για συνέχεια νοήματος. timestamp = 0 παντού.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        sentences = [text]

    chunks: List[dict] = []
    cur: List[str] = []
    cur_len = 0
    for sent in sentences:
        if cur and cur_len + len(sent) > max_chars:
            chunks.append(" ".join(cur))
            cur = cur[-overlap_sentences:] if overlap_sentences else []
            cur_len = sum(len(s) + 1 for s in cur)
        cur.append(sent)
        cur_len += len(sent) + 1
    if cur:
        chunks.append(" ".join(cur))

    return [{"text": c, "start": 0} for c in chunks]


def slug_from_url(url: str) -> str:
    """Φτιάχνει ένα σταθερό source_id από το URL."""
    s = re.sub(r"^https?://(www\.)?", "", url)
    s = re.sub(r"[^0-9A-Za-z]+", "-", s).strip("-")
    return s[:80] or "source"


def main() -> None:
    p = argparse.ArgumentParser(description="Universal ingest κειμένου στο uh.ai.")
    p.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    p.add_argument("--url", required=True, help="Το URL της ανάρτησης/βίντεο")
    p.add_argument("--title", required=True, help="Τίτλος")
    p.add_argument("--file", default=None, help="Αρχείο κειμένου (αλλιώς διαβάζει stdin)")
    p.add_argument("--source-id", default=None, help="Custom source_id (αλλιώς από URL)")
    p.add_argument("--api", default=API)
    args = p.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    chunks = chunk_text(text)
    if not chunks:
        sys.exit("Δεν δόθηκε κείμενο για ingest.")

    source_id = args.source_id or slug_from_url(args.url)
    print(f"✂️  {len(chunks)} chunks ({args.platform}: {source_id})")

    resp = requests.post(
        f"{args.api}/api/ingest",
        json={
            "source_id": source_id,
            "platform": args.platform,
            "url": args.url,
            "title": args.title,
            "chunks": chunks,
        },
        timeout=300,
    )
    resp.raise_for_status()
    print(f"✅ Ingested: {resp.json()}")


if __name__ == "__main__":
    main()
