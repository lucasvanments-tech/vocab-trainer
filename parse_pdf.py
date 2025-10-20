# parse_pdf.py
import json
import re
from PyPDF2 import PdfReader
import sys

INPUT_PDF = "data/une_langue.pdf"
OUTPUT_JSON = "vocab.json"

def extract_text(pdf_path):
    reader = PdfReader(pdf_path)
    text = []
    for page in reader.pages:
        try:
            text.append(page.extract_text() or "")
        except Exception as e:
            print("page extract issue:", e)
            text.append("")
    return "\n".join(text)

def parse_pairs(raw):
    # Normalize dashes
    raw = raw.replace("–", "-").replace("—", "-")
    lines = raw.splitlines()
    pairs = []
    bullet_re = re.compile(r"^[\s•\-\u2022]*")
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        # Remove bullet chars at start
        ln_clean = bullet_re.sub("", ln)
        # Try splitting on " - " or " -"
        if "-" in ln_clean:
            parts = [p.strip() for p in ln_clean.split("-", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                fr, nl = parts
                # filter out header lines that are not vocabulary (heuristic)
                if len(fr.split()) <= 6 and len(nl.split()) <= 6:
                    pairs.append({"fr": fr, "nl": nl})
                    continue
        # also try lines with "–" already normalized, or " — "
        if "—" in ln_clean or "–" in ln_clean:
            # fallback split
            parts = re.split(r"[–—]", ln_clean, maxsplit=1)
            parts = [p.strip() for p in parts]
            if len(parts) == 2:
                pairs.append({"fr": parts[0], "nl": parts[1]})
    return pairs

def main():
    print("Reading PDF:", INPUT_PDF)
    raw = extract_text(INPUT_PDF)
    pairs = parse_pairs(raw)
    print(f"Found {len(pairs)} candidate pairs. Sample:")
    for i, p in enumerate(pairs[:10]):
        print(i+1, p["fr"], "->", p["nl"])
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)
    print("Wrote", OUTPUT_JSON)

if __name__ == "__main__":
    main()
