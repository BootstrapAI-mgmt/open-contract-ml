# CITE — resolving the dangling citation anchors

Branch `fix/dangling-citations`, worktree `C:/wt/open-contract-ml`.

> **Note on notation.** The retired anchor namespace used a one-letter prefix
> that the verification gate now forbids anywhere in the repository's markdown.
> This report therefore writes the retired keys *without that prefix* — `cae-05`
> for what was formerly the `cae-05` anchor in that namespace — so that the
> report does not itself re-introduce the token it is reporting the removal of.

---

## Gate verdict

**Flipped.** Zero anchors remain in shipped content.

```
$ git ls-files '*.md' | xargs grep -nE "Q-[a-zA-Z0-9-]+"
$ echo "exit=$?"
exit=123          # xargs reporting grep's "no matches"
```

The un-published ledger is still absent from the tree. Its filename is elided as
`<ledger>` below — writing it out inside a tracked file is *itself* a test
failure, which is one of the traps documented further down.

```
$ git ls-files | grep -i <ledger> || echo "absent from tracked tree: OK"
absent from tracked tree: OK
$ ls <ledger>
ls: cannot access '<ledger>': No such file or directory
```

Full suite, before and after:

```
before (baseline, scratch dir excluded):   222 passed in 12.14s
after:                                     225 passed in 13.52s
```

The +3 are the new link-integrity tests. No existing test was modified,
relaxed, or skipped.

---

## The measured inventory

The brief said thirteen files; that is correct, and the count of keys was not.

| Quantity | Measured |
|---|---|
| Files carrying anchors | **13** |
| Total occurrences | **36** |
| Distinct anchor keys | **15** |
| Bare-namespace prose mentions (not a key) | **1** |

**Trap for anyone re-measuring.** The brief's regex is the correct one. A
narrower and more natural-looking pattern — prefix, alphanumerics, hyphen,
digit — returns only **8** of the 13 files, because the alphanumeric class
cannot cross the *second* hyphen in a three-segment key such as `ml-tab-02`.
I made exactly this mistake on my first pass and briefly believed the brief
had over-counted. Measure with the brief's pattern.

### Key → source

Every key resolved to a source that, in most call sites, **already had a
bracket citation sitting immediately next to it** — `[Bathe2014] / cae-05`.
So the dominant edit was deletion of a redundant dangling half, not a rewrite.

| Retired key | Resolves to |
|---|---|
| cae-03 | [Slotnick2014] |
| cae-05 | [Bathe2014] |
| cae-07 | [Paris1963] |
| cae-08 | [Miner1945] |
| ml-cnn-02, ml-cnn-02b | [Ronneberger2015] |
| ml-op-01 | [Kovachki2023] |
| ml-pinn-02 | [Karniadakis2021] |
| ml-rom-02 | [Lee2020] |
| ml-tab-01 | [Goodfellow2016] |
| ml-tab-02, ml-tab-02b | [Chen2016] |
| ml-tab-03 | [Ke2017] |
| ml-tab-04 | [Rasmussen2006] |
| surr-04 | [McElfresh2023] |

The mapping was built by reading **only** the bibliographic metadata lines of
the upstream ledger — the attribution line and the ISBN/DOI/URL lines. No line
beginning with a blockquote marker was ever copied out of it.

---

## A live R5 breach, found in passing

`examples/worked-cells/TASK-9-HT-worked-instance/WALKTHROUGH.md` shipped a
**four-line verbatim quotation** of the McElfresh2023 abstract — in quote
marks, with page attribution. That is the same defect class that got six
documents withdrawn, sitting in a document that was *not* withdrawn.

`test_no_verbatim_third_party_text` did not catch it because that test encodes
five specific excerpt fragments — Bathe, the NASA study, Jin2001, Kaw2012, and
a ReLU paper — and McElfresh2023 was not among them. **The test is a list of
known offenders, not a detector of the category.** Anyone who reads a green run
of that test as "this repository contains no verbatim third-party text" is
reading it wrong; it means "none of the five known passages is present."

The passage is now a short paraphrase in the document's own voice, citing the
source by reference. The surrounding caveat — classification-only, 176 datasets,
transfers by analogy — was already the document's own text and is unchanged.

