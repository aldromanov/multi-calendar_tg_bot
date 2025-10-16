def format_event(ev: dict, name_width: int = 25) -> str:
    start = ev.get("start")
    try:
        start_str = start.strftime("%d.%m %H:%M")
    except Exception:
        start_str = str(start)

    summary = ev.get("summary", "(без названия)")
    if len(summary) > name_width:
        summary = summary[: name_width - 3] + "..."
    summary_padded = summary.ljust(name_width)

    return f"📌 <code>{summary_padded} | {start_str}</code>"


def get_user_id(user):
    return getattr(user, "id", "0")
