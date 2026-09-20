"""Render the exported PPTX with LibreOffice, then rasterize its PDF with Poppler."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def render_pptx_preview(
    data: bytes,
    *,
    soffice: str,
    pdftoppm: str,
    expected_pages: int,
) -> list[bytes]:
    with TemporaryDirectory(prefix="aippt-preview-") as directory:
        root = Path(directory)
        source = root / "deck.pptx"
        source.write_bytes(data)
        profile = (root / "lo-profile").as_uri()
        subprocess.run(
            [
                soffice,
                f"-env:UserInstallation={profile}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(root),
                str(source),
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )
        pdf = root / "deck.pdf"
        if not pdf.is_file():
            raise RuntimeError("办公渲染引擎未输出 PDF")
        subprocess.run(
            [pdftoppm, "-png", "-scale-to", "1440", str(pdf), str(root / "page")],
            check=True,
            timeout=120,
            capture_output=True,
        )
        pages = sorted(root.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        if len(pages) != expected_pages:
            raise RuntimeError("实际渲染页数与 PPTX 页数不一致")
        return [page.read_bytes() for page in pages]
