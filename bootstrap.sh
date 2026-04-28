#!/usr/bin/env bash
#
# bootstrap.sh — one-time setup for a fresh meta/ folder.
#
# Run this once, right after copying meta-template/ into your project.
# It substitutes {{PROJECT_NAME}} placeholders, optionally initializes git,
# and then deletes itself (since it has no purpose after the first run).
#
# Re-running is safe — substitution is idempotent — but the script will
# refuse to run if {{PROJECT_NAME}} is no longer present anywhere.

set -euo pipefail

# ---- Locate ourselves and refuse to run from the template repo --------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "$(basename "$SCRIPT_DIR")" == "meta-template" ]]; then
  echo "ERROR: bootstrap.sh appears to be running inside the meta-template/ source folder."
  echo "Copy meta-template/ to your project as meta/, then run bootstrap.sh from there."
  exit 1
fi

# ---- Sanity: verify we're in something that looks like our template ---------
for required in GOVERNANCE.md README.md STATUS.md scripts/build_index.py; do
  if [[ ! -f "$required" ]]; then
    echo "ERROR: $required not found. Are you in the meta/ folder?"
    exit 1
  fi
done

# ---- Detect whether bootstrap is needed ------------------------------------
# Exclude bootstrap.sh itself — it deliberately mentions the placeholder in its
# own code (substitution markers + this self-check), and those references are
# not user-facing project content.
if ! grep -rl '{{PROJECT_NAME}}' . --exclude='bootstrap.sh' --exclude-dir='.git' >/dev/null 2>&1; then
  echo "No {{PROJECT_NAME}} placeholders found. Bootstrap already ran."
  read -r -p "Delete bootstrap.sh anyway? [y/N] " ans
  if [[ "${ans:-N}" =~ ^[Yy]$ ]]; then
    rm -- "$0"
    echo "Deleted bootstrap.sh."
  fi
  exit 0
fi

# ---- Prompt for project name -----------------------------------------------
echo "============================================================"
echo "  meta/ bootstrap"
echo "============================================================"
echo
echo "This script personalizes the meta/ folder for your project."
echo

DEFAULT_NAME="$(basename "$(cd .. && pwd)")"
read -r -p "Project name [${DEFAULT_NAME}]: " PROJECT_NAME
PROJECT_NAME="${PROJECT_NAME:-$DEFAULT_NAME}"

if [[ -z "$PROJECT_NAME" ]]; then
  echo "ERROR: project name cannot be empty."
  exit 1
fi

echo
echo "Substituting {{PROJECT_NAME}} → $PROJECT_NAME ..."

# ---- Substitute placeholders -----------------------------------------------
# Use find + a portable in-place sed (BSD + GNU compatible).
PORTABLE_SED_INPLACE() {
  if sed --version >/dev/null 2>&1; then
    sed -i "$@"        # GNU sed
  else
    sed -i '' "$@"     # BSD sed (macOS)
  fi
}

# Files to process: every text file under the meta tree, excluding the script
# itself, .git, and binary-ish locations.
FILES_TO_TOUCH=()
while IFS= read -r f; do
  FILES_TO_TOUCH+=("$f")
done < <(grep -rl '{{PROJECT_NAME}}' . \
         --exclude-dir='.git' \
         --exclude='bootstrap.sh' \
         2>/dev/null)

if [[ ${#FILES_TO_TOUCH[@]} -eq 0 ]]; then
  echo "No files contained {{PROJECT_NAME}} (other than this script). Continuing."
else
  for f in "${FILES_TO_TOUCH[@]}"; do
    PORTABLE_SED_INPLACE "s|{{PROJECT_NAME}}|${PROJECT_NAME}|g" "$f"
    echo "  patched: $f"
  done
fi

# ---- Optionally git init ---------------------------------------------------
echo
if [[ -d .git ]]; then
  echo ".git already exists — skipping git init."
else
  read -r -p "Initialize a fresh git repo for this meta/ folder? [Y/n] " ans
  if [[ ! "${ans:-Y}" =~ ^[Nn]$ ]]; then
    git init -q
    git add .
    git commit -q -m "chore(meta): initial import from meta-template"
    echo "Initialized fresh git repo + committed initial state."
  fi
fi

# ---- Smoke-test the validator ----------------------------------------------
echo
echo "Running validator smoke test..."
if command -v python3 >/dev/null 2>&1; then
  if python3 scripts/build_index.py --validate; then
    echo "Validator OK."
  else
    echo "WARNING: validator failed. Inspect output above."
  fi
else
  echo "python3 not found on PATH — skipping smoke test."
fi

# ---- Self-delete -----------------------------------------------------------
echo
echo "Bootstrap complete."
echo "Next steps:"
echo "  1. Edit STATUS.md and ROADMAP.md to describe your project's current state."
echo "  2. Trim or extend the seed epics in epics/ to match what you're building."
echo "  3. (Optional) install pre-commit hooks: pre-commit install"
echo "  4. (Optional) copy claude-config/ into the project root's .claude/ if you use Claude Code."
echo
read -r -p "Delete bootstrap.sh now? [Y/n] " ans
if [[ ! "${ans:-Y}" =~ ^[Nn]$ ]]; then
  rm -- "$0"
  echo "Deleted bootstrap.sh."
else
  echo "Kept bootstrap.sh. Re-run any time, or delete manually when ready."
fi
