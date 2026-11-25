#!/usr/bin/env python3
"""Build a paragraph-indexed corpus from plain text (stdlib only).
Usage: index_corpus.py --text-dir DIR --out corpus_index.json
       [--map ids.json] [--max-para-chars 1500]
Each .txt/.md file becomes one document; source_document_id defaults to the
file stem, --map takes {"<filename>": "<DOCID>"}. Paragraphs are split on
blank lines and get stable DOCID::pNNN ids used by all evidence cards.
"""
import argparse, hashlib, json, os, re, sys


def split_paragraphs(text):
 blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
 return [" ".join(b.split()) for b in blocks if b.strip()]


def chunk_long(paragraph, limit):
 if len(paragraph) <= limit:
  return [paragraph]
 parts, buf = [], ""
 for sent in re.split(r"(?<=[.!?。！？；;])\s*", paragraph):
  if buf and len(buf) + len(sent) > limit:
   parts.append(buf)
   buf = sent
  else:
   buf = (buf + " " + sent).strip()
 if buf:
  parts.append(buf)
 return parts or [paragraph[:limit]]


def main():
 ap = argparse.ArgumentParser()
 ap.add_argument("--text-dir", required=True)
 ap.add_argument("--out", required=True)
 ap.add_argument("--map", default=None)
 ap.add_argument("--max-para-chars", type=int, default=1500)
 args = ap.parse_args()

 idmap = {}
 if args.map:
  with open(args.map, encoding="utf-8") as f:
   idmap = json.load(f)

 docs, warnings = [], []
 names = sorted(n for n in os.listdir(args.text_dir)
    if n.lower().endswith((".txt", ".md")))
 if not names:
  warnings.append({"error": "no .txt/.md files found", "dir": args.text_dir})
 for name in names:
  path = os.path.join(args.text_dir, name)
  try:
   with open(path, encoding="utf-8", errors="replace") as f:
    text = f.read()
  except OSError as e:
   warnings.append({"file": name, "error": str(e)})
   continue
  doc_id = idmap.get(name, os.path.splitext(name)[0])
  paras = []
  for p in split_paragraphs(text):
   paras.extend(chunk_long(p, args.max_para_chars))
  if not paras:
   warnings.append({"file": name,
       "error": "no text extracted (possible parse failure)"})
  docs.append({
   "source_document_id": doc_id,
   "source_file": name,
   "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
   "content_bytes": len(text.encode("utf-8")),
   "paragraph_count": len(paras),
   "paragraphs": [
    {"paragraph_id": "%s::p%03d" % (doc_id, i), "text": p}
    for i, p in enumerate(paras, 1)
   ],
  })

 index = {"index_version": "2.0.0", "documents": docs, "warnings": warnings}
 with open(args.out, "w", encoding="utf-8") as f:
  json.dump(index, f, ensure_ascii=False, indent=1)
 print(json.dumps({
  "out": args.out,
  "documents": [{"id": d["source_document_id"],
     "paragraphs": d["paragraph_count"]} for d in docs],
  "warnings": warnings,
 }, ensure_ascii=False, indent=1))
 return 0 if docs else 1


if __name__ == "__main__":
 sys.exit(main())
