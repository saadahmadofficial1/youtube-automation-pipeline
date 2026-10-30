# YouTube Automation Pipeline

A checkpointed Python orchestration demo for multilingual video planning, scene provenance and Shorts quality checks. Built with Claude Code.

## What it does

Creates a job manifest, plans Spanish/French/German variants, tracks scene revisions, resumes completed stages and writes a local review dashboard. Caption rules check safe placement, timing, contrast and sentence boundaries.

## Stack

Python 3.10+ standard library, JSON manifests and automation. Designed for workflows that can connect LLM APIs, narration and FFmpeg rendering; this public edition uses synthetic fixtures and makes no LLM API calls.

## Try it

```sh
python3 -m unittest discover -s tests -v
python3 -m src.cli new "How Roman roads shaped Europe"
python3 -m src.cli run JOB_ID --smoke
python3 -m src.cli upload JOB_ID
```

Use the ID printed by `new`. `run --smoke` generates synthetic plans, not rendered video or verified research. The review HTML contains text cards, not actual frame captures. The `upload` command returns a local simulation receipt and never contacts an account. Production runs are disabled in this edition.

## Design

Research → master plan → localisations → Shorts → quality checks → upload plan. Scene repair invalidates downstream stages. Human editorial review is still needed: passing synthetic checks does not establish factual accuracy, media rights or video quality.

## Public edition

Account integrations, scheduled account jobs, production narration/render scripts, private config, logs, review output, vendor code and model weights are excluded. No existing screenshots or demo media have been cleared for reuse.
