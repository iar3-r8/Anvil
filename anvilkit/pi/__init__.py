"""The Pi integration: bake-off, approval, sandbox, ruleset guard and
single-role modules.

A plain package - a docstring only, no imports, no re-exports. Submodules
are imported by their full dotted path (``anvilkit.pi.piguard``, imported
``from anvilkit.pi import piguard``), so ``import anvilkit.pi`` pulls in
none of them: importing ``piguard`` must not drag in the ``subprocess``,
``urllib`` and ``threading`` usage of its eleven siblings.
"""
