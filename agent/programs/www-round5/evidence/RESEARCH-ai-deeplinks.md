# Research: zero-cost "Ask Assistant" deep links for docs

Status: research complete (web-only, no repo edits). Plan mode blocked the requested
output path `/home/muhammed/console/agent/a68f3ab4/RESEARCH-ai-deeplinks.md`,
so the full findings live here. Copy this file to that path once plan mode is exited.

**Confidence legend:** HIGH = documented by the vendor or reproduced by multiple
independent 2026 sources. MED = multiple third-party sources agree, no vendor doc.
LOW = single source, or sources disagree.

---

## 1. Claude (claude.ai)

**Web:** `https://claude.ai/new?q=<urlencoded prompt>`

- Parameter name is `q`. No vendor documentation exists for the *web* URL - Anthropic's
  only published deep-link doc covers the desktop scheme (below) and explicitly scopes
  itself to Desktop.
  Source: https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link
- Third-party link generators still ship `claude.ai/new?q=` as their current output and
  claim it **auto-submits on most clicks** ("Yes on most clicks", with edge cases needing
  a manual send). Confidence MED - this is a vendor-unsupported surface.
  Source: https://u2l.ai/tools/claude-prompt-link-generator
  Source: https://folge.me/tools/prompt-to-url (also lists an `incognito` flag for an
  anonymous chat)
- Security research from March 2026 (updated May 2026) describes `claude.ai/new?q=...` as
  a live feature and used it as the delivery vector for a prompt-injection/exfiltration
  chain. Anthropic fixed the injection, not the parameter.
  Source: https://www.oasis.security/blog/claude-ai-prompt-injection-data-exfiltration-vulnerability
- **Conflicting claim:** one search-summary source asserts the web `?q=` was removed in
  October 2025. No primary evidence for that was found, and the March/May 2026 security
  writeup plus current generators contradict it. Treat as unresolved. Confidence LOW on
  "removed"; MED on "still works".
- **Logged out:** generators say the user is bounced to claude.ai signup and the prompt
  "usually" survives the login redirect, but corporate SSO and account-switching can drop
  the parameter. Confidence LOW.
- **Length:** no published web limit. The desktop doc's 14,000-character truncation is the
  only hard number Anthropic publishes, and it is desktop-only.
- Direct verification was not possible: `WebFetch https://claude.ai/new?q=hello` returns
  **HTTP 403** (bot/Cloudflare block), so this needs a real browser to confirm.

**Desktop (documented, HIGH confidence):**

```
claude://claude.ai/new?q=Summarize%20this%20week%27s%20release%20notes
claude://code/new?q=Fix%20the%20failing%20test&folder=%2FUsers%2Fme%2Frepo
claude://cowork/new?q=Draft%20the%20Q2%20update&folder=%2FUsers%2Fme%2Fdocs
```

| Param | Notes (verbatim from the doc) |
|---|---|
| `q` | "Text to prefill in the prompt field" |
| `prompt` | alias for `q`, Code sessions only |
| `folder` | absolute path, triggers a confirmation dialog |
| `file` | "not currently supported" |

- "Prompt text passed in `q` is truncated to roughly 14,000 characters."
- Behaviour is **prefill only** - the doc says prefill, never auto-send.
- All values must be URL-encoded.

---

## 2. ChatGPT

**Canonical host is `chatgpt.com`.** `chat.openai.com` still redirects and is still used in
older write-ups, but every current example uses `chatgpt.com`.

`https://chatgpt.com/?q=<urlencoded prompt>`

- `q` is the prompt. Confidence HIGH - this is the URL OpenAI's own ChatGPT search Chrome
  extension installs as the browser's default search engine:
  `https://chatgpt.com/?q=%s&hints=search&ref=ext`
  Source: https://www.bleepingcomputer.com/news/security/openais-new-chatgpt-search-chrome-extension-feels-like-a-search-hijacker/
  Source: https://chromewebstore.google.com/detail/chatgpt-search/ejcfepkfckglbgocfkanmcdngdijcgld
