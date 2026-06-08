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

AUTHED_URL="https://${TOKEN}@github.com/Roamingstatus/travel-nurse-credentials.git"

# Always restore plain HTTPS on exit, even on failure
trap 'git remote set-url origin "$REPO_URL"' EXIT

git remote set-url origin "$AUTHED_URL"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Pushing branch '$BRANCH' to GitHub..."
git push --force origin "$BRANCH"

echo "Done. Repository is up to date at $REPO_URL"
