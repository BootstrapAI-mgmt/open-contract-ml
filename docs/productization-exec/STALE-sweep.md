# STALE — staleness sweep (open-contract-ml)

**Agent:** STALE · **Branch:** `prod/staleness-sweep` · **Date:** 2026-09-16

Full cross-repo report: **`cfd-automation:docs/productization-exec/STALE-sweep.md`**.

## Gate verdict

**PASS.** This repo has no `OPEN-CLOSED-MAP.yaml` and no `scripts/` — it *is* the
extracted open core, so there is no map checker to satisfy here. The standing
gate is the suite:

```
$ python -m pytest tests -q --tb=short -o addopts=""
222 passed in 12.46s
```

## What changed

One document. This repo is brand new, so "staleness" here can only mean a claim
that was wrong on arrival — and there was exactly one.

`docs/EXTRACTION.md:169` said:

> `grep -ri spine` over this tree returns hits in **exactly two files**, and both
> are deliberate: `PROVENANCE.yaml` … and this document …

It returns **three**:

```
$ git grep -il spine -- .
PROVENANCE.yaml
docs/EXTRACTION.md
tests/test_provenance.py
```

The third is the detector itself. **The code already knew this and the doc did
not** — `tests/test_provenance.py:316`:

```python
#: The files allowed to say "spine".
#: … This file is the detector, and a detector unavoidably contains the string
#: it looks for; the cost is that a genuine leak *inside this file* would not be
#: caught, which is an acceptable blind spot …
SHORTHAND_EXEMPT = {"PROVENANCE.yaml", "docs/EXTRACTION.md", "tests/test_provenance.py"}
```

So the doc undercounted its own exemption set by one. I corrected the count to
three, named the third file and its reason, and pointed the paragraph at
`SHORTHAND_EXEMPT` so the two can no longer drift apart silently.

**Code was right, doc was wrong → a doc fix.** Had it been the other way round
this would have been a bug report instead, per my brief.

## Evidence

```
$ git grep -il spine -- . | wc -l
3
$ python -m pytest tests -q -o addopts=""
222 passed in 12.46s          # incl. test_internal_shorthand_does_not_leak_into_published_content
```

The rename gate still passes after the edit — unsurprising, since
`docs/EXTRACTION.md` is itself exempt, but worth confirming rather than assuming.

## Staleness sweep — checked, not changed

- References to `CAE-ML-data-pipelines` in `docs/model-onboarding.md`,
  `docs/spec/ADOPTION.md`, `docs/spec/CONTRACT-v1.md` and
  `examples/reference-package/model_card.md` are **correct** — dp is genuinely
  the spec authority (owner decision D10) and the upstream provenance. Not stale.
- `LICENSE` is Apache-2.0 and `README.md` agrees. No licence drift.
- `PROVENANCE.yaml` deliberately retains upstream `spine` paths; renaming them
  would falsify the provenance record. Untouched, and correctly so.

## Blocked — needs a file I do not own

Nothing.

## Follow-ups

1. The repo is private and must stay private for now (explicit anti-scope). No
   action taken or implied here.
2. If `SHORTHAND_EXEMPT` ever gains a fourth member, `docs/EXTRACTION.md` must
   move with it. The paragraph now names the set by identifier, which makes that
   coupling visible, but nothing enforces it — a test asserting the doc's stated
   count matches `len(SHORTHAND_EXEMPT)` would close the loop.