- `hints=` selects a UI mode. Documented values in the wild:
  `search | image | think | research | shopping | study | canvas`.
  It is a **client-side UI shortcut only**, not an API.
  Source: https://matthew.philogene.co.za/understanding-chatgpts-hints-parameter-a-ui-shortcut-not-a-search-window/
  Source: https://folge.me/tools/prompt-to-url
- `temporary-chat=true` opens an ephemeral chat. Confidence MED.
  Source: https://folge.me/tools/prompt-to-url
- **Auto-submit:** yes in the search-engine flow (that is the whole point of `hints=search`
  + `ref=ext`). For a bare `?q=` without `hints`, sources describe prefill and disagree on
  auto-send. Confidence MED. Do not depend on either behaviour.
- **`model=` does NOT work.** A reported bug: passing `q=` forces the default model and
  silently ignores `model=`. Confidence MED.
  Source: https://community.openai.com/t/using-the-q-url-parameters-defaults-the-model-to-gpt4o-even-if-you-explicitly-pass-a-model-via-the-url-using-model/1074025
- **Length:** no published limit. One generator caps at 4,000 chars overall and notes
  ChatGPT itself tolerates ~6,000. Confidence LOW.

---

## 3. Other providers

### Perplexity - works
`https://www.perplexity.ai/search?q=<urlencoded>` (also `https://www.perplexity.ai/?q=`).
This is the documented "add Perplexity as a browser search engine" URL, so it **runs the
query** rather than merely prefilling. Confidence HIGH for the search-engine form.
Source: https://github.com/qutebrowser/qutebrowser/discussions/8435
Source: https://folge.me/tools/prompt-to-url

### Grok - works
`https://grok.com/?q=<urlencoded>`. "Grok auto-submits the `q=` value on page load. Some
edge cases require a manual submit click." Recommended cap 2,000 chars pre-encoding.
Confidence MED (third-party only).
Source: https://u2l.ai/tools/grok-prompt-link-generator

### Microsoft Copilot - works, and this is the cautionary tale
`https://copilot.microsoft.com/?q=<urlencoded>`. "When a user clicks this URL, Copilot
automatically loads the prompt and executes it as if the user had manually typed and
submitted it" - on page load, no further interaction. Confidence HIGH that the parameter
exists and auto-executes; UNKNOWN whether the January 2026 patch narrowed it.
Source: https://wizardcyber.com/reprompt-attack-microsoft-copilot-ai-abuse/
Source: https://www.malwarebytes.com/blog/news/2026/01/reprompt-attack-lets-attackers-steal-data-from-microsoft-copilot
This is the "Reprompt" attack (CVE-2026-24307 / related CVE-2026-21516), disclosed by
Varonis Threat Labs, patched in the 13–14 January 2026 Patch Tuesday. A one-click link
exfiltrated profile details, file summaries and conversation memory from an authenticated
consumer session. **Relevance to us: a prefilled-prompt deep link is a documented attack
surface. Our button must only ever carry text the user can see.**

### Google Gemini - does NOT work natively
`gemini.google.com/app?q=` / `?prompt=` only function with a third-party Chrome extension
that simulates keystrokes; Gemini has no native URL prefill. One generator lists
`gemini.google.com/app?q=` as supported, which contradicts the extension authors - treat
the generator as wrong. Confidence MED that it does not work natively.
Source: https://github.com/elliot79313/gemini-url-prompt
Source: https://chromewebstore.google.com/detail/gemini-url-prompt/kdbgjkfdooaiompgeckjbegnnccchmma

### Google AI Studio - partial
`https://aistudio.google.com/app/prompts/new_chat` accepts `model=` and `grounding=true`,
but a prompt-prefill parameter is an open feature request, not a shipped feature. Mintlify
nonetheless ships an `aistudio` contextual-menu option, so some mechanism may exist -
unverified. Confidence LOW.
Source: https://discuss.ai.google.dev/t/set-prompt-to-aistudio-via-url-query-parameter/77309

