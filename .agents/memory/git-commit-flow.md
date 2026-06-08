---
name: Git commit flow
description: How to get code changes committed and pushed to GitHub from the main agent.
---

## Rule
`git commit` is blocked in the main agent shell (exits 254). Replit auto-commits all changes when `mark_task_complete` is called. To push to GitHub after the auto-commit, the user runs the "Push to GitHub" workflow.

**Why:** Replit sandbox policy prevents direct git commits from the main agent.

## How to apply
1. Make all code changes via write/edit/bash tools.
2. Do NOT try `git commit` — it will fail with exit code 254.
3. Call `mark_task_complete` — Replit auto-commits everything at that point.
4. After the auto-commit, user (or agent via workflow restart) runs "Push to GitHub" to push to the remote.
