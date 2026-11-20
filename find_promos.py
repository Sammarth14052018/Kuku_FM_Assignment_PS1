"""Find and rank microdrama promo cuts."""
import argparse
from collections import Counter
import csv
import json
import logging
import math
from pathlib import Path

from llm import ask_json
from parser import Line, parse
from prompts import critic_prompt, single_prompt, stitch_prompt


def timestamp(seconds: float) -> str:
    minutes, ms = divmod(round(seconds * 1000), 60000)
    return f"{minutes:02}:{ms // 1000:02}.{ms % 1000:03}"


def validate(item: dict, episodes: dict[int, list[Line]], single_ep: int | None) -> dict:
    if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip()
                                              for k in ("hook", "cliffhanger", "why")):
        raise ValueError("schema")
    segments = item.get("segments")
    counts = (1,) if single_ep is not None else (2, 3)
    if not isinstance(segments, list) or len(segments) not in counts:
        raise ValueError("index")
    ranges = []
    occupied = set()
    duration = 0.0
    estimated = False
    for seg in segments:
        if not isinstance(seg, dict) or any(type(seg.get(k)) is not int for k in ("ep", "start", "end")):
            raise ValueError("index")
        ep, a, b = seg["ep"], seg["start"], seg["end"]
        lines = episodes.get(ep, [])
        if not 0 <= a <= b < len(lines) or (single_ep is not None and ep != single_ep):
            raise ValueError("index")
        ids = {(ep, i) for i in range(a, b + 1)}
        if occupied & ids:
            raise ValueError("overlap")
        occupied.update(ids)
        ranges.append(dict(ep=ep, start_ts=timestamp(lines[a].start), end_ts=timestamp(lines[b].end)))
        duration += lines[b].end - lines[a].start
        estimated |= any(line.estimated for line in lines[a:b+1])
    duration = round(duration, 3)
    if not 20 <= duration <= 60:
        raise ValueError("duration")
    return dict(kind="single" if single_ep is not None else "stitched", segments=ranges,
                duration_s=duration, hook=item["hook"], cliffhanger=item["cliffhanger"],
                why=item["why"], timing_estimated=estimated, ids=occupied, cuts=segments)


def critic_context(promo: dict, episodes: dict[int, list[Line]]) -> dict:
    clip = []
    opening = []
    remaining = 3.0
    for seg in promo["cuts"]:
        lines = episodes[seg["ep"]]
        selection = lines[seg["start"]:seg["end"]+1]
        clip.append([line.text for line in selection])
        for line in selection:
            if remaining <= 0:
                break
            duration = line.end - line.start
            words = line.text.split()
            count = math.ceil(len(words) * min(1, remaining / duration))
            opening.append(" ".join(words[:count]))
            remaining -= duration
    last = promo["cuts"][-1]
    after = episodes[last["ep"]][last["end"]+1:last["end"]+4]
    return dict(clip=clip, first_3s=opening, after_cut=[line.text for line in after])


def score(critic: dict) -> float:
    ratings = ("hook", "cliffhanger", "standalone")
    flags = ("scroll_stop_3s", "resolved_right_after", "spoils_big_twist")
    if not isinstance(critic, dict) or any(type(critic.get(k)) is not int or
                                           not 1 <= critic[k] <= 10 for k in ratings):
        raise ValueError("invalid critic ratings")
    if any(type(critic.get(k)) is not bool for k in flags):
        raise ValueError("invalid critic flags")
    if not isinstance(critic.get("issues"), list) or not all(isinstance(i, str) for i in critic["issues"]):
        raise ValueError("invalid critic issues")
    value = .4 * critic["hook"] + .3 * critic["cliffhanger"] + .3 * critic["standalone"]
    return round(value - (not critic["scroll_stop_3s"]) - 2 * critic["resolved_right_after"]
                 - critic["spoils_big_twist"], 2)


def propose(system: str, data: dict, label: str, stats: Counter) -> tuple[str, list]:
    result = ask_json(system, json.dumps(data, ensure_ascii=False))
    if not isinstance(result, dict) or not isinstance(result.get("candidates"), list):
        logging.warning("%s: missing candidate response", label)
        stats["llm"] += 1
        return "", []
    return str(result.get("summary", "")), result["candidates"][:5]


def collect(episodes: dict[int, list[Line]], stats: Counter) -> list[dict]:
    proposals = []
    catalog = []
    for ep, lines in episodes.items():
        rows = [[l.idx, l.start, l.end, l.text] for l in lines]
        summary, singles = propose(single_prompt(), dict(ep=ep, lines=rows), f"Episode {ep}", stats)
        proposals.extend((ep, item) for item in singles)
        # Keep the cross-episode catalog affordable for a full season.
        if sum(len(l.text) for l in lines) * len(episodes) > 180000:
            rows = [[i, a, b, text[:100]] for i, a, b, text in rows
                    if "CAMERA:" not in text[:8] or " | " in text]
        catalog.append(dict(ep=ep, summary=summary, lines=rows, singles=singles))
    _, stitched = propose(stitch_prompt(), dict(episodes=catalog), "Stitch stage", stats)
    proposals.extend((None, item) for item in stitched)
    valid = []
    singles_ids = set()
    for ep, item in proposals:
        try:
            promo = validate(item, episodes, ep)
        except ValueError as exc:
            stats[str(exc)] += 1
            continue
        key = frozenset(promo["ids"])
        if ep is None and key in singles_ids:
            stats["duplicate"] += 1
            continue
        if ep is not None:
            singles_ids.add(key)
        valid.append(promo)
    return valid


