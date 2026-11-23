#!/usr/bin/env python3
"""render_preview.py: SVG -> real PNG preview + PDF export, with evidence. Stdlib only.

Usage: render_preview.py figure.svg preview.png figure.pdf
Backend chain (probed honestly, in order):
  rsvg-convert -> inkscape -> soffice -> ImageMagick(magick/convert) -> cairosvg -> PyMuPDF.
Every produced file is VERIFIED (PNG signature + IHDR dimensions + non-trivial size;
PDF header + size) and reported as JSON evidence for result.json's export checkpoint.
If every backend is unavailable or produces invalid output, exits 3 and prints
"preview_unavailable"; callers must record this honestly instead of fabricating a preview.
"""
import json, os, shutil, struct, subprocess, sys, tempfile


def try_cmd(cmd, timeout=180):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode == 0
    except Exception:
        return False


def png_dims(path):
    """Parse PNG signature + IHDR (stdlib); None if invalid."""
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            f.read(4)
            if f.read(4) != b"IHDR":
                return None
            return struct.unpack(">II", f.read(8))
    except OSError:
        return None


def valid_png(path):
    return os.path.isfile(path) and os.path.getsize(path) > 100 and png_dims(path) is not None


def valid_pdf(path):
    try:
        return os.path.getsize(path) > 200 and open(path, "rb").read(5) == b"%PDF-"
    except OSError:
        return False


def soffice_render(svg, png, pdf):
    """LibreOffice Draw export; output named after input basename, so work in tmpdir."""
    with tempfile.TemporaryDirectory() as td:
        stem = os.path.splitext(os.path.basename(svg))[0]
        env_arg = f"-env:UserInstallation=file://{td}/profile"
        ok_png = try_cmd(["soffice", "--headless", env_arg, "--convert-to", "png",
                          "--outdir", td, svg]) and os.path.isfile(os.path.join(td, stem + ".png"))
        ok_pdf = try_cmd(["soffice", "--headless", env_arg, "--convert-to", "pdf",
                          "--outdir", td, svg]) and os.path.isfile(os.path.join(td, stem + ".pdf"))
        if ok_png:
            shutil.move(os.path.join(td, stem + ".png"), png)
        if ok_pdf:
            shutil.move(os.path.join(td, stem + ".pdf"), pdf)
        return ok_png, ok_pdf


def render(svg, png, pdf):
    if shutil.which("rsvg-convert"):
        ok_png = try_cmd(["rsvg-convert", "-d", "300", "-o", png, svg]) and valid_png(png)
        ok_pdf = try_cmd(["rsvg-convert", "-f", "pdf", "-o", pdf, svg]) and valid_pdf(pdf)
        if ok_png or ok_pdf:
            return "rsvg-convert", ok_png, ok_pdf
    if shutil.which("inkscape"):
        ok_png = try_cmd(["inkscape", svg, "--export-type=png", f"--export-filename={png}",
                          "--export-dpi=300"]) and valid_png(png)
        ok_pdf = try_cmd(["inkscape", svg, "--export-type=pdf", f"--export-filename={pdf}"]) \
            and valid_pdf(pdf)
        if ok_png or ok_pdf:
            return "inkscape", ok_png, ok_pdf
    if shutil.which("soffice"):
        ok_png, ok_pdf = soffice_render(svg, png, pdf)
        ok_png, ok_pdf = ok_png and valid_png(png), ok_pdf and valid_pdf(pdf)
        if ok_png or ok_pdf:
            return "soffice", ok_png, ok_pdf
    magick = shutil.which("magick") or shutil.which("convert")
    if magick:
        ok_png = try_cmd([magick, "-density", "300", svg, png]) and valid_png(png)
        ok_pdf = try_cmd([magick, svg, pdf]) and valid_pdf(pdf)
        if ok_png or ok_pdf:
            return "imagemagick", ok_png, ok_pdf
    try:
        import cairosvg
        ok_png = ok_pdf = False
        try:
            cairosvg.svg2png(url=svg, write_to=png, dpi=300)
            ok_png = valid_png(png)
        except Exception:
            pass
        try:
            cairosvg.svg2pdf(url=svg, write_to=pdf)
            ok_pdf = valid_pdf(pdf)
        except Exception:
            pass
        if ok_png or ok_pdf:
            return "cairosvg", ok_png, ok_pdf
    except ImportError:
        pass
    try:
        import fitz  # PyMuPDF (pdf-render tool)
        doc = fitz.open(svg)
        ok_pdf = ok_png = False
        try:
            with open(pdf, "wb") as f:
                f.write(doc.convert_to_pdf())
            ok_pdf = valid_pdf(pdf)
        except Exception:
            pass
        try:
            pdfdoc = fitz.open("pdf", open(pdf, "rb").read()) if ok_pdf else None
            page = (pdfdoc or doc).load_page(0)
            page.get_pixmap(dpi=300).save(png)
            ok_png = valid_png(png)
        except Exception:
            pass
        if ok_png or ok_pdf:
            return "pymupdf", ok_png, ok_pdf
    except ImportError:
        pass
    return None, False, False


def evidence(path, png, pdf, backend, ok_png, ok_pdf):
    ev = {"backend": backend}
    if ok_png:
        w, h = png_dims(png)
        ev["png"] = {"path": os.path.basename(png), "bytes": os.path.getsize(png),
                     "width_px": w, "height_px": h}
    if ok_pdf:
        ev["pdf"] = {"path": os.path.basename(pdf), "bytes": os.path.getsize(pdf)}
    return ev


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: render_preview.py figure.svg preview.png figure.pdf")
    backend, ok_png, ok_pdf = render(sys.argv[1], sys.argv[2], sys.argv[3])
    if backend is None:
        print("preview_unavailable: no working SVG backend "
              "(rsvg-convert/inkscape/soffice/ImageMagick/cairosvg/PyMuPDF)")
        sys.exit(3)
    print(json.dumps(evidence(sys.argv[1], sys.argv[2], sys.argv[3], backend, ok_png, ok_pdf)))
    sys.exit(0 if (ok_png or ok_pdf) else 4)


if __name__ == "__main__":
    main()
