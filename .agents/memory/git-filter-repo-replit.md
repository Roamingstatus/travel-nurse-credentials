---
name: git-filter-repo deletes tracked files in Replit
description: Running git-filter-repo in Replit removes tracked files from the working tree AND deletes the .replit config file, breaking the environment.
---

## Rule
Never run `git-filter-repo` (or any history-rewriting tool) without immediately verifying `.replit` still exists afterward and reinstalling all language modules.

## Why
`git-filter-repo` rewrites the working tree to match the rewritten history. Any file it removes from history also disappears from disk. Since `.replit` declares the language modules (`modules = ["python-3.11"]`, nodejs, etc.), losing it means the container drops those runtimes on next restart, causing `ModuleNotFoundError: No module named 'uvicorn'` and `npm: command not found`.

## How to apply
After any history rewrite:
1. Check `.replit` exists — if missing, recreate workflows via `configureWorkflow()` and reinstall language modules via `installProgrammingLanguage()`
2. Reinstall Python deps: `pip install -r requirements.txt && pip install stripe`
3. Node.js: `installProgrammingLanguage({ language: "nodejs-20" })`
4. The `.replit` file is now gitignored (line 60 of `.gitignore`) — good, it won't be committed again, but it must exist on disk for Replit to work.
