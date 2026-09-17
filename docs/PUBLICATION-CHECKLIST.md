# Publication checklist

> **Owner resolution, 2026-09-16 (decision D24, recorded in cfd-automation:docs/productization-audit/SHEPHERDING-HANDOFF.md §5):** no institutional intellectual property attaches to anything in these repositories; the university-address commits upstream were an accident of git configuration. The institutional-IP item below is therefore CLEARED for D21; it stays in this checklist as the record of what was measured.


Preparation for owner decision **D21** — making this repository public. Every
item is owner-run. Nothing here publishes anything, and no agent should: the
visibility flip, the PyPI upload and the release tag are owner acts.

`docs/EXTRACTION.md` opens with the reason this file is a checklist rather than
a judgement call:

> Publishing is irreversible. [...] a file wrongly left out can be added next
> week, and a file wrongly published cannot be unpublished.

**Every result below was measured on 2026-09-16 and every one must be re-run
before the flip.** A measurement in a document is a claim about the past. The
commands are given so that re-running is cheaper than trusting.

---

## 0. Status summary

| | Item | State on 2026-09-16 |
|---|---|---|
| **1** | Institutional-IP determination | **BLOCKING — unresolved, and larger than expected** |
| 2 | Third-party verbatim text, both scans | clear |
| 3 | Provenance falsifier | green |
| 4 | Secrets | none |
| 5 | Build, install, run from the wheel | green |
| 6 | PyPI name available | yes |
| 7 | Licence and notice state | consistent |
| 8 | Version and tag plan | decided, not executed |
| 9 | The flip | owner |

Item 1 is the only one that is not mechanical, and it is the one that matters.

---

## 1. Institutional IP — BLOCKING

> **This correction is the most important thing in this document.** The brief
> that produced this checklist stated the institutional-IP flag concerned
> university-address commits in `physics-surrogates` and `diffsim-jax`, "**NOT
> this repo**", and asked for it to be listed as an owner item gating the
> programme's public step rather than this repository's.
>
> That is measurably wrong, and in the direction that matters. **84 of this
> repository's 87 extracted files have at least one commit authored from a
> university address in their upstream history, and 80 have nothing else.**

This repository's own commit history is clean — every commit here is
`noreply@anthropic.com`. But this repository is an *extraction*: its content was
copied out of named commits of sibling repositories, and it is the authorship of
*those* commits that carries whatever institutional claim exists.

```console
$ # authors of every commit touching an extracted source path, at the recorded ref
    117  jcoleman@captechu.edu
      3  bsaipersonal@gmail.com
      3  claude-cowork@anthropic.com
      2  jpcoleman12@gmail.com

$ # per extracted file
extracted files total             : 87
  every commit university-authored: 80
  mixed authorship                :  4
  no university commit at all     :  3
```

The three files with no university-authored commit are the `physics-surrogates`
contribution (`safeload.py`) and two others. `NOTICE` already attributes
`safeload.py`'s MIT copyright to an individual, not to an institution.

**What this is not.** A commit email address is not a determination of
ownership. Whether Capitol Technology University has any claim over this work
depends on enrolment or employment agreements and on the university's IP policy,
not on what was configured in `git config user.email` at the time. It is
entirely possible the answer is "no claim whatsoever."

**What it is.** An unanswered question attached to ~97% of the content of a
repository that is about to be made irreversibly public under Apache-2.0, where
the owner grants a patent and copyright licence to the world on that content.

**Required before the flip:** an owner determination, and — if there is any doubt
— counsel. Record the outcome here with a date. Do not proceed on the basis that
this repository's own `git log` is clean; it is clean because the extraction
deliberately did not carry history, which is exactly why the question has to be
asked upstream instead.

To re-measure:

```console
$ python - <<'PY'
import yaml, subprocess, collections
d = yaml.safe_load(open("PROVENANCE.yaml", encoding="utf-8"))
CLONES = {"CAE-ML-data-pipelines": "C:/wt/x-dp", "cae-ml-gui": "C:/wt/x-gui",
          "physics-surrogates": "C:/wt/x-ps"}
c = collections.Counter()
for r in d["extracted"]:
    o = subprocess.run(["git","-C",CLONES[r["source_repo"]],"log","--format=%ae",
                        r["source_ref_sha"],"--",r["source_path"]],
                       capture_output=True, text=True)
    c.update(a for a in o.stdout.split() if a)
for k,v in c.most_common(): print(f"{v:5d}  {k}")
PY
```

