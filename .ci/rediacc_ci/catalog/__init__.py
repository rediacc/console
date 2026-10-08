"""The Rediaccfile template catalog under `packages/json/`: the generator that builds `dist/` and the lifecycle suite that runs each template's `up()` and `down()`.

Ported from `packages/json/generate.sh` and `packages/json/test-templates.sh` (PLAN-retire-bash-oracles B5, W10). The `@rediacc/json` package scripts invoke `generate.py` and `lifecycle.py` by path.
"""
