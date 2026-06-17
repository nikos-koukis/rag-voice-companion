"""
batch_ingest.py — Μαζικό ingest πολλών YouTube βίντεο των Unboxholics.

Δέχεται:
  • πολλά URLs/IDs ως ορίσματα
  • αρχείο με ένα URL/ID ανά γραμμή (--file)
  • ολόκληρο playlist ή κανάλι (--playlist), που «ανοίγει» αυτόματα σε βίντεο

Κάνει ingest το καθένα, κάνει skip όσα δεν έχουν υπότιτλους, και βγάζει σύνοψη.

Παραδείγματα:
  python batch_ingest.py URL1 URL2 URL3
  python batch_ingest.py --file videos.txt
  python batch_ingest.py --playlist "https://www.youtube.com/@Unboxholics/videos" --limit 20
"""

import argparse
import subprocess
import sys
import time
from typing import List

from youtube_ingest import ingest_one, API

FAILED_FILE = "failed_ingest.txt"


def expand_playlist(
    url: str, limit: int, after: str = "", before: str = ""
) -> List[str]:
    """
    Επιστρέφει τα video IDs ενός playlist/καναλιού μέσω yt-dlp.

    Χωρίς φίλτρο ημερομηνίας: γρήγορο (--flat-playlist).
    Με φίλτρο: εξάγει id+upload_date streaming και ΣΤΑΜΑΤΑΕΙ μόνο του στο πρώτο
    βίντεο παλαιότερο του παραθύρου (τα κανάλια είναι newest-first), τερματίζοντας
    το yt-dlp — γρήγορο και χωρίς να σκανάρει όλο το ιστορικό.
    """
    base = [
        sys.executable, "-m", "yt_dlp",
        "--extractor-args", "youtube:player_client=android",
    ]

    # --- Γρήγορη διαδρομή: χωρίς ημερομηνίες ---
    if not (after or before):
        cmd = base + ["--flat-playlist", "--print", "%(id)s"]
        if limit:
            cmd += ["--playlist-end", str(limit)]
        cmd.append(url)
        out = subprocess.run(cmd, capture_output=True, text=True)
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip().isalnum() or "-" in ln.strip() or "_" in ln.strip()]

    # --- Διαδρομή με ημερομηνίες: streaming + early stop ---
    cmd = base + ["--print", "%(id)s %(upload_date)s"]
    if limit:
        cmd += ["--playlist-end", str(limit)]
    cmd.append(url)

    ids: List[str] = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for line in proc.stdout or []:
            parts = line.strip().split()
            if len(parts) < 2 or not parts[1].isdigit():
                continue
            vid, date = parts[0], parts[1]
            if before and date > before:
                continue
            if after and date < after:
                break  # newest-first: φτάσαμε παλαιότερα του παραθύρου → στοπ
            ids.append(vid)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()
    return ids


def main() -> None:
    p = argparse.ArgumentParser(description="Μαζικό ingest YouTube βίντεο στο uh.ai.")
    p.add_argument("videos", nargs="*", help="URLs ή IDs")
    p.add_argument("--file", default=None, help="Αρχείο με ένα URL/ID ανά γραμμή")
    p.add_argument("--playlist", default=None, help="Playlist ή κανάλι URL")
    p.add_argument("--limit", type=int, default=0, help="Όριο βίντεο από playlist/κανάλι")
    p.add_argument("--after", default="", help="Μόνο βίντεο ΜΕΤΑ από YYYYMMDD (π.χ. 20260101)")
    p.add_argument("--before", default="", help="Μόνο βίντεο ΠΡΙΝ από YYYYMMDD")
    p.add_argument("--dry-run", action="store_true", help="Μόνο μέτρημα/λίστα, χωρίς ingest")
    p.add_argument("--delay", type=float, default=2.0,
                   help="Δευτ. καθυστέρηση μεταξύ βίντεο (αποφυγή IP block· default 2)")
    p.add_argument("--lang", default="el")
    p.add_argument("--api", default=API)
    args = p.parse_args()

    targets: List[str] = list(args.videos)

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            targets += [
                ln.strip() for ln in f
                if ln.strip() and not ln.strip().startswith("#")
            ]

    if args.playlist:
        win = ""
        if args.after or args.before:
            win = f" (after={args.after or '-'}, before={args.before or '-'})"
        print(f"🔎 Ανάγνωση playlist/καναλιού{win}...")
        ids = expand_playlist(args.playlist, args.limit, args.after, args.before)
        print(f"   βρέθηκαν {len(ids)} βίντεο.")
        targets += ids

    # Αφαίρεση διπλότυπων διατηρώντας τη σειρά.
    seen = set()
    targets = [t for t in targets if not (t in seen or seen.add(t))]

    if not targets:
        sys.exit("Δεν δόθηκαν βίντεο. Δες: python batch_ingest.py --help")

    if args.dry_run:
        print(f"\n🧪 DRY RUN — {len(targets)} βίντεο θα γίνονταν ingest:")
        for t in targets:
            print(f"  - {t}")
        print("\n(Τίποτα δεν μπήκε στη βάση. Βγάλε το --dry-run για να τρέξει κανονικά.)")
        return

    print(f"\n🚀 Ξεκινάω ingest {len(targets)} βίντεο (delay={args.delay}s)...\n")
    ok, skipped, errors = [], [], []
    for i, t in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}]", end=" ")
        res = ingest_one(t, api=args.api, lang=args.lang)
        {"ok": ok, "no_transcript": skipped}.get(res["status"], errors).append(res)
        if i < len(targets) and args.delay > 0:
            time.sleep(args.delay)

    print("\n" + "=" * 48)
    print(f"✅ Ingested:        {len(ok)}")
    print(f"⏭️  Χωρίς υπότιτλους: {len(skipped)}")
    print(f"❌ Σφάλματα:         {len(errors)}")
    if skipped:
        print("\nSkipped (χωρίς transcript):")
        for r in skipped:
            print(f"  - {r['video_id']}")
    if errors:
        print("\nΣφάλματα:")
        for r in errors:
            print(f"  - {r['video_id']}: {r.get('reason', '')[:80]}")
        # Αποθήκευση αποτυχημένων IDs για εύκολο retry: --file failed_ingest.txt
        with open(FAILED_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(r["video_id"] for r in errors) + "\n")
        print(f"\n💾 Τα αποτυχημένα αποθηκεύτηκαν στο {FAILED_FILE}")
        print(f"   Retry αργότερα (όταν ξεμπλοκάρει η IP):")
        print(f"   python batch_ingest.py --file {FAILED_FILE} --delay 4")


if __name__ == "__main__":
    main()
