"""
seed_example.py — Παράδειγμα ingest δεδομένων στο uh.ai backend.

Τρέξε το αφού έχει σηκωθεί το backend (uvicorn) στο localhost:8000.
Δείχνει τη μορφή που περιμένει το /api/ingest. Αντικατέστησε τα δείγματα
με πραγματικά transcripts (π.χ. από το YouTube Transcript API).

    python seed_example.py
"""

import requests

API = "http://localhost:8000"

SAMPLE_VIDEOS = [
    {
        "video_id": "dQw4w9WgXcQ",  # ⚠️ placeholder — βάλε πραγματικό UH video_id
        "title": "Unboxing του νέου PlayStation 5 Pro",
        "chunks": [
            {"text": "Τι λέει μάγκες, σήμερα ανοίγουμε το νέο PlayStation 5 Pro!", "start": 0},
            {"text": "Η συσκευασία είναι πανέμορφη, στρατός όλη η ομάδα το περίμενε.", "start": 35},
            {"text": "Τα γραφικά στο 4K είναι εξωπραγματικά, δείτε εδώ το demo.", "start": 120},
            {"text": "Η τιμή είναι αλμυρή αλλά αξίζει για τους hardcore gamers.", "start": 240},
        ],
    },
    {
        "video_id": "9bZkp7q19f0",  # ⚠️ placeholder
        "title": "Gaming setup tour 2026",
        "chunks": [
            {"text": "Σήμερα σας δείχνω όλο μου το gaming setup για το 2026.", "start": 0},
            {"text": "Το mechanical πληκτρολόγιο κάνει τη διαφορά στα competitive παιχνίδια.", "start": 90},
            {"text": "Τρία οθόνες, μάγκα, για ultimate παραγωγικότητα και gaming.", "start": 180},
        ],
    },
]


def main() -> None:
    for video in SAMPLE_VIDEOS:
        resp = requests.post(f"{API}/api/ingest", json=video, timeout=120)
        resp.raise_for_status()
        print("Ingested:", resp.json())


if __name__ == "__main__":
    main()
