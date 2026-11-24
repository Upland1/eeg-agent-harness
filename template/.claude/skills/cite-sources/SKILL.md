---
name: cite-sources
description: How every agent records the sources behind a solution — papers, documentation, external code examples, the supervisor's own code, rules — in its handoff file. Use before writing or finishing any handoff file, and whenever a decision, formula, parameter or piece of code comes from somewhere.
---

# Cite sources

Every agent says where its solution came from. A reader (the supervisor, the requester,
the methods-auditor) must be able to open each source and check the claim. This
procedure implements CLAUDE.md **G6**.

## When to cite

Cite every time you use something you did not derive on the spot:

- a method, formula, threshold, parameter value or default;
- an architecture or training recipe;
- an implementation pattern taken from a library, a repository or this project's code;
- a known answer used in a synthetic test;
- a decision taken because of a rule, an audit finding or a request.

If a choice is your own, write `[own]` and one line on why. Never leave a choice
uncited and never invent a source. If you cannot find a source, say so.

## How to cite in the text

Put a bracketed number right after the claim, change or table row: `[1]`, `[2, 3]`.
Use the same number for the same source within one file. Every file that cites has
a `## Sources` section at the end, numbered to match.

In tables, the **Source** column holds the numbers (`[2]`), `G3`, `05_audit #1`, or
`[own]`.

## Formats for the Sources list

Pick the line that matches the source type. Keep the type tag in front.

| Type | Format |
|---|---|
| Paper | `[n] PAPER — Authors (Year). Title. Venue. DOI or URL. Used for: …` |
| Book / chapter | `[n] BOOK — Authors (Year). Title, chapter/section, pages. Used for: …` |
| Documentation | `[n] DOCS — Library vVersion, page title. URL. Used for: …` |
| External code example | `[n] CODE — owner/repo @ commit-or-tag, path:line-line. License. Used for: …` |
| This project's code | `[n] OWN-CODE — path:line-line @ commit. Used for: …` |
| Project rule | `[n] RULE — CLAUDE.md Gk` |
| Audit / handoff | `[n] HANDOFF — agent_runs/<run>/05_audit.md, Round N, finding k` |
| Request | `[n] REQUEST — 00_assignment.md (requester / the supervisor), quoted phrase` |
| Data / output | `[n] DATA — path to CSV or log, command that produced it, commit` |
| Own reasoning | `[own]` inline only, never in the list |

Get the commit with `git rev-parse --short HEAD` (or `git -C <repo> rev-parse --short
HEAD`) and line numbers from the file you actually read. Versions come from
`pip show <package>`, not memory.

## Rules for code examples

1. **Read, understand, then write your own.** Use examples to learn the structure and
   check your result. Re-implement in this project's style.
2. **Copying.** Copy at most a few lines, only from code with a compatible license
   (MIT, BSD, Apache-2.0; check the repo's LICENSE file), and mark the lines with a
   comment `# adapted from [n]`. No copying from code without a license.
3. **Prefer primary sources.** The paper's own code or the library that defines the
   method (MNE, mne-connectivity, scikit-learn, SciPy, braindecode, pyRiemann) over
   blog posts or random gists. Say which you used.
4. **Record differences.** When your version differs from the example (e.g. sampling
   rate, window length, channel count, normalization), say how and why.
5. **Code written for another paradigm** is a source like any other, cited with commit and
   lines. Say why what you take applies to this project's paradigm (docs/PARADIGM.md).

## Checklist before marking your file READY

- [ ] Every row of the Changes / Tests table has something in its Source column.
- [ ] Every `[n]` in the text appears in `## Sources`, and every source is cited.
- [ ] Code sources carry repo, commit, path and lines; docs carry a version.
- [ ] Copied lines are marked in the code and covered by a compatible license.
- [ ] Nothing is cited that you did not actually open in this run.
