import datetime as dt

from config import TZINFO, AHEAD_HOUR


def format_event(ev: dict, name_width: int = 25) -> str:
    start = ev.get("start")
    now = dt.datetime.now(TZINFO)
    mark = "⌛️" if start < now else "📌"

    try:
        start_str = start.strftime("%d.%m %H:%M")
    except Exception:
        start_str = str(start)

    summary = ev.get("summary", "(без названия)")
    if len(summary) > name_width:
        summary = summary[: name_width - 3] + "..."

    summary_padded = summary.ljust(name_width)

    return f"<code>{mark} {start_str} | {summary_padded}</code>"


def get_user_id(user):
    username = getattr(user, "username", "anon")
    id = getattr(user, "id", "0")
    return f"{username} ({id})"


def get_notify_time(ahead_hours: int = AHEAD_HOUR) -> list[int]:
    geometry = [ahead_hours * 60]
    while geometry[-1] > 60:
        next_val = max(60, geometry[-1] // 2)
        if next_val == geometry[-1]:
            break
        geometry.append(next_val)

    minute_stage = [30, 15, 10, 5, 0]
    notify_points = geometry + minute_stage
    return sorted(set(notify_points), reverse=True)
