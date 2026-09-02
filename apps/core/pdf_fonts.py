"""Bundled ReportLab fonts matching the web application's typography."""

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PDF_DISPLAY_FONT = "StoreTrackFrauncesSemiBold"
PDF_BODY_FONT = "StoreTrackInter"
PDF_BODY_BOLD_FONT = "StoreTrackInterSemiBold"
PDF_BODY_ITALIC_FONT = "StoreTrackInterItalic"
PDF_BODY_BOLD_ITALIC_FONT = "StoreTrackInterSemiBoldItalic"
PDF_MONO_FONT = "StoreTrackPlexMono"
PDF_MONO_MEDIUM_FONT = "StoreTrackPlexMonoMedium"

_FONT_DIR = Path(__file__).resolve().parent / "static" / "core" / "fonts"
_FONT_FILES = {
    PDF_DISPLAY_FONT: "Fraunces-SemiBold.ttf",
    PDF_BODY_FONT: "Inter-Regular.ttf",
    PDF_BODY_BOLD_FONT: "Inter-SemiBold.ttf",
    PDF_BODY_ITALIC_FONT: "Inter-Italic.ttf",
    PDF_BODY_BOLD_ITALIC_FONT: "Inter-SemiBoldItalic.ttf",
    PDF_MONO_FONT: "IBMPlexMono-Regular.ttf",
    PDF_MONO_MEDIUM_FONT: "IBMPlexMono-Medium.ttf",
}


def register_pdf_fonts():
    """Register the bundled UI font families with ReportLab once per process."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    for font_name, filename in _FONT_FILES.items():
        if font_name not in registered:
            pdfmetrics.registerFont(TTFont(font_name, str(_FONT_DIR / filename)))

    pdfmetrics.registerFontFamily(
        PDF_BODY_FONT,
        normal=PDF_BODY_FONT,
        bold=PDF_BODY_BOLD_FONT,
        italic=PDF_BODY_ITALIC_FONT,
        boldItalic=PDF_BODY_BOLD_ITALIC_FONT,
    )
    pdfmetrics.registerFontFamily(
        PDF_MONO_FONT,
        normal=PDF_MONO_FONT,
        bold=PDF_MONO_MEDIUM_FONT,
        italic=PDF_MONO_FONT,
        boldItalic=PDF_MONO_MEDIUM_FONT,
    )


register_pdf_fonts()