### Mistral Le Chat - no evidence
No URL-prefill parameter found for `chat.mistral.ai`. Also note the service was rebranded
toward "Mistral Vibe" in May 2026. Confidence LOW; do not ship a Mistral button.

---

## 4. Practical URL length

**Ship a 2,000-character budget for the entire URL.** That is the real-world figure, and it
is set by servers and intermediaries, not browsers.

- Browsers are not the constraint: Chrome tolerates ~2 MB, Firefox stops *displaying* past
  65,536 chars, Safari fails around ~80,000.
- Servers and CDNs are: Apache `LimitRequestLine` defaults to ~8,192, nginx ~4,096, IIS
  ~4,096.
- Sources: https://learn.microsoft.com/en-us/archive/blogs/ieinternals/url-length-limits ,
  https://urlencodedecode.com/blog/url-length-limits-by-browser.html
- Independent corroboration from the link-generator side: both u2l.ai generators cap at
  "2000 chars before URL encoding … URLs over ~2000 chars fail in older browsers, Outlook";
  folge.me caps at 4,000.
- **URL-encoding roughly triples the cost of newlines, punctuation and non-ASCII** (`\n` →
  `%0A`, each non-ASCII byte → `%XX`), so a 2,000-char URL carries roughly 1,200–1,500
  characters of readable prompt, and much less for a non-English locale.

**Conclusion: inlining page content is not viable.** A single docs page is 5–50 KB of
markdown. Send a short question plus a URL pointer to the markdown, and let the assistant
fetch it.

---

## 5. How real docs sites do it

### Vercel - closest model to what we want
- Changelog 18 July 2025: a "copy page dropdown in the top right corner … select your
  provider or copy as markdown", with **v0, Claude and ChatGPT** as the three providers.
  "The page content will be formatted and loaded into the selected AI provider."
  Source: https://vercel.com/changelog/open-vercel-documentation-pages-in-ai-providers
- Menu items (from the docs page itself, last updated 2026-02-27):
  - **View as Markdown** - refetches the canonical URL with `Accept: text/markdown`, makes
    a browser-local Blob, opens it in a new tab.
  - **Copy page** - copies the markdown to the clipboard.
  Source: https://vercel.com/docs/agent-resources/markdown-access
- Vercel also does **content negotiation**: `https://vercel.com/docs/functions` returns HTML
  to a browser and `text/markdown` when the request carries `Accept: text/markdown` *or*
  when it detects a known AI agent, with `Vary: Accept` so caches stay separate. Plus
  `.md` endpoints, `.graph.md` cross-link maps, `graph.json`, `sitemap.md`, `taxonomy.json`.
- The exact provider URLs Vercel builds are **not published** and are constructed in
  client-side JS. Confirming them needs a real browser with devtools.

### PostHog - same pattern, explicitly named
Menu in the bottom-right of every docs page offers four items:
1. Copy Markdown  2. View raw Markdown  3. "Open a prompt in **ChatGPT** to read the page"
4. "Open a prompt in **Claude** to read the page".
The phrasing "a prompt … to read the page" strongly implies **a URL pointer, not inlined
content**. Per-page markdown via `.md` (`https://posthog.com/docs/getting-started/install.md`),
index at `https://posthog.com/llms.txt`.
Source: https://posthog.com/docs/ai-engineering/markdown-llms-txt

### Mintlify - the most configurable, and it is a product surface
`docs.json` → `contextual.options`. Built-ins:
`copy`, `view`, `assistant`, `download-pdf`, `chatgpt`, `claude`, `perplexity`, `grok`,
`aistudio`, `devin`, `devin-desktop`, `mcp`, `add-mcp`, `cursor`, `vscode`, `devin-mcp`,
`download-spec`. `display` is `header` (default) or `toc`. Per-page override via frontmatter.

```json
{ "contextual": { "options": ["copy", "view", "chatgpt", "claude"], "display": "header" } }
```

Custom entries use a templated href with three placeholders - **`$page` (the current page
content as markdown), `$path` (the page path), `$mcp` (the hosted MCP server URL)**:

```json
{ "href": { "base": "https://x.com/intent/tweet",
            "query": [{ "key": "text", "value": "Check out this documentation: $page" }] } }
```

