# PLAN: backup usage meters every chunk the store holds: chunks a killed run uploaded and a later commit references are billed at commit, not only at the next nightly run; crash debris is billed until GC deletes it; a reconcile verb repairs and checks the ledger against the store (moved)
Status: moved
Moved-To: agent/plans/_done/PLAN-backup-meter-orphaned-chunks.md

This plan moved to `agent/plans/_done/PLAN-backup-meter-orphaned-chunks.md`. The stub keeps every citation of the old path resolving; a plan moves exactly once, at close. See agent/README.md for the layout.
