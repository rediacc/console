"""Python ports of `.ci/scripts/test/proxies/proxy-*.sh`, box W7P6.

Each module here is a twin of one bash proxy in that directory; the shared contract both sides implement (`proxy_init`/`need_*`/`preflight`/`pass`/ `fail`/`expect_*`/`finish`) is documented at `.ci/scripts/test/proxies/proxy-lib.sh` on the bash side and ported at `rediacc_ci.core.proxyx` on this one. See that module's docstring for why `proxy-lib.sh` itself has no twin of its own.
"""

__all__: list[str] = []
