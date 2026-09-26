"""PDF generation for return reports using WeasyPrint."""

from __future__ import annotations

from io import BytesIO

from django.template.loader import render_to_string
from django.utils.html import escape

from .return_report import build_return_report


class PdfEngineUnavailable(RuntimeError):
    """WeasyPrint n'est pas installé ou ses dépendances natives manquent."""


def _load_html_engine():
    """Charge WeasyPrint à la demande, en signalant proprement son absence."""

    try:
        from weasyprint import HTML
    except ImportError as error:  # pragma: no cover - dépend de l'environnement
        raise PdfEngineUnavailable(
            "L'export PDF nécessite WeasyPrint et ses bibliothèques natives."
        ) from error

    return HTML


def _format_amount(value) -> str:
    return f"{float(value):.2f} €"


def generate_return_report_pdf(reservation_id: int) -> BytesIO:
    """Generate a printable PDF for a reservation return report."""
    data = build_return_report(reservation_id)

    for line in data["lines"]:
        line["extra_cost_label"] = _format_amount(line["extra_cost"])

    data["total_extra_label"] = _format_amount(data["total_extra"])

    context = {
        "data": data,
        "escape": escape,
    }

    html_string = render_to_string("return_report.html", context)
    html_engine = _load_html_engine()

    buffer = BytesIO()
    html_engine(string=html_string).write_pdf(buffer)
    buffer.seek(0)
    return buffer
