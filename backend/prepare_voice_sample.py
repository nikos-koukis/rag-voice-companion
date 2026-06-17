"""
prepare_voice_sample.py — Ετοιμάζει καθαρό δείγμα φωνής για ElevenLabs voice cloning.

Κατεβάζει τον ήχο από ΔΙΚΟ ΣΑΣ YouTube βίντεο (yt-dlp), κόβει ένα απόσπασμα και
το «καθαρίζει» με ffmpeg (mono, 44.1kHz, loudness normalization) ώστε να είναι
ιδανικό για κλωνοποίηση.

⚠️ Χρησιμοποίησέ το ΜΟΝΟ για περιεχόμενο που σου ανήκει ή έχεις άδεια, και
κλωνοποίησε φωνές ΜΟΝΟ με τη συναίνεση του προσώπου.

Απαιτήσεις:
  pip install -r requirements.txt        # περιλαμβάνει το yt-dlp
  ffmpeg εγκατεστημένο   (macOS: brew install ffmpeg)

Παραδείγματα:
  # Κόψε το απόσπασμα 02:10 → 03:30 όπου ο Σάκης μιλάει καθαρά:
  python prepare_voice_sample.py "https://youtu.be/XXXX" --start 02:10 --end 03:30 --out sakis

  # Πολλαπλά αποσπάσματα (τρέξ' το πολλές φορές με διαφορετικό --out suffix):
  python prepare_voice_sample.py "https://youtu.be/XXXX" --start 10:00 --end 11:00 --out sakis_2
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

OUT_DIR = "voice_samples"


def need(tool: str, hint: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"Λείπει το «{tool}». {hint}")


def to_seconds(ts: str) -> str:
    """Δέχεται 'SS', 'MM:SS' ή 'HH:MM:SS' και το επιστρέφει σε μορφή ffmpeg/yt-dlp."""
    if not re.fullmatch(r"(\d+:)?(\d{1,2}:)?\d{1,2}", ts):
        sys.exit(f"Μη έγκυρο timestamp: {ts} (χρησιμοποίησε SS ή MM:SS ή HH:MM:SS)")
    return ts


def main() -> None:
    p = argparse.ArgumentParser(description="Ετοιμασία δείγματος φωνής για ElevenLabs.")
    p.add_argument("url", help="YouTube URL ή ID (δικό σας περιεχόμενο)")
    p.add_argument("--start", default=None, help="Αρχή αποσπάσματος (π.χ. 02:10)")
    p.add_argument("--end", default=None, help="Τέλος αποσπάσματος (π.χ. 03:30)")
    p.add_argument("--out", default="sample", help="Όνομα αρχείου εξόδου (χωρίς κατάληξη)")
    p.add_argument("--format", default="mp3", choices=["mp3", "wav"], help="Format εξόδου")
    p.add_argument(
        "--client",
        default="android",
        help="YouTube player client (android δουλεύει· web/tv μπλοκάρονται από SABR).",
    )
    args = p.parse_args()

    need("ffmpeg", "Σε macOS: brew install ffmpeg")

    os.makedirs(OUT_DIR, exist_ok=True)
    raw_path = os.path.join(OUT_DIR, f"{args.out}__raw.{args.format}")
    final_path = os.path.join(OUT_DIR, f"{args.out}.{args.format}")

    # 1. Κατέβασμα ήχου (μόνο το απόσπασμα, αν δοθεί) με yt-dlp ως module του venv.
    yt_cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio/best",
        "--extractor-args", f"youtube:player_client={args.client}",
        "-x", "--audio-format", args.format, "--audio-quality", "0",
        "-o", raw_path,
        "--force-overwrites",
    ]
    if args.start and args.end:
        section = f"*{to_seconds(args.start)}-{to_seconds(args.end)}"
        yt_cmd += ["--download-sections", section]
    elif args.start or args.end:
        sys.exit("Δώσε ΚΑΙ --start ΚΑΙ --end (ή κανένα για όλο το βίντεο).")
    yt_cmd.append(args.url)

    print("📥 Κατέβασμα ήχου...")
    try:
        subprocess.run(yt_cmd, check=True)
    except FileNotFoundError:
        sys.exit("Λείπει το yt-dlp. Τρέξε: pip install -r requirements.txt")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Αποτυχία κατεβάσματος (yt-dlp): {exc}")

    if not os.path.exists(raw_path):
        sys.exit("Δεν δημιουργήθηκε αρχείο ήχου — έλεγξε το URL/απόσπασμα.")

    # 2. Καθάρισμα: mono, 44.1kHz, loudness normalization (ιδανικό για cloning).
    print("🎚️  Καθάρισμα ήχου (mono + normalize)...")
    ff_cmd = [
        "ffmpeg", "-y", "-i", raw_path,
        "-ac", "1", "-ar", "44100",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        final_path,
    ]
    try:
        subprocess.run(ff_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Αποτυχία ffmpeg: {exc}")

    os.remove(raw_path)
    size_mb = os.path.getsize(final_path) / (1024 * 1024)
    print(f"✅ Έτοιμο: {final_path}  ({size_mb:.1f} MB)")
    print("   Ανέβασέ το στο ElevenLabs → Add a New Voice → Instant Voice Cloning.")
    print("   Συμβουλή: μάζεψε 1–3 λεπτά ΚΑΘΑΡΗΣ ομιλίας (χωρίς μουσική/άλλες φωνές).")


if __name__ == "__main__":
    main()
