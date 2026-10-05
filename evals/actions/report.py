# ruff: noqa: E501  (each line of the report stays on one line, to be read as it prints)
"""Show a run of the action eval, and put two runs side by side."""

from typing import Any


def pct(entry: dict[str, Any] | None) -> str:
    if not entry or entry.get("rate") is None:
        return "not defined"
    return f"{entry['rate'] * 100:.0f}% ({entry['ok']}/{entry['n']})"


def number(value: float | None, unit: str = "") -> str:
    return "not defined" if value is None else f"{value:g}{unit}"


def lines(summary: dict[str, Any], blind: bool = False) -> list[str]:
    """The headline numbers, in the words of the challenge. A blind run (held-out) shows totals only."""
    s, e = summary, summary["escalation"]
    out = [
        f"attempts {s['attempts']} (provider errors, counted apart: {s['provider_errors']})",
        f"correct end state            {pct(s['correct'])}",
        f"safe automated resolution    {pct(s['safe_automated_resolution'])}, "
        f"automation attempted on {pct(s['safe_automated_resolution']['attempted'])}",
        f"containment (no transfer)    {pct(s['containment'])}",
        f"escalation                   {e['correct']} of {e['expected']} needed one; missed {e['missed']}; unnecessary {e['unnecessary']}",
    ]
    u = s["unsafe"]
    bound = (
        f"; with 0 seen, the true rate could still be up to {u['upper_bound_if_zero']:.0%}"
        if u["upper_bound_if_zero"]
        else ""
    )
    out.append(f"unsafe outcomes              {u['attempts']} of {u['n']}{bound}")
    for kind, count in u["by_type"].items():
        out.append(f"    {kind}: {count}")
    r = s["route"]
    out.append(
        f"router                       model {pct(r['model'])}, rules alone {pct(r['rules_only'])}"
    )
    f = s["efficiency"]
    out.append(
        f"latency p50 / p95            {number(f['seconds_p50'], ' s')} / {number(f['seconds_p95'], ' s')}; "
        f"{number(f['model_calls_mean'])} model calls, {number(f['tokens_in_mean'])} tokens in and "
        f"{number(f['tokens_out_mean'])} out per case"
    )
    out.append(
        f"cost                         per attempt {number(f['cost_per_attempt_usd'], ' USD')}, "
        f"per safe resolution {number(f['cost_per_safe_resolution_usd'], ' USD')} ({f['safe_resolutions']} resolutions)"
    )
    c = s["consistency"]
    if c["cases_repeated"]:
        out.append(
            f"steadiness                   {c['same_every_time']} of {c['cases_repeated']} repeated cases gave the same verdict every time"
        )
    if not blind:
        for title, key in (
            ("category", "by_category"),
            ("language", "by_language"),
            ("segment", "by_segment"),
        ):
            out.append(f"by {title}:")
            out += [
                f"    {name:<14}{pct(entry)}  unsafe {entry['unsafe']}"
                for name, entry in s[key].items()
            ]
    return out


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """The same held-out workload under two systems, one row per measure."""
    rows = [
        ("correct end state", pct(before["correct"]), pct(after["correct"])),
        (
            "safe automated resolution",
            pct(before["safe_automated_resolution"]),
            pct(after["safe_automated_resolution"]),
        ),
        ("containment", pct(before["containment"]), pct(after["containment"])),
        (
            "missed escalations",
            str(before["escalation"]["missed"]),
            str(after["escalation"]["missed"]),
        ),
        (
            "unnecessary escalations",
            str(before["escalation"]["unnecessary"]),
            str(after["escalation"]["unnecessary"]),
        ),
        (
            "unsafe outcomes",
            f"{before['unsafe']['attempts']}/{before['unsafe']['n']}",
            f"{after['unsafe']['attempts']}/{after['unsafe']['n']}",
        ),
        ("router", pct(before["route"]["model"]), pct(after["route"]["model"])),
        (
            "latency p50 (s)",
            number(before["efficiency"]["seconds_p50"]),
            number(after["efficiency"]["seconds_p50"]),
        ),
    ]
    width = max(len(name) for name, _, _ in rows)
    return [f"{'':<{width}}  {'baseline':<18}{'with actions':<18}"] + [
        f"{n:<{width}}  {b:<18}{a:<18}" for n, b, a in rows
    ]
