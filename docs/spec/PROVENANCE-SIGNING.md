# OMS-compatible provenance signing

**Status: design only.** Nothing here is implemented, no dependency is proposed,
and no code in this repository signs or verifies anything. This document exists
so that when signing is implemented it is implemented against a decided shape
rather than an improvised one.

[CONTRACT-v1.md](CONTRACT-v1.md) §10.4 records the gap this closes:

> **No signature or attestation.** `provenance` proves the bytes have not changed
> since packaging. It does not prove who packaged them. Signing is a v2 concern.

The conclusion below is that the *field* is a 1.1 concern and the *enforcement*
is a v2 concern. Reserving an optional, ignorable slot early costs nothing and
prevents two producers inventing two incompatible ones.

---

## 1. What the provenance block actually proves today

Less than it looks like, and the gap is measurable rather than theoretical.

`provenance.artifacts` pins **every file needed to execute the model** — for the
reference package, `./predict.py` and `./model_weights.json` — each by `sha256`
and `bytes`, and rule `M013` re-hashes them against the files on disk. That part
is strong: appending one line to the entrypoint turns the check red on both the
digest and the byte count.

The three files that carry the *claims*, however, are not pinned by anything:

| File | Hashed by the Contract? |
|---|---|
| the entrypoint and weights | **yes** (`M013`) |
| `manifest.yaml` | no |
| `model_card.md` | no |
| `validation_report.json` | no |

For the card and the report this is deliberate and correct: both are written
*after* the artifacts they describe, so hashing them into the manifest would be
circular. §6.3 of the spec says so, and binds them instead by the
`model_id` / `version` / `dataset_sha256` triple (`C002`, `V002`, `V003`).

But binding identity is not the same as binding content, and the consequence is
concrete. Both of the following were run against a copy of the reference package
and both returned exit 0:

```console
$ # inject a false certification claim into the model card
$ python -m opencontractml.verify check .
OK   .  (contract 1.0, 0 warning(s))

$ # multiply A1_accuracy's declared thresholds by 1000
$ python -m opencontractml.verify check .
OK   .  (contract 1.0, 0 warning(s))
```

So: the Contract guarantees the *model you run* is the model that was packaged.
It does not guarantee the *claims you read* are the claims that were made. Any
party who can hand you a directory can edit the card and the report freely, and
can rewrite `manifest.yaml` wholesale — including every declared digest — because
nothing signs the manifest either.

This is precisely the hole a detached signature fills, and it is worth being
exact about it: signing is not a nice-to-have hardening pass on top of a
tamper-proof package. The package is not tamper-proof. Signing is what makes the
declarations mean anything to a reader who does not trust the sender.

---

## 2. What OMS provides

