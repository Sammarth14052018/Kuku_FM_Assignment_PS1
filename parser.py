"""Parse episode-local timelines. Line indices are zero based."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Line:
    ep: int
    idx: int
    start: float
    end: float
    text: str
    estimated: bool


def seconds(stamp: str) -> float:
    total = 0.0
    for part in stamp.replace(",", ".").split(":"):
        total = total * 60 + float(part)
    return round(total, 3)


def estimate(text: str) -> float:
    return max(1.5, len(text.split()) / 2.5)


def parse_episode(ep: int, rows: list[str]) -> list[Line]:
    stamp = r"(?:\d+:)?\d+:\d{2}(?:[.,]\d{1,3})?"
    timed: list[tuple[float, float | None, str]] = []
    prefix: list[str] = []
    native = any(row.startswith("EPISODE LOGLINE:") for row in rows) and any(
        row.startswith("Start: (") for row in rows)
    label = ""
    for i, row in enumerate(rows):
        if native:
            if row.startswith("**"):
                label = row.strip("*").rstrip(":")
                continue
            match = re.fullmatch(rf"Start: \(({stamp})\)\s*\|\s*End: \(({stamp})\)", row)
            if match:
                timed.append((seconds(match[1]), seconds(match[2]), label + ":"))
            elif timed and not row.startswith(("SCENE ", "Scene ", "---", "Actions and dialogue")):
                start, end, text = timed[-1]
                timed[-1] = start, end, text + " " + row
            continue
        if row.isdecimal() and i + 1 < len(rows) and "-->" in rows[i + 1]:
            continue
        cue = re.fullmatch(rf"({stamp})\s*-->\s*({stamp}).*", row)
        entry = re.fullmatch(rf"\[?({stamp})\]?\s+(.*)", row)
        if cue or entry:
            match = cue or entry
            text = "" if cue else match[2]
            timed.append((seconds(match[1]), seconds(match[2]) if cue else None,
                          " ".join([*prefix, text]).strip()))
            prefix.clear()
        elif timed:
            start, end, text = timed[-1]
            timed[-1] = start, end, (text + " " + row).strip()
        else:
            prefix.append(row)
    if not timed:
        lines = []
        start = 0.0
        for i, text in enumerate(prefix):
            end = round(start + estimate(text), 3)
            lines.append(Line(ep, i, start, end, text, True))
            start = end
        return lines
    if native:
        timed.sort(key=lambda item: item[0])
    merged: list[tuple[float, str]] = []
    for start, _, text in timed:
        if merged and start < merged[-1][0]:
            raise ValueError(f"Episode {ep}: timestamps go backwards")
        if merged and start == merged[-1][0]:
            merged[-1] = start, merged[-1][1] + " | " + text
        else:
            merged.append((start, text))
    last_start, last_text = merged[-1]
    last_end = max((end for _, end, _ in timed if end is not None), default=0)
    inferred = last_end <= last_start
    if inferred:
        last_end = round(last_start + estimate(last_text), 3)
    bounds = [start for start, _ in merged] + [last_end]
    return [Line(ep, i, start, bounds[i+1], text, inferred and i == len(merged)-1)
            for i, (start, text) in enumerate(merged)]


def parse(source: str) -> dict[int, list[Line]]:
    groups: dict[int, list[str]] = {}
    ep = 1
    for raw in source.splitlines():
        row = raw.strip().lstrip("\ufeff")
        header = re.fullmatch(r"(?:EPISODE NUMBER:\s*)?#?\s*Ep(?:isode)?\s+(\d+)", row, re.I)
        if header:
            ep = int(header[1])
            if ep in groups:
                raise ValueError(f"Repeated episode number {ep}")
        elif row:
            groups.setdefault(ep, []).append(row)
    return {ep: lines for ep, rows in groups.items() if (lines := parse_episode(ep, rows))}
