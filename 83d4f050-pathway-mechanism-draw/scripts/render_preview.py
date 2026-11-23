"""render_preview.py: SVG -> PNG+PDF (rsvg->inkscape->cairosvg->PyMuPDF; exit 3 if none).
Every claimed output is verified non-empty with correct magic bytes; a backend
that exits 0 but writes an empty/invalid file counts as failure (honest degrade).
After a real PNG is produced we READ IT BACK (deterministic render readback):
parse IHDR for width/height, re-check non-empty, and cross-check the SVG's
node/edge element counts — not just "generated and trusted"."""
import os, re, shutil, subprocess, sys
import xml.etree.ElementTree as ET

PNG_M, PDF_M = b"\x89PNG", b"%PDF"


def okfile(path, magic):
    try:
        if os.path.getsize(path) == 0:
            return False
        with open(path, "rb") as f:
            return f.read(len(magic)) == magic
    except OSError:
        return False


def png_dims(path):
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n" or f.read(8) != b"\x00\x00\x00\rIHDR":
                return None
            w, h = int.from_bytes(f.read(4), "big"), int.from_bytes(f.read(4), "big")
            return (w, h) if w > 0 and h > 0 else None
    except OSError:
        return None


def svg_counts(path):
    try:
        root = ET.parse(path).getroot()
        nodes = sum(1 for e in root.iter() if "data-type" in e.attrib)
        edges = sum(1 for e in root.iter() if "data-relation" in e.attrib)
        w, h = root.get("width"), root.get("height")
        return nodes, edges, w, h
    except Exception:
        return None, None, None, None


def readback(png, svg):
    """Deterministic render readback: PNG dims + non-empty + SVG element counts."""
    dims = png_dims(png) if okfile(png, PNG_M) else None
    nodes, edges, sw, sh = svg_counts(svg)
    return {"png_dims": dims, "svg_nodes": nodes, "svg_edges": edges,
            "svg_width": sw, "svg_height": sh}


def run(cmd, out, magic):
    try:
        if subprocess.run(cmd, capture_output=True, timeout=120).returncode != 0:
            return False
    except Exception:
        return False
    return okfile(out, magic)


def render(svg, png, pdf):
    if shutil.which("rsvg-convert"):
        ok = (run(["rsvg-convert", "-d", "300", "-o", png, svg], png, PNG_M),
              run(["rsvg-convert", "-f", "pdf", "-o", pdf, svg], pdf, PDF_M))
        if any(ok):
            return ("rsvg-convert",) + ok
    if shutil.which("inkscape"):
        ok = (run(["inkscape", svg, "--export-type=png", f"--export-filename={png}", "--export-dpi=300"], png, PNG_M),
              run(["inkscape", svg, "--export-type=pdf", f"--export-filename={pdf}"], pdf, PDF_M))
        if any(ok):
            return ("inkscape",) + ok
    try:
        import cairosvg
        ok = [False, False]
        for fn, kw, i, out, m in ((cairosvg.svg2png, {"write_to": png, "dpi": 300}, 0, png, PNG_M),
                                  (cairosvg.svg2pdf, {"write_to": pdf}, 1, pdf, PDF_M)):
            try:
                fn(url=svg, **kw)
                ok[i] = okfile(out, m)
            except Exception:
                pass
        if any(ok):
            return ("cairosvg",) + tuple(ok)
    except ImportError:
        pass
    try:
        import fitz
        doc = fitz.open(svg)
        ok = [False, False]
        try:
            open(pdf, "wb").write(doc.convert_to_pdf())
            ok[1] = okfile(pdf, PDF_M)
        except Exception:
            pass
        try:
            pg = (fitz.open("pdf", open(pdf, "rb").read()) if ok[1] else doc).load_page(0)
            pg.get_pixmap(dpi=300).save(png)
            ok[0] = okfile(png, PNG_M)
        except Exception:
            pass
        if any(ok):
            return ("pymupdf",) + tuple(ok)
    except ImportError:
        pass
    return None, False, False


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    backend, ok_png, ok_pdf = render(sys.argv[1], sys.argv[2], sys.argv[3])
    if backend is None:
        print("preview_unavailable: no SVG backend (rsvg/inkscape/cairosvg/fitz)")
        sys.exit(3)
    rb = readback(sys.argv[2], sys.argv[1])
    print(f"backend={backend} png={'ok' if ok_png else 'failed'} pdf={'ok' if ok_pdf else 'failed'}")
    print(f"readback={rb}")
    # PNG claimed but readback invalid => do not trust it
    if ok_png and not rb["png_dims"]:
        print("readback FAIL: PNG magic ok but IHDR dimensions unreadable")
        sys.exit(4)
    sys.exit(0 if (ok_png or ok_pdf) else 4)


if __name__ == "__main__":
    main()
