from __future__ import annotations

from typing import Any


def daily_to_markdown(summary: dict[str, Any]) -> str:
    overview = summary["overview"]
    lines = [
        f"# GPU Daily Report - {summary['report_date']}",
        "",
        f"- Server: {_text(overview.get('server_name'))}",
        f"- Generated: {_text(summary.get('generated_at'))}",
        f"- Range: {_text(summary.get('range_start'))} to {_text(summary.get('range_end'))}",
        "",
        "## Overview",
        "",
        _table(
            ["Metric", "Value"],
            [
                ["Active Users", overview.get("active_user_count")],
                ["Used GPUs", overview.get("used_gpu_count")],
                ["Total Usage", overview.get("total_usage_human")],
                ["Sample Interval", f"{overview.get('sample_interval_seconds')}s"],
                ["Active Threshold", f"{overview.get('active_memory_threshold_mb')} MB"],
                ["Heartbeat Gaps", overview.get("heartbeat_gap_count")],
                ["Unknown Processes", overview.get("unknown_process_count")],
                ["Errors", overview.get("error_count")],
            ],
        ),
        "",
        "## Users",
        "",
        _table(
            ["User", "GPUs", "Duration", "Avg Memory", "Peak Memory"],
            [
                [
                    _display_name(user),
                    _gpu_indexes(user.get("gpu_indexes")),
                    user.get("duration_human"),
                    _gb(user.get("avg_memory_gb")),
                    _gb(user.get("peak_memory_gb")),
                ]
                for user in summary.get("users", [])
            ],
        ),
        "",
        "## GPU Summary",
        "",
        _table(
            ["GPU", "Users", "Duration", "Peak Memory"],
            [
                [
                    f"GPU {gpu.get('gpu_index')}",
                    ", ".join(_text(user) for user in gpu.get("users", [])),
                    gpu.get("duration_human"),
                    _gb(gpu.get("peak_memory_gb")),
                ]
                for gpu in summary.get("gpus", [])
            ],
        ),
        "",
        "## User GPU Detail",
        "",
        _table(
            ["User", "GPU", "Sessions", "Duration", "Avg Memory", "Peak Memory"],
            [
                [
                    _display_name(entry),
                    f"GPU {entry.get('gpu_index')}",
                    _sessions(entry.get("sessions", [])),
                    entry.get("duration_human"),
                    _gb(entry.get("avg_memory_gb")),
                    _gb(entry.get("peak_memory_gb")),
                ]
                for entry in summary.get("user_gpu", [])
            ],
        ),
    ]
    notes = summary.get("notes") or []
    if notes:
        lines.extend(["", "## Notes", "", *[f"- {_text(note)}" for note in notes]])
    return "\n".join(lines).rstrip() + "\n"


def weekly_to_markdown(summary: dict[str, Any]) -> str:
    overview = summary["overview"]
    lines = [
        f"# GPU Weekly Report - {summary['week_start']} to {summary['week_end']}",
        "",
        f"- Server: {_text(overview.get('server_name'))}",
        f"- Generated: {_text(summary.get('generated_at'))}",
        f"- Range: {_text(summary.get('range_start'))} to {_text(summary.get('range_end'))}",
        "",
        "## Overview",
        "",
        _table(
            ["Metric", "Value"],
            [
                ["Active Users", overview.get("active_user_count")],
                ["Used GPUs", overview.get("used_gpu_count")],
                ["Total Usage", overview.get("total_usage_human")],
                ["Heartbeat Gaps", overview.get("heartbeat_gap_count")],
                ["Errors", overview.get("error_count")],
                ["Empty Days", ", ".join(overview.get("missing_or_empty_dates", [])) or "-"],
                ["Future Days", ", ".join(overview.get("future_dates", [])) or "-"],
            ],
        ),
        "",
        "## Users",
        "",
        _table(
            ["User", "GPUs", "Active Days", "Duration", "Daily Avg Usage", "Avg Memory", "Peak Memory"],
            [
                [
                    _display_name(user),
                    _gpu_indexes(user.get("gpu_indexes")),
                    user.get("active_days"),
                    user.get("duration_human"),
                    user.get("daily_avg_usage_human"),
                    _gb(user.get("avg_memory_gb")),
                    _gb(user.get("peak_memory_gb")),
                ]
                for user in summary.get("users", [])
            ],
        ),
        "",
        "## GPU Summary",
        "",
        _table(
            ["GPU", "Users", "Active Days", "Duration", "Peak Memory"],
            [
                [
                    f"GPU {gpu.get('gpu_index')}",
                    ", ".join(_text(user) for user in gpu.get("users", [])),
                    gpu.get("active_days"),
                    gpu.get("duration_human"),
                    _gb(gpu.get("peak_memory_gb")),
                ]
                for gpu in summary.get("gpus", [])
            ],
        ),
        "",
        "## Daily Breakdown",
        "",
        _table(
            ["Date", "Users", "GPUs", "Usage", "Heartbeat Gaps", "Errors"],
            [
                [
                    day.get("date"),
                    day.get("active_user_count"),
                    day.get("used_gpu_count"),
                    day.get("total_usage_human"),
                    day.get("heartbeat_gap_count"),
                    day.get("error_count"),
                ]
                for day in summary.get("daily", [])
            ],
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No records_"
    header = "| " + " | ".join(_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _cell(value: Any) -> str:
    return _text(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _text(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _display_name(record: dict[str, Any]) -> str:
    return _text(record.get("display_name") or record.get("username"))


def _gpu_indexes(value: Any) -> str:
    if not value:
        return "-"
    return ", ".join(f"GPU {item}" for item in value)


def _gb(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return f"{value} GB"


def _sessions(sessions: list[dict[str, Any]]) -> str:
    if not sessions:
        return "-"
    return "<br>".join(
        f"{_short_time(session.get('start_time'))} - {_short_time(session.get('end_time'))} ({_text(session.get('duration_human'))})"
        for session in sessions
    )


def _short_time(value: Any) -> str:
    text = _text(value)
    if "T" in text and len(text) >= 19:
        return text[11:19]
    return text
