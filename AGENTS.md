# Repository Guidelines

## Project structure

Read `Kuku — AI Generalist Assignment (1).pdf` for the problem statements, submission requirements, and evaluation criteria. The directory `I Married a Broken Soldier. He was a Duke/` contains 50 timestamped episode screenplays. In filenames such as `episode-001-Episode 1671703.txt`, the three-digit prefix gives the episode order. Preserve the supplied filenames and timestamps so reviewers can trace results back to the original scenes.

## Local inspection

Run these commands from the workspace root with ripgrep installed.

- `rg --files -g 'episode-*.txt' | sort` lists the screenplays in episode order.
- `rg -n '^SCENE ' -g 'episode-001-*.txt'` locates scene headings in the first episode and prints their line numbers.

## Confidentiality and quality checks

Kuku permits using the screenplays with AI tools for this assignment. Keep the input pack out of shared repositories, public demos, and submission folders. Use an original example when a public walkthrough needs sample input.

For promo recommendations, check each segment’s episode, start time, and end time against its screenplay. Add the segment durations in playback order and verify that each promo totals 20–60 seconds. Read the selected material on its own to check whether the hook lands within three seconds and the ending leaves a question unresolved.

## Adding a prototype

This workspace currently contains assignment materials only. When adding the first prototype, document its entry point, dependencies, and exact run and verification commands. Include a shareable sample input so another contributor can reproduce a run.