The OpenSSF Model Signing specification (v1,
https://github.com/ossf/model-signing-spec) signs model artifacts — weights,
configuration, tokenizers, datasets — as a single verifiable unit:

- a **detached signature**, distributed inside the model folder;
- formatted as a **Sigstore Bundle**: a DSSE envelope wrapping an in-toto
  statement, together with the verification material;
- whose payload **manifest references every file by cryptographic hash**
  (SHA-256 or BLAKE2b), with optional annotations for domain-specific fields;
- **PKI-agnostic** — bare keys, PKI certificate chains, or keyless
  identity-based signing through Sigstore.

OMS states its own non-goals plainly: it does not address model quality,
fairness, ethical behaviour, or privacy. It answers *who vouches for these
bytes*, and nothing else.

That is an exact complement. The Contract answers *what was measured and against
what bar*; OMS answers *who says so*. Neither subsumes the other and the overlap
is one field.

---

## 3. The mapping

### 3.1 What stays

Everything. No part of the `provenance` block is replaced, and there is a
positive reason not to collapse the duplication.

`provenance.artifacts[].sha256` and the OMS payload's per-file digests would
cover the same two files with the same algorithm, which looks redundant. It is
not, because they fail differently and independently:

- `M013` works **offline, with no key material, no network, and no trust
  decision**. `opencontractml.verify` is standard-library-only precisely so it
  runs from a bare interpreter in any CI. It answers "are these the bytes the
  manifest describes?" — a question with a local answer.
- An OMS verification answers "did an identity I trust sign this set of bytes?"
  — which needs a key, a policy about which identities count, and usually a
  transparency-log lookup.

Collapsing the first into the second would make the Contract's integrity check
depend on a cryptographic stack and a trust policy, and would end the property
that a consumer with nothing installed can still check a package. The
duplication is the feature.

### 3.2 What is added

One optional field, and a file that is not a Contract artifact.

| Added | Where | Notes |
|---|---|---|
| `provenance.signature` | `manifest.yaml` | optional; `{format, path}` |
| the signature sidecar | the package directory, e.g. `./model.sig` | produced by OMS tooling, **not** listed in `provenance.artifacts` |

### 3.3 Coverage, and the one thing that must not be got wrong

The OMS payload should cover **every file in the package except the signature
itself**:

```
manifest.yaml           <- signed; this is the point
model_card.md           <- signed
validation_report.json  <- signed
predict.py              <- signed (and independently pinned by M013)
model_weights.json      <- signed (and independently pinned by M013)
model.sig               <- NOT covered; it is the signature
```

**The sidecar must not appear in `provenance.artifacts`.** If it did, the
manifest would carry the signature file's digest, while the signature covers the
manifest — a cycle with no fixed point, and `M013` would fail on every package
the moment it was signed. `provenance.signature.path` records a *path*, never a
digest, which is what keeps the reference acyclic.

Signing `manifest.yaml` is the substance of the proposal. It is the file that
declares every other digest, so a signature over it transitively protects the
whole package, and it is currently the least protected file in the directory.

---

## 4. Proposed field, contract 1.1

```yaml
provenance:
  artifacts: [...]                 # unchanged
  dataset: {...}                   # unchanged
  code: {...}                      # unchanged
  environment: {...}               # unchanged
  signature:                       # NEW, optional
    format: oms                    # the only value defined at 1.1
    path: ./model.sig              # relative to the package root
```

`format` is an enum with one member rather than a free string, so that a second
scheme has to be added deliberately. `path` is package-relative, like every
other path in the manifest.

### 4.1 No schema bump is required — verified, not assumed

`manifest.schema.json` does not set `additionalProperties` at the root or on
`provenance`, so it defaults to `true` and an additive key validates against the
**existing shipped schema**:

```console
baseline reference manifest      : VALID
with provenance.signature added  : VALID  <- no schema change required
removing provenance.dataset      : REJECTED -> 'dataset' is a required property
```

The third line is the negative control: the schema is not vacuously permissive,
it is permissive in the additive direction only. That is exactly the
compatibility rule §7 already states — "Unknown additive keys MUST be ignored,
not rejected" — so a 1.1 producer's manifest stays a valid 1.0 manifest.

Confirmed the same way at the checker level: a copy of the reference package
carrying `provenance.signature` passes the current 1.0 checker unchanged.

```console
$ python -m opencontractml.verify check <copy-with-signature>
OK   ...  (contract 1.0, 0 warning(s))
```

### 4.2 Checker behaviour

A new rule, `M017`, at **WARN** severity. It must never be an error, in either
direction:

| Condition | Verdict |
|---|---|
| field absent, `spec_version` 1.0 | silent |
| field absent, `spec_version` ≥ 1.1 | **WARN** — "package is unsigned" |
| field present, `format` unknown | WARN |
| field present, `path` missing from the package | WARN |
| field present, sidecar present | silent — *no signature verification* |

> **Deviation from the brief, deliberate.** The brief specified "checker warns
> when absent". Warning on absence *unconditionally* would emit a warning for
> every package that exists today, including `examples/reference-package/`,
> whose `OK ... (contract 1.0, 0 warning(s))` output is quoted in
> [README.md](../../README.md) and asserted in the suite. Gating the warning on
> `spec_version >= 1.1` gives the intended pressure — a producer who opts into
> 1.1 is told when they are unsigned — without retroactively making every
> conformant 1.0 package noisy. If the unconditional form is wanted instead, the
> README output and the tests that assert it have to change in the same commit.

The last row is the important one. **The checker does not verify signatures.**
It records that a package claims to have one and that the file is where the
claim says. Actual verification needs key material, a trust policy and probably
a transparency-log lookup, none of which belong in a standard-library-only
checker that has to run anywhere. A separate opt-in extra —
`open-contract-ml[signing]` — would carry that, and is out of scope here.

Reading `M017` as "this package is signed" would therefore be wrong, and the
rule text should say so in as many words.

---

## 5. Producing and verifying, end to end

Design sketch. No part of this is implemented.

**Produce** (after the package is otherwise complete and `verify` is clean):

1. build the package; ensure `M013` passes, so the declared digests are true;
2. add `provenance.signature: {format: oms, path: ./model.sig}` to the manifest;
3. run OMS tooling over the package directory, excluding `model.sig`, to produce
   the sidecar.

Step 2 precedes step 3, because the manifest must contain the field *before* it
is signed — otherwise the signed manifest differs from the shipped one and
verification fails on the file that matters most.

**Verify:**

1. `python -m opencontractml.verify check <pkg>` — structure, and `M013` against
   the on-disk artifacts. Offline, no keys.
2. OMS verification of `model.sig` against a trust policy — authenticity, and
   coverage of the manifest, card and report.

Step 1 without step 2 is today's guarantee. Step 2 without step 1 tells you an
identity vouched for some bytes and nothing about whether those bytes describe a
conformant model. The two are complementary and a consumer who cares should run
both.

---

## 6. What this deliberately does not do

- **No dependency.** Not in `dependencies`, not in an extra, not vendored.
- **No implementation.** No signing, no verification, no key handling.
- **No schema change.** Demonstrated above, not assumed.
- **No new required field.** A 1.1 package without a signature stays conformant.
- **No error-severity rule.** An unsigned package is not a non-conformant one.
- **No trust policy.** Which identities count is a deployment question and will
  differ per consumer.

---

## 7. Open questions for whoever implements this

1. **Is the package directory the right signing unit?** OMS signs a folder. A
   Contract package *is* a folder, so this fits — but packages are sometimes
   handed around as a tarball or a wheel, and the signature's relative paths
   must survive that.
2. **What covers the corpus?** `provenance.dataset.sha256` pins the training
   corpus, which is usually not in the package. OMS can sign datasets, but a
   dataset outside the signed folder is out of the sidecar's coverage. The
   digest is a claim about an absent file either way.
3. **Re-signing on re-packaging.** `provenance.code.commit` already lags by one
   commit for hand-built packages (§6, "Known wrinkle"). A signature adds a
   second thing that must be refreshed whenever the manifest is touched, and a
   stale signature fails loudly, which is better than the current silent lag but
   is a workflow cost.
4. **Should `format` allow more than `oms` at 1.1?** Adding a second value later
   is additive and cheap; adding one now with no implementation behind it is
   speculative. The recommendation is one value.
5. **Does the ecosystem's GUI consumer need to know?** `cae-ml-gui` reads the
   manifest. An unknown additive key must be ignored under §7, but "must" and
   "does" are different claims and it has not been tested against one.