Mintlify does **not** publish the base URLs behind the built-in `chatgpt`/`claude` options.
The existence of `$page` (full markdown) as a placeholder shows they do inline content for
custom options, which makes the 2,000-char budget a live concern for anyone using it.
Source: https://www.mintlify.com/docs/ai/contextual-menu

### Kinde - the one site whose exact URL is published
Builds only a ChatGPT link, and it sends **a URL, not content**:

```
https://chat.openai.com/?q=Can%20you%20summarize%20this%20page%3A%20https%3A%2F%2Fdocs.kinde.com%2Fget-started%2Fguides%2Ffirst-things-first%2F
```

decoded: `Can you summarize this page: https://docs.kinde.com/get-started/guides/first-things-first/`

The author says Claude and Gemini "don't support this type of pre-written prompt" and ships
a "Copy for AI" clipboard button instead. That assessment is from an earlier snapshot and is
now wrong about Claude.
Source: https://dev.to/kinde/adding-some-ai-hints-to-our-documentation-1nhf

### Cloudflare - markdown only, no provider buttons
`developers.cloudflare.com/workers/llms.txt`, `developers.cloudflare.com/workers/index.md`,
a "View as Markdown" affordance, and an `/agent-setup/` hub pushing Skills + MCP. No
"Open in ChatGPT/Claude" links found on the page.
Source: https://developers.cloudflare.com/workers/ , https://developers.cloudflare.com/agent-setup/

### Fumadocs - open-source, drop-in
`npx @fumadocs/cli add ai/page-actions` gives `<LLMCopyButton markdownUrl>` and
`<ViewOptions markdownUrl githubUrl>`; generates `llms.txt`, `llms-full.txt`, per-page
`.md`/`.mdx`, and supports `Accept`-header negotiation. Worth reading its `page-actions`
component for the real provider URLs.
Source: https://www.fumadocs.dev/docs/integrations/llms

---

## 6. llms.txt conventions

**Spec (llmstxt.org):**
- "We propose adding a `/llms.txt` markdown file to websites to provide LLM-friendly
  content." A curated *index*, not a dump - so an agent finds what it needs without
  burning tokens.
- Format: an H1 with the project name (**the only required section**); an optional
  blockquote summary; zero or more H2-delimited sections containing file lists, each entry
  `[name](url)` optionally followed by `:` and notes.
- Per-page markdown convention, verbatim: pages "provide a clean markdown version of those
  pages at the same URL as the original page, either with `.md` appended (`page.html.md`)
  or with the extension replaced by `.md`."
- **`llms-full.txt` is NOT in the spec.** It is a de-facto convention (a single file
  containing the whole corpus) popularised by Mintlify, Vercel and Fumadocs.
  Source: https://llmstxt.org/

**Per-page `.md` support among the sites in §5:**

| Site | `llms.txt` | `llms-full.txt` | per-page `.md` |
|---|---|---|---|
| Vercel | `vercel.com/llms.txt` | `vercel.com/docs/llms-full.txt` | yes, `.md` + `Accept:` negotiation + `.graph.md` |
| PostHog | `posthog.com/llms.txt` | - | yes, `.md` |
| Cloudflare | `developers.cloudflare.com/llms.txt` | - | yes, as `index.md` per directory |
| Mintlify (and every site it hosts) | auto, also `/.well-known/llms.txt` | auto, also `/.well-known/llms-full.txt` | yes - llms.txt entries carry `.md`, plus `Link` and `X-Llms-Txt` discovery headers |
| Stripe | `docs.stripe.com/llms.txt` | - | not verified |
| Supabase | `supabase.com/docs/llms.txt` | - | not verified |
| Anthropic | `docs.claude.com/llms.txt` | `docs.claude.com/llms-full.txt` | not verified |
| Fumadocs sites | generated | generated | yes |

Sources: https://mintlify.com/docs/ai-ingestion , https://www.mintlify.com/blog/real-llms-txt-examples

---

## 7. Ready-to-use provider table