---

## What changed

**The 13 documents.** Anchors removed. In 30 of 36 occurrences the adjacent
bracket citation already named the source, so the anchor was deleted outright.
Six occurrences needed the bracket key substituted in because the anchor was
carrying the citation alone (the fatigue model card's scatter-range references,
and the drag-from-shape CNN anchor). Two occurrences were prose *about* the
ledger rather than citations into it — the problem-spec's description of what
the verdict sheet carries, and `docs/EXTRACTION.md`'s historical note on a
withdrawn file — and were reworded to drop the key without losing the meaning.
No engineering content was rewritten.

**`docs/REFERENCES.md`** (new). 29 entries. The short-key scheme is
`[FirstAuthorYear]` — chosen because the documents were *already* using it in
26 distinct keys; inventing a third namespace alongside a working one would
have been strictly worse. Records were verified against the upstream project
bibliography rather than written from memory, including the three keys that
appear unbracketed in the model cards ([Li2021], [Chen2018], [Battaglia2018]).

**Eleven documents** gained a one-line pointer to the bibliography. The two
that carry no bracket citations did not need one.

**`tests/test_link_integrity.py`** (new). See below.

**`PROVENANCE.yaml`** — see "files I do not own", below. I touched it.

---

## The new gate, and what it found

`test_no_markdown_link_points_outside_the_shipped_tree` asserts no markdown
link resolves to a path the repository does not ship. Three design points worth
keeping:

1. It checks the **tracked set**, not the filesystem. A target that exists in a
   working tree but was never committed is unreachable by anyone who clones;
   `Path.exists()` would pass and be wrong.
2. Fenced code blocks are stripped. A path inside a code sample is illustrative.
3. `KNOWN_DANGLING` is a **ratchet, not an amnesty**. A companion test,
   `test_no_known_dangling_entry_has_been_fixed`, fails if a listed link starts
   resolving — so the list is forced to shrink and cannot quietly absorb new
   breakage.

**It immediately found 10 pre-existing dangling links** (7 distinct
file→target pairs) in two documents outside this change. This is the same
defect the brief sent me to fix, in a different costume, and it was already
in the repository.

### Red/green proof

Planted a dangling pointer in `docs/REFERENCES.md`:

```
E       AssertionError: 1 markdown link(s) resolve to a path this repository does not ship:
E           docs/REFERENCES.md:69: [..](appendix-that-does-not-exist.md) -> docs/appendix-that-does-not-exist.md
E
E         Point the link at something the repository actually contains, or drop it. A citation
E         belongs in docs/REFERENCES.md, not in a pointer to a file only the author can see.
FAILED tests/test_link_integrity.py::test_no_markdown_link_points_outside_the_shipped_tree
1 failed in 0.34s
```

Removed it:

```
3 passed in 0.08s
```

---

## Blocked — needs a file I do not own

**1. `docs/model-onboarding.md` and `docs/model-packages.md` — 10 dangling links.**
Two of the targets **do ship**, at paths that moved during extraction. These are
mechanical fixes and worth doing:

| File | Current link | Correct target |
|---|---|---|
| `docs/model-onboarding.md`, `docs/model-packages.md` | `../schemas/manifest.schema.json` | `../src/opencontractml/schemas/contract-v1/manifest.schema.json` |
| `docs/model-onboarding.md`, `docs/model-packages.md` | `../templates/model_card.template.md` | `../src/opencontractml/templates/model_card.template.md` |

The other three have no target in this repository and the link should be dropped
or the prose reworded: `gui-design.md` (never written), `../ROADMAP.md` (not
extracted; also a file this wave must not create), and
`../.github/workflows/validate-model-package.yml` (not extracted).

After any of these is fixed, **delete the matching `KNOWN_DANGLING` entry in
`tests/test_link_integrity.py`** — the companion test will fail until you do.
That is deliberate.

**2. `README.md` — docs index is now incomplete.** Lines 87–90 list the shipped
documents. Add:

```
docs/REFERENCES.md                  the bibliography every [Key] citation resolves to
```