def describe(promo: dict) -> str:
    return " + ".join(f"Ep {s['ep']} {s['start_ts']} to {s['end_ts']}" for s in promo["segments"])


def rank(episodes: dict[int, list[Line]], top: int, stats: Counter) -> tuple[list[dict], list[str]]:
    scored = []
    flagged = []
    for promo in collect(episodes, stats):
        critic = ask_json(critic_prompt(), json.dumps(critic_context(promo, episodes), ensure_ascii=False))
        try:
            promo["score"] = score(critic)
        except ValueError:
            logging.warning("Missing or invalid critic for %s", describe(promo))
            stats["llm"] += 1
            continue
        promo["critic"] = critic
        issues = list(critic["issues"])
        if critic["resolved_right_after"]:
            issues.append("resolved right after")
        if not critic["scroll_stop_3s"]:
            issues.append("no 3s hook")
        if critic["spoils_big_twist"]:
            issues.append("spoils big twist")
        if issues:
            flagged.append(f"{describe(promo)}: {', '.join(issues)}")
        scored.append(promo)
    occupied = set()
    kept = []
    for promo in sorted(scored, key=lambda p: -p["score"]):
        ids = promo.pop("ids")
        del promo["cuts"]
        if ids & occupied:
            stats["duplicate"] += 1
            continue
        occupied.update(ids)
        if len(kept) < top:
            promo["rank"] = len(kept) + 1
            kept.append(promo)
        else:
            stats["below_top"] += 1
    return kept, flagged


def write_outputs(out: Path, kept: list[dict], flagged: list[str], stats: Counter,
                  episodes: dict[int, list[Line]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "promos.json").write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    md = ["# Ranked promos", "", "## Why #1 goes first", ""]
    if kept:
        best = kept[0]
        md.append(f"{best['why']} Its weighted score after penalties is {best['score']:.1f}.")
    else:
        md.append("No eligible promos survived validation and review.")
    for p in kept:
        md.extend(["", f"## {p['rank']}. {describe(p)}", "",
                   f"{p['kind']} | {p['duration_s']}s | score {p['score']}",
                   "", f"- Hook: {p['hook']}", f"- Cliffhanger: {p['cliffhanger']}", f"- Why: {p['why']}"])
    (out / "promos.md").write_text("\n".join(md) + "\n", encoding="utf8")
    counts = Counter(s["ep"] for p in kept for s in p["segments"])
    report = ["# Quality report", "", f"- Kept: {len(kept)}",
              f"- Rejected (bad duration): {stats['duration']}", f"- Rejected (bad index): {stats['index']}",
              f"- Rejected (overlap): {stats['overlap']}", f"- Rejected (schema): {stats['schema']}",
              f"- LLM JSON failures (includes unavailable responses): {stats['llm']}",
              f"- Dedup dropped: {stats['duplicate']}", f"- Below top N: {stats['below_top']}",
              "", "## Kept segments per episode", ""]
    report.extend(f"- Episode {ep}: {counts[ep]}" for ep in episodes)
    report.extend(["", f"## Critic flags before ranking ({len(flagged)})", ""])
    report.extend(f"- {row}" for row in flagged or ["None"])
    report.extend(["", "## Known failure modes", "",
                   "- Cliffhanger cut too late: inspect the final line and its answer.",
                   "- Hook needs prior context: review the clip without the episode summary.",
                   "- Words-only hook with no visuals: verify the opening shot in footage.",
                   "- Big twist spoiled: check whether the reveal spends the show's payoff.",
                   "- Clustering in few episodes: inspect the episode counts above.",
                   "- Estimated timestamps: confirm cuts against recorded dialogue."])
    (out / "quality_report.md").write_text("\n".join(report) + "\n", encoding="utf8")
    with (out / "eval_sheet.csv").open("w", newline="", encoding="utf8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["rank", "segments", "tool_score", "human_hook_1to5", "human_cliff_1to5",
                         "human_standalone_1to5", "would_post(Y/N)", "failure_type", "notes"])
        for p in kept:
            writer.writerow([p["rank"], describe(p), p["score"], "", "", "", "", "", ""])


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("screenplay", type=Path)
    cli.add_argument("--out", type=Path, default=Path("out"))
    cli.add_argument("--top", type=int, default=10)
    args = cli.parse_args(argv)
    if args.top < 1:
        cli.error("--top must be positive")
    try:
        episodes = parse(args.screenplay.read_text(encoding="utf-8-sig"))
        if not episodes:
            raise ValueError("No screenplay lines found")
        stats = Counter()
        kept, flags = rank(episodes, args.top, stats)
        write_outputs(args.out, kept, flags, stats, episodes)
    except (OSError, ValueError) as exc:
        logging.error("%s", exc)
        return 1
    print(f"Wrote {len(kept)} ranked promos to {args.out}")
    return int(not kept and stats["llm"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