The three source worktrees must be on disk for this to resolve. If they are not,
the loop reports nothing and **that is not a clear result** — it is an
unverifiable one.

---

## 2. Third-party verbatim text — two independent scans

`docs/EXTRACTION.md` records why one scan is not enough: the never-copy list is
*path-based*, and D18 opened worked cells whose prose had **transcribed excerpts
inlined into it**. A path exclusion cannot see that. Both scans must be run and
both must be clean.

**Scan 1 — structural.** The never-copy list applied to the tracked tree *and*
to every recorded `source_path`, so a forbidden file renamed on the way in fails
too.

```console
$ python -m pytest "tests/test_provenance.py::test_forbidden_content_is_absent_from_the_tree" \
                   "tests/test_provenance.py::test_forbidden_content_is_absent_from_every_recorded_source" -q
42 passed in 0.29s
```

**Scan 2 — content-based.** Whitespace-insensitive fragments of the excerpts
that were found in and removed from the extraction set, so a copy that is
reflowed, un-indented or pasted inline still fails.

```console
$ python -m pytest "tests/test_provenance.py::test_no_verbatim_third_party_text" -q
1 passed in 0.29s
```

> **Read scan 2 correctly.** It encodes a fixed list of known passages. A green
> run means *none of those specific passages is present*; it does not mean the
> repository contains no third-party text. The session that added
> `docs/REFERENCES.md` found a live verbatim quotation that this test did not
> catch, because the passage was not on its list. Treat it as a regression guard,
> not as a detector.

**Also verify no pointer into the unpublished ledger survives**, in any file
type — not only markdown, which is the mistake that let 36 references through
once already:

```console
$ python -m pytest tests/test_link_integrity.py -q
5 passed
```

---

## 3. Provenance falsifier

Every file traced, nothing dropped silently, nothing forbidden present.

```console
$ python -m pytest tests/test_provenance.py -q
```

Note that `test_recorded_source_digests_are_real_blobs` **skips** when the source
worktrees are absent, and says so loudly. A run that skips it has not verified
the recorded source digests. Before the flip, run it with the sources on disk.

Full suite:

```console
$ python -m pytest -q
227 passed in 15.72s
```

---

## 4. Secrets

```console
$ git grep -nE 'ghp_|AKIA|sk-[A-Za-z0-9]|BEGIN (RSA|OPENSSH)'
$ echo $?
1        # no matches
```

This pattern set is narrow. It catches GitHub PATs, AWS access-key IDs, common
API-key prefixes and private-key headers. It does not catch a password in prose,
a bearer token with no recognisable prefix, or a credential in a `.csv`. A
dedicated scanner over the full tree is worth one run before the flip.

---

## 5. Build, install and run from the artifact

The point of this step is to test the **wheel**, not the source tree. A source
tree that works proves nothing about what a user gets.

```console
$ python -m build
Successfully built open_contract_ml-0.1.0.tar.gz and open_contract_ml-0.1.0-py3-none-any.whl

$ python -m venv /tmp/clean && /tmp/clean/Scripts/python -m pip install dist/*.whl
$ /tmp/clean/Scripts/python -c "import opencontractml.verify as v; print(v.__file__)"
...\clean\Lib\site-packages\opencontractml\verify.py

$ /tmp/clean/Scripts/python -m opencontractml.verify check examples/reference-package
OK   examples\reference-package  (contract 1.0, 0 warning(s))

$ /tmp/clean/Scripts/open-contract-ml check examples/reference-package
OK   examples\reference-package  (contract 1.0, 0 warning(s))
```

Both the module entry point and the console script were exercised. The schema
and card template resolve from inside the wheel through `importlib.resources`,
with no source tree present:

```console
...\clean\Lib\site-packages\opencontractml\schemas\contract-v1\manifest.schema.json
$id : https://github.com/BootstrapAI-mgmt/open-contract-ml/schemas/contract-v1/manifest.schema.json
```

