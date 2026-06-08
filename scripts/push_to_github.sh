#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Roamingstatus/travel-nurse-credentials"

if [ -z "${GITHUB_PAT:-}" ]; then
  echo "ERROR: GITHUB_PAT secret is not set."
  echo "Add it in Replit Secrets (the lock icon in the sidebar) then re-run this workflow."
  exit 1
fi

AUTHED_URL="https://${GITHUB_PAT}@github.com/Roamingstatus/travel-nurse-credentials.git"

git remote set-url origin "$AUTHED_URL"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Pushing branch '$BRANCH' to GitHub..."
git push origin "$BRANCH"

git remote set-url origin "$REPO_URL"

echo "Done. Repository is up to date at $REPO_URL"
