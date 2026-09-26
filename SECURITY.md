# Security policy

## Reporting a vulnerability

Please do not describe a vulnerability in a public issue, pull request or
discussion.

Report it through GitHub's private vulnerability reporting ("Report a
vulnerability" on this repository's Security tab) when that is available. When
it is not, open an issue titled "Security contact request" that contains no
details, and the maintainer will arrange a private channel.

A useful report names the affected version or commit, the steps that reproduce
the problem, and what an attacker gains. Reports are acknowledged, and answered
with a fix or with the reason the behaviour is not treated as a vulnerability.

## Supported versions

Fixes are made on `main` and ship in the next release. Only the latest release
is supported.

## The safe-artifact policy

Reading a model artifact can run code: a pickle stream, and therefore
`torch.load` on an untrusted `.pt` file, may name a function to call while it is
being read. This package reads serialized artifacts only through
`opencontractml.safe_artifact` and `opencontractml.safeload`, and never
deserializes an unknown pickle without restriction. `safe_artifact` unpickles a
model bundle through a closed allow-list of globals, so a stream that names
`os.system` or `eval` is refused before anything in it runs. `safeload` reads
`.safetensors` natively, `.npz` with `allow_pickle=False`, and `.pt`, `.pth` and
`.ckpt` only with `torch.load(weights_only=True)`, and refuses every other
format. The one exception is a caller that names the exact sha256 of a file it
has verified: that load is unrestricted, announces itself on stderr and through
the warnings module, and fails closed if the file's bytes no longer match. No
flag or environment variable opens it. A way to run code through either module
without such a pin is a vulnerability; please report it as described above.