> **Trap, and it is easy to fall into.** A user-level editable install of this
> package exists on the development machine and puts a *different worktree* on
> `sys.path`:
>
> ```console
> $ python -c "import opencontractml.verify as v; print(v.__file__)"
> C:\wt\open-contract-ml\src\opencontractml\verify.py     # not the tree you are in
> ```
>
> Every `pytest` run and every `python -m opencontractml.verify` invocation in a
> worktree silently exercises whatever that `.pth` points at. Print `__file__`
> before believing any before/after result, or use the clean venv above. This is
> the single most likely way to produce a green run that means nothing.

---

## 6. PyPI name

```console
$ python -m pip index versions open-contract-ml
ERROR: No matching distribution found for open-contract-ml

$ curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/open-contract-ml/json
404
$ curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/opencontractml/json
404
```

Both the distribution name and the import name are unclaimed. Names are
first-come; re-check immediately before upload.

Uploading is an owner act and is **not** required by D21 — the visibility flip
and a PyPI release are separate decisions and can be taken separately. If PyPI
is wanted, claim the name with a `0.1.0` release only after item 1 is resolved,
because `pip` releases cannot be meaningfully unpublished either.

---

## 7. Licence and notice state

| File | State |
|---|---|
| `LICENSE` | Apache-2.0, 202 lines, verbatim from apache.org; digest recorded in `PROVENANCE.yaml` |
| `NOTICE` | Apache-style notice, plus the MIT notice for `safeload.py` reproduced in full and an explanation of why MIT's terms are satisfied, plus a provenance paragraph |
| `pyproject.toml` | `license = "Apache-2.0"`, `license-files = ["LICENSE", "NOTICE"]` — both travel in the wheel |
| `README.md` | states Apache-2.0 and points at `NOTICE` for the MIT component |

Consistent. Two things to confirm by eye before the flip:

- **`NOTICE` attributes `safeload.py`'s MIT copyright to an individual.** That is
  correct for MIT, and it interacts with item 1 — see that the attribution the
  owner wants is the attribution that is there.
- **No licence field for the *model*.** The manifest has no licence key for a
  model, its weights or its training corpus. That is a gap in the Contract, not
  in this repository's licensing, and it is a v1.1 candidate. It does not block.

---

## 8. Version and tag plan

Consistent across all three places it appears:

```console
$ grep '^version' pyproject.toml          -> version = "0.1.0"
$ python -c "import opencontractml as o; print(o.__version__)"   -> 0.1.0
$ <clean venv> importlib.metadata.version("open-contract-ml")    -> 0.1.0
$ git tag -l                              -> (empty)
```

Plan: tag **`v0.1.0`** at the commit that is made public, after item 1 clears.
`Development Status :: 3 - Alpha` in `pyproject.toml` is the right classifier
for a contract whose v1.0 has four stated known limitations and has never been
run against a production model — see `docs/STANDARDS-ALIGNMENT.md` §6.4.

Do not tag before the flip. A tag on a private repository that is then made
public is fine; a tag pushed to the wrong remote is not.

---

## 9. The flip itself — owner

1. Resolve item 1 and record the determination and its date in this file.
2. Re-run items 2–6. Do not reuse the measurements above.
3. Read `docs/EXTRACTION.md` "Known gaps in what *is* here" once more and decide
   whether each is acceptable in public. Gap 1 in particular — nine walkthroughs
   instruct the reader to run software that is not in this repository — is a
   documentation defect a first-time reader will hit immediately.
4. Flip visibility.
5. Tag `v0.1.0`.
6. Decide separately about PyPI.

---

## What this checklist does not cover

- **Whether the Contract is any good.** That is
  `docs/STANDARDS-ALIGNMENT.md`'s subject, and its answer is qualified.
- **Trademark.** No search was done on "open-contract-ml" or "The Contract" as
  a name.
- **Export control.** Not assessed.
- **The other repositories.** This checklist is about this repository only.
  `physics-surrogates` and `diffsim-jax` have their own institutional-IP
  exposure, which is what the brief originally pointed at and which remains
  true — it is simply not the *whole* of the exposure.
- **Whether anyone wants it.** Not a checklist item.
