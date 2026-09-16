# Forwarders for two live modules the oracles reach as siblings

Two of the retired guards resolve a module through their own directory's PARENT:

    pre-edit/block-plan-without-tasks.sh:90   .../../stop/wl_planfid.py
    pre-ask/block-settled-questions.sh:133    .../../stop/worklist.py

Both were moved here unchanged at the W5 P7 cutover and both say why they resolve
that way rather than through `CLAUDE_PROJECT_DIR`. Neither module moved:
`.claude/hooks/stop/` is the live worklist machinery, and duplicating any of it
here would be a second copy of a 48-file package that drifts.

So each file in this directory is a FORWARDER that executes the live module in
place, exactly as `../lib/sanctioned.py` and `../pre-bash/lib/command-scan.sh`
do. That keeps all 46 oracles byte-identical to the guards they were, which is
what makes `tests/test_guards_differential.py` a comparison against the real file
rather than against a transcription of it.

WHY NOT A SYMLINK TO `../hooks/stop`. A directory symlink is one git entry but it
is traversable, so any gate globbing `.claude/**/*.py` would find all 48 modules
a second time and report each one twice. Two named forwarders say exactly what is
borrowed and nothing else appears.