**3. `examples/falsifier-benchmark/falsifier_benchmark.py` — 15 dangling anchors.**
The brief's gate greps markdown only. The same anchors are embedded in shipped
**Python** source, in strings printed to the user as part of the benchmark's
verdict output: 15 distinct keys from the `surr` family, on 15 lines. A reader
of that output gets the identical unresolvable pointer. The gate as specified
passes while this remains. Cheapest correct fix is the same as the markdown
one — drop the anchor, keep the bracket citation.

---

## Staleness sweep

- **Test-count claims:** none in any tracked document. Checked; nothing to fix.
- **`README.md`:** now incomplete — Blocked item 2.
- **`docs/EXTRACTION.md`:** re-checked. Its account of which files were withdrawn
  and why is still accurate; only the anchor token in one table cell changed.
- **`EXTRACTION-MANIFEST.md`:** not present in this repository. The stale count
  the brief warns about is in the upstream repo, out of scope here.
- **Version pins / badges / CHANGELOG:** none present that this change affects.
- **`PROVENANCE.yaml`:** brought current — below.

---

## Context not captured anywhere else

**The scratch directory cannot be committed, and the wave protocol says to
commit it.** `tests/test_provenance.py` carries `.agent-scratch` on its
never-copy list with the reason *"agent working files never travel"*. Committing
it fails two tests outright. The protocol's `git add -A` instruction is generic
across the wave; this repository has a specific, deliberate guard against
exactly that, and the anti-scope rule forbids weakening the falsifier to make
anything pass. I resolved it in favour of the repository's own gate: the scratch
directory is excluded locally via `.git/info/exclude` (**not** a committed
`.gitignore` entry, which the protocol also forbids), everything of value from
it is in this report, and my working inventory file was deleted so that even a
raw recursive grep over the tree is clean. **Any future agent in this repo hits
this same contradiction.**

**The digest pins make editing extracted files a two-part job.** Twelve of the
13 documents are `extracted` records pinning both `source_sha256` and a local
`sha256`, and `docs/EXTRACTION.md` is an `authored` record pinning `sha256`.
Editing any of them fails `test_recorded_digests_match_the_committed_content`
until the pin is rewritten. There is **no regeneration tool** in the repo — I
looked. The digest is of the **staged blob** (`git cat-file blob :<path>`), not
the working-tree bytes; a recent commit exists specifically to fix that
confusion, and computing it from the file on disk produces pins that pass
locally and fail in a fresh clone.

**`transformed:` is documentation, not a gate.** No test reads it. I set it to
`true` on the 12 edited records because it is now factually true, but nothing
would have caught leaving it false. Three records were already `true`, which is
why only 9 flips were needed for 12 records — worth knowing before someone reads
a mismatched count as a bug.

**Writing about this defect is constrained in a non-obvious way.** The verbatim
test fails **any** tracked file containing the un-published ledger's filename,
case-insensitively and whitespace-collapsed, with only three files exempt. A
report or reference file that names that file directly turns the suite red. This
report and `docs/REFERENCES.md` are both written around that constraint. It is
easy to trip and the failure message does not obviously point at the cause.

**The surrogate-selector tool does not ship here.** `examples/problem-spec/`
contains only the contract document and a template; the engine it describes is
not in this repository. That is pre-existing and out of scope, but it means the
problem-spec's "what the tool returns" section describes software a reader
cannot run. Worth a decision before publication.

**What I did not do:** I did not verify that heading fragments (`file.md#section`)
resolve to real headings — only that the file part exists. Slug-generation rules
vary between renderers and a naive implementation produces false failures. It is
a genuine remaining gap.

---

## Follow-ups

1. **Fix the 10 dangling links** in `docs/model-onboarding.md` /
   `docs/model-packages.md` using the table above, and prune `KNOWN_DANGLING`.
2. **Strip the 15 anchors from `falsifier_benchmark.py`** and widen the
   publication gate beyond `--include=*.md`.
3. **Add `docs/REFERENCES.md` to the README index.**
4. **Decide whether `test_no_verbatim_third_party_text` should grow** from a
   five-item known-offender list into something category-shaped. The McElfresh
   passage proves the current design misses new instances. At minimum, add that
   passage's fragment so it cannot return.
5. **Fragment-level link checking** — verify `#section` anchors resolve.
6. **Decide on the problem-spec's absent engine** before the repo goes public.
