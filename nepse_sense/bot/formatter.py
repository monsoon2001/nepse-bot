import html


def escape_html(text: str) -> str:
    return html.escape(str(text))


def format_signal_message(symbol: str, signal, data_asof: str = "") -> str:
    lines = [
        f"<b>{escape_html(symbol)}</b>",
        f"Category: <b>{escape_html(signal.category)}</b>",
        f"Score: {signal.score}/100",
        f"Confidence: {escape_html(signal.confidence_tier)}",
        "",
        "<b>Reasons:</b>",
    ]
    for r in signal.reasons:
        lines.append(f"  • {escape_html(r)}")
    if signal.risk_flags:
        lines.append("")
        lines.append("<b>Risk Flags:</b>")
        for rf in signal.risk_flags:
            lines.append(f"  ⚠️ {escape_html(rf)}")
    if data_asof:
        lines.append("")
        lines.append(f"<i>Data as of: {escape_html(data_asof)}</i>")
    lines.append("")
    lines.append("<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)


def paginate(items: list, page: int = 1, per_page: int = 5) -> tuple[list, int]:
    total_pages = (len(items) + per_page - 1) // per_page
    total_pages = max(1, total_pages)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], page, total_pages
