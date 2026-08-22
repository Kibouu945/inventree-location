"""PDF generation for return reports using WeasyPrint."""

from __future__ import annotations

from io import BytesIO

from django.template.loader import render_to_string
from django.utils.html import escape
from weasyprint import HTML

from .return_report import build_return_report


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

    buffer = BytesIO()
    HTML(string=html_string).write_pdf(buffer)
    buffer.seek(0)
    return buffer