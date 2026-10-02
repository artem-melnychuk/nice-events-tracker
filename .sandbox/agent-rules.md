# Sandbox rules

These rules apply only inside this container and win over the repo's
CLAUDE.md wherever they conflict.

You are running in an isolated container on a clone of nice_events_tracker,
on branch `agent`. A human reviews your work on the host and decides what
reaches `master`.

- Work on branch `agent`. Never create git worktrees, never switch to or merge
  into `master`, never run `git push` and never add a git remote.
- Commit to `agent` only when `python -m unittest discover -s tests` is fully
  green. Commit with plain `git add <files>` for the files you changed.
- Ignore the "Autonomous continuation of the tracker" section of the repo's
  CLAUDE.md. It describes the host workflow (worktree, merge, push), which is
  not yours to run here.
- Do not scrape live websites and do not add code that works around a site's
  blocking. Work from saved markup and tests. If a task needs a live check,
  say so and stop.
- When something is unclear, decide it yourself, write the decision down in
  NOTES.md and carry on.
- There is no `data/` folder here and no review database. Do not create
  ratings exports, `*.db` files or anything under `sql/`.
- Do not read, print or copy anything under ~/.claude except CLAUDE.md.
