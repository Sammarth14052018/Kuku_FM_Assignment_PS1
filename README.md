# Find the Promos

A Python CLI for Kuku's AI Generalist Assignment, Problem 1. It helps an editor find 20 to 60 seconds of existing footage that could introduce a microdrama to a first-time viewer on Instagram, TikTok or YouTube. Each recommendation gives the episode, exact cut points, opening hook, unresolved ending and reason to post it. For a stitched promo, the segments are listed in playback order.

**Start with the completed run.** The tool processed 50 episodes and returned 10 picks from eight episodes. Nine are continuous cuts and one joins two segments. The assignment report explains the approach and audits the top pick. [Ranked promos](out-full/promos.md) · [Two-page solution report](submission-report/Find%20the%20Promos%20-%20Solution%20Report.pdf)

## Run the sample

From the repository root, use Python 3.12 or newer. The sample contains three original episodes and can be shared for demonstrations.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Choose a provider and set its key in the same terminal. The CLI reads environment variables directly.

| `PROVIDER` | API key variable | Default model |
|---|---|---|
| `openai` (default) | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |

For example, in zsh, enter an OpenAI key without displaying it or saving it in command history:

```zsh
export PROVIDER=openai
read -rs 'OPENAI_API_KEY?Paste your OpenAI API key and press Enter: '
export OPENAI_API_KEY
python find_promos.py sample_screenplay.txt --out runs/sample --top 10
```

Set `MODEL` to override the selected provider's default. Choose a model that supports temperature control. The default output directory is `out/`, and the default shortlist size is 10. Use a fresh output directory for each run because the CLI replaces its reports, including the evaluation sheet.

## Supply a screenplay

Pass one UTF-8 text file. The parser accepts bracketed timestamps such as `[00:12] LENA: Who sent this?`, plain `mm:ss` or `hh:mm:ss` entries, SRT cues, and Kuku's native timestamped action and dialogue blocks. Episode headers include `EPISODE 1`, `Episode 2` and `# Ep 3`. Times are local to each episode.

Untimed text following a timestamp continues the current entry. Each entry ends at the next distinct start time. Without an explicit final end, the parser estimates the last entry's length. For a fully untimed episode it uses 2.5 words per second, with a minimum of 1.5 seconds per line. Cuts using inferred times carry `timing_estimated: true`.

If you have Kuku's private input pack locally, combine the numbered files in order. The extra newline preserves the episode boundary even when a file has no trailing newline.

```sh
season_file=$(mktemp)
for episode in "I Married a Broken Soldier. He was a Duke"/episode-*.txt; do
  cat "$episode"
  printf '\n'
done > "$season_file"
python find_promos.py "$season_file" --out runs/full-season --top 10
rm "$season_file"
```

The selected API provider receives screenplay text. Keep Kuku's source pack out of public repositories and shared demos.

## How selection works

1. **Parse.** `parser.py` creates an episode-local timeline of indexed screenplay lines and groups camera, action and dialogue entries with the same start time.
2. **Propose.** Using the instructions in `prompts.py`, the model summarizes each episode and suggests up to five continuous cuts. A second pass sees all episodes, uses compact excerpts for larger inputs, and proposes up to five promos of two or three segments.
3. **Validate.** `find_promos.py` checks episode IDs, inclusive line ranges, segment overlap and total duration. For stitched clips, duration is the sum of the selected segments.
4. **Critique.** A separate prompt scores hook, cliffhanger and standalone clarity from 1 to 10. It receives the selected text in playback order, an approximate first-three-second excerpt and up to three unseen lines after the final cut.
5. **Rank.** The score weights hook at 40%, cliffhanger at 30% and standalone clarity at 30%. A weak opening costs one point, immediate resolution costs two, and spoiling a major twist costs one. Higher-scoring promos claim their source footage first. The CLI returns the top remaining cuts.

`llm.py` handles both official SDKs and retries malformed JSON once. Calls run sequentially: one per episode, one stitching call, then one critique per valid candidate. Lowering `--top` shortens the final list without reducing critique calls. Provider charges depend on the model and usage. Failed responses are logged so other candidates can still be processed.

## Read and evaluate a run

| Output from the full run | Use |
|---|---|
| [promos.md](out-full/promos.md) | Read the ranked shortlist and the reason the first pick leads. |
| [promos.json](out-full/promos.json) | Retrieve episode-local timestamps, playback order, duration, scores, critic flags and timing confidence. |
| [quality_report.md](out-full/quality_report.md) | Inspect rejected ranges, failed model responses, duplicates, episode coverage and critic issues. |
| [eval_sheet.csv](out-full/eval_sheet.csv) | Record a human posting decision for each cut. |

Of 250 proposals in the full run, 95 failed duration checks, 62 failed index checks, six were dropped as duplicates and 77 fell below the top ten. The report recorded zero LLM JSON failures. Editorial scores still need human review. For example, the first pick starts at 02:30.500 in episode 36, but the spoken warning credited as its hook starts at 02:33.500. An editor should preview what the viewer actually hears in those first three seconds.

To evaluate the shortlist, copy the CSV, hide `tool_score`, and preview each cut as a new viewer. Rate the hook, cliffhanger and standalone clarity from 1 (weak) to 5 (strong). Enter Y or N for `would_post(Y/N)` and use `failure_type` and `notes` to identify the exact moment behind the decision. The saved full-run sheet has blank human ratings.

## Test without an API key

```sh
python -m pytest -q
python -m pytest -q tests/test_validation.py::test_sample_cli
```

The suite covers parsing, time estimation, validation, scoring, JSON retry and recovery from a failed episode call. The second command runs the sample through the CLI entry point with mocked model responses and verifies all four output files.
