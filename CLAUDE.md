# lynx-portfolio

Working notes for sessions in this project.

<!-- LYNX-EP-NOTE:BEGIN -->

## Entry-point card — keep it current

This project carries `index.ep.md` (and `index.ep.html`), the standard card
that answers what this is, where to look first, and how to run it. Every
project in `~/claude/` has one in the same shape, so jumping between them
does not mean re-learning where to look.

**When work here changes any of the following, refresh the card:**

- what the project is or does (title, one-line purpose, description)
- the file someone should open first
- the command that starts it
- the top-level layout or where the documentation lives

Refresh it with:

```bash
python3 ~/claude/lynx_factory/web/tools/gen_ep_index.py --only <this-project>
```

That regenerates from this repo's own README/CLAUDE.md plus the Lynx Factory
ledger — it does not invent anything, so fixing the card usually means fixing
the README first. The README's ownership footer is refreshed by the same
command.

To hand-write a card and stop it being regenerated, set `ep_locked: true` in
its front matter.

<!-- LYNX-EP-NOTE:END -->
