"""The Contract v1 — a conformance standard for engineering-ML model packages.

A *contract package* is a directory holding a manifest, a model card, a
validation report and the artifacts they name. The Contract says what must be
in it, and :mod:`opencontractml.verify` decides whether a given directory
complies::

    python -m opencontractml.verify check <package-dir>

The normative text is ``docs/spec/CONTRACT-v1.md``; the machine-readable
structure is ``opencontractml/schemas/contract-v1/``. A worked conformant
instance is ``examples/reference-package/``.

Import layout
-------------

Only :mod:`~opencontractml.verify` is imported here, and it is deliberately
standard-library-only, so ``import opencontractml`` costs nothing and works on
a bare interpreter. Everything with a dependency is imported explicitly:

===============================  ==============================================
module                           needs
===============================  ==============================================
``opencontractml.verify``        nothing (PyYAML read opportunistically)
``opencontractml.manifest``      pyyaml, jsonschema, pydantic
``opencontractml.model_card``    pyyaml
``opencontractml.safe_artifact`` nothing
``opencontractml.gate``          ``[gate]``: numpy, pandas, scikit-learn
``opencontractml.corpus_gate``   ``[gate]``
``opencontractml.safeload``      ``[tensors]``: torch, safetensors
===============================  ==============================================
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

#: This distribution's own version. Distinct from :data:`CONTRACT_VERSION`,
#: which is the version of the *specification* this release implements.
__version__ = "0.1.0"

__all__ = ["verify", "CONTRACT_VERSION", "SUPPORTED_CONTRACT_MAJOR", "__version__"]

_LAZY = {"CONTRACT_VERSION", "SUPPORTED_CONTRACT_MAJOR"}


def __getattr__(name: str) -> Any:
    """Resolve the checker's names on first use (PEP 562).

    Importing ``.verify`` eagerly here would put it in ``sys.modules`` before
    ``runpy`` got to it, so the documented ``python -m opencontractml.verify``
    would warn on every single invocation. Deferring the import also keeps
    ``import opencontractml`` genuinely free of side effects.
    """
    if name != "verify" and name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    # `from . import verify` would route back through this __getattr__ via
    # _handle_fromlist and recurse until the stack blew. import_module resolves
    # the submodule directly.
    mod = importlib.import_module(f"{__name__}.verify")
    value = mod if name == "verify" else getattr(mod, name)
    setattr(sys.modules[__name__], name, value)  # resolve once, then it is a plain attribute
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
