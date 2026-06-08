#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Roamingstatus/travel-nurse-credentials"

# Accept either GITHUB_TOKEN or GITHUB_PAT (legacy name)
TOKEN="${GITHUB_TOKEN:-${GITHUB_PAT:-}}"

if [ -z "$TOKEN" ]; then
  echo "ERROR: Neither GITHUB_TOKEN nor GITHUB_PAT secret is set."
  echo "Add a GitHub Personal Access Token (repo scope) as GITHUB_TOKEN in Replit Secrets."
  exit 1
fi

# ── Step 1: Clear stale lock files ───────────────────────────────────────────
find .git -name "*.lock" -type f -delete 2>/dev/null || true

# ── Step 2: Scrub .replit from current branch history (one-time) ─────────────
# Only check HEAD-reachable commits (not --all) so we don't re-trigger on the
# gitsafe-backup remote which still has old refs.
if git log HEAD --oneline --follow -- .replit 2>/dev/null | grep -q .; then
  echo "Scrubbing .replit from git history (one-time operation)..."
  git-filter-repo --path .replit --invert-paths --force --quiet
  echo "  scrub complete"
else
  echo ".replit absent from branch history — skipping scrub"
fi

# ── Step 3: Ensure .replit is gitignored ────────────────────────────────────
if ! grep -qxF '.replit' .gitignore 2>/dev/null; then
  echo '.replit' >> .gitignore
  git add .gitignore
  git -c user.email="push-script@local" -c user.name="Push Script" \
      commit -m "gitignore: exclude .replit (contains Replit-specific config)" \
      --allow-empty || true
fi

# ── Step 4: Ensure origin remote exists, then push ───────────────────────────
AUTHED_URL="https://${TOKEN}@github.com/Roamingstatus/travel-nurse-credentials.git"

# Restore plain HTTPS on exit (success or failure)
trap 'git remote set-url origin "$REPO_URL" 2>/dev/null || git remote remove origin 2>/dev/null || true' EXIT

# Add or update origin
if git remote get-url origin &>/dev/null; then
  git remote set-url origin "$AUTHED_URL"
else
  git remote add origin "$AUTHED_URL"
  echo "Added origin remote"
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Pushing branch '$BRANCH' to GitHub..."
git push --force origin "$BRANCH"

echo "Done. Repository is up to date at $REPO_URL"