| Provider | URL template | Auto-submits? | Confidence (Aug 2026) | Caveats |
|---|---|---|---|---|
| ChatGPT | `https://chatgpt.com/?q={prompt}` (opt. `&hints=search`, `&temporary-chat=true`) | likely, esp. with `hints=search` | HIGH the param works; MED on auto-submit | `model=` is ignored when `q` is present; `chat.openai.com` redirects |
| Claude (web) | `https://claude.ai/new?q={prompt}` | reported yes, "most clicks" | MED - undocumented, one source claims removal | Could not verify: claude.ai returns 403 to non-browser fetches |
| Claude (desktop) | `claude://claude.ai/new?q={prompt}` | no, prefill only | HIGH - vendor-documented | `q` truncated at ~14,000 chars; needs the desktop app installed |
| Perplexity | `https://www.perplexity.ai/search?q={prompt}` | yes (it is a search URL) | HIGH | answers rather than converses |
| Grok | `https://grok.com/?q={prompt}` | yes, on page load | MED | third-party sources only |
| Copilot | `https://copilot.microsoft.com/?q={prompt}` | yes, on page load, no interaction | HIGH it exists | this exact behaviour was CVE-2026-24307; post-patch behaviour unverified |
| Gemini | none native (`?q=`/`?prompt=` need a browser extension) | n/a | MED | do not ship |
| Google AI Studio | `.../app/prompts/new_chat?model=…&grounding=true`; prompt prefill unshipped | n/a | LOW | do not ship |
| Mistral Le Chat | none found | n/a | LOW | do not ship |

`{prompt}` is always `encodeURIComponent`'d.

---

## 8. Recommendation

Ship a **"Copy page as Markdown" + dropdown** in the docs page header, exactly the
Vercel/PostHog/Mintlify shape, with four members: Copy as Markdown, View as Markdown,
Open in ChatGPT, Open in Claude. Add Perplexity and Grok behind the same abstraction if we
want more members; skip Gemini, AI Studio and Mistral (no native prefill), and skip Copilot
(its auto-execute is the exact behaviour that produced a January 2026 CVE, and its
post-patch semantics are unverified).

**Send a pointer, never the page body.** The safe budget is 2,000 characters for the whole
URL, and encoding costs roughly 3× on newlines and non-ASCII, so a page will not fit and a
truncated page is worse than no page. Build:

```
https://chatgpt.com/?hints=search&q=<enc>
https://claude.ai/new?q=<enc>
```

with a prompt of the shape:

> Read `https://rediacc.com/docs/<page>.md` and answer using it. Full docs index:
> `https://rediacc.com/llms.txt`. My question: `<user text>`

That keeps every link well under 500 characters even with a long question, costs us zero
API spend, and degrades gracefully: if the provider only prefills rather than auto-submits,
the user just presses Enter.

**Prerequisites this depends on** - we must actually serve them before the button is
meaningful:
1. per-page `.md` (spec convention: `.md` appended, or the extension replaced),
2. `llms.txt` as a curated index - and mirror it at `/.well-known/llms.txt`,
3. `llms-full.txt` for whole-corpus paste,
4. optionally `Accept: text/markdown` negotiation on canonical URLs with `Vary: Accept`.

**One caveat to state out loud:** `claude.ai/new?q=` is undocumented by Anthropic for the
web, sources disagree on whether it still works, and I could not verify it (403 to
non-browser fetches). Before shipping, click both links once in a real browser, logged in
and logged out. Anthropic's *documented* path is the desktop scheme `claude://claude.ai/new?q=`,
which is a reasonable fallback but requires the desktop app.

---

## Remaining / not done

- Could not empirically verify any URL in a real browser - plan mode plus the 403 from
  claude.ai. Ten minutes with `agent-browser` would settle Claude web, ChatGPT auto-submit,
  and the logged-out redirect question.
- The exact provider URLs Vercel and Mintlify build are client-side JS and are not
  published; reading them needs devtools on a live page, or the Fumadocs `page-actions`
  source (`npx @fumadocs/cli add ai/page-actions`).
