"""The test tables of `block_cli_bundle`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

EDGE_CASES = [
    ("the bundle as the program", "node packages/cli/dist/cli.js"),
    ("a cli-bundle file as the program", "node cli-bundle.cjs"),
    ("flags before the program are skipped", "node --enable-source-maps cli-bundle.cjs"),
    # The three shapes the 2026-08-27 narrowing exists for.
    ("this repo's OWN build entry", "node packages/cli/bundle.mjs"),
    (
        "the path is an OUTPUT flag, not the program",
        "node scripts/x.mjs --outdir packages/cli/dist/out.js",
    ),
    ("prose merely quoting the banned command", "echo 'node packages/cli/dist/cli.js'"),
    ("a wrapper payload is still scanned", "sh -c 'node packages/cli/dist/cli.js'"),
    ("node with an unrelated program", "node scripts/dev/x.mjs"),
    # Command position: the whitespace arm of the old anchor refused this sentence.
    (
        "a sentence naming the command is not running it",
        "echo the docs say never to run node cli-bundle.js in this repo",
    ),
    ("a prefix command still reaches it", "sudo node cli-bundle.js"),
    ("npx is a launcher shellscan walks", "npx node cli-bundle.js"),
    # Launchers walked by shellscan (#ec63ff8c): both were allowed before 2026-10-09.
    ("npx with its own flag before node", "npx -y node packages/cli/dist/cli.js"),
    ("find -exec running node", r"find packages -maxdepth 0 -exec node cli-bundle.js \;"),
    (
        "npx running another program over the bundle path",
        "npx -y prettier --check packages/cli/dist/cli.js",
    ),
    ("npx -c runs a shell string", "npx -c 'node cli-bundle.js'"),
    ("npx running tsx", "npx tsx scripts/gen/gen-docs.ts"),
    ("after && still reaches it", "cd x && node cli-bundle.js"),
    # npm's own parse finds the program (#31ed6c5f): abbreviated options, and `npm exec`/`exe`/`x` as launchers. Each refusal was allowed before.
    ("an abbreviated npx value option", "npx --logl silent node packages/cli/dist/cli.js"),
    ("npm exec launches node", "npm exec -- node packages/cli/dist/cli.js"),
    ("npm x launches node", "npm x node packages/cli/dist/cli.js"),
    (
        "an npm option before an abbreviated exec",
        "npm --logl silent exe -- node packages/cli/dist/cli.js",
    ),
    ("npm exec -c runs a shell string", "npm exec -c 'node packages/cli/dist/cli.js'"),
    (
        "npm exec running another program over the bundle path",
        "npm exec -- prettier --check packages/cli/dist/cli.js",
    ),
    ("npm run is not a launcher", "npm run build -- packages/cli/dist/cli.js"),
    ("npm x running tsx", "npm x tsx --version"),
]
