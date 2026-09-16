"""Tests for the `.claude` hook package.

They are a package (rather than loose files) so pytest's default `prepend`
import mode walks up past `tests/` and `rediacc_hooks/` and puts `.claude` on
`sys.path` on its own -- which is what makes `import rediacc_hooks.shellscan`
work here without a `conftest.py` doing a hand-written path hop.
"""
