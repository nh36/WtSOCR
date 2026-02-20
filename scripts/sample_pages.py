#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
from pathlib import Path

def parse_pages(s, max_page=None):
    pages = set()
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            a = int(a)
            b = int(b)
            for p in range(a, b + 1):
                pages.add(p)
        else:
            pages.add(int(part))
    if max_page:
        pages = {p for p in pages if 1 <= p <= max_page}
    return sorted(pages)

def pdf_page_count(pdf_path):
    try:
        out = subprocess.check_output(["pdfinfo", pdf_path], text=True)
    except Exception:
        return None
    m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    return int(m.group(1)) if m else None

TIB_RANGE = re.compile(r"[\u0F00-\u0FFF]")

def analyze_text(text):
    total = len(text)
    tib = len(TIB_RANGE.findall(text))
    latin = sum(c.isalpha() and ord(c) < 128 for c in text)
    return total, tib, latin

def extract_page_text(pdf_path, page, out_txt):
    cmd = ["pdftotext", "-f", str(page), "-l", str(page), "-layout", pdf_path, out_txt]
    subprocess.check_call(cmd)

def main():
    ap = argparse.ArgumentParser(description="Sample PDF pages and assess text layer quality.")
    ap.add_argument("pdf", help="Path to PDF")
    ap.add_argument("--pages", default="1,5,20,100,200,400", help="Comma/range list, e.g. 1,5,20,100-110")
    ap.add_argument("--outdir", default="work/samples", help="Output directory")
    args = ap.parse_args()

    pdf_path = args.pdf
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    max_page = pdf_page_count(pdf_path)
    pages = parse_pages(args.pages, max_page)
    if not pages:
        raise SystemExit("No valid pages to sample.")

    print(f"PDF: {pdf_path}")
    if max_page:
        print(f"Pages: {max_page}")
    print("page\tchars\ttib\tlatin\tfile")

    for p in pages:
        out_txt = outdir / f"{Path(pdf_path).stem}_p{p:04d}.txt"
        extract_page_text(pdf_path, p, str(out_txt))
        text = out_txt.read_text(errors="ignore")
        total, tib, latin = analyze_text(text)
        print(f"{p}\t{total}\t{tib}\t{latin}\t{out_txt}")

if __name__ == "__main__":
    main()
