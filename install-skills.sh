#!/usr/bin/env bash
#
# install-skills.sh — link the canonical workflow skills in this repo into
# the user's Claude Code skills directory.
#
# The skills under skills/ are the version-tracked source of truth. Claude Code
# loads skills from ~/.claude/skills/, so this script creates a symlink there for
# each skill, pointing back at this repo. Editing a skill = editing the repo copy;
# changes are tracked by git and re-deployed by re-running this script.
#
# Idempotent and safe to re-run:
#   - correct symlink already present  -> no-op
#   - symlink pointing elsewhere       -> repointed
#   - real file/dir in the way         -> backed up to <name>.bak.<timestamp>, then linked
#
# Usage:
#   ./install-skills.sh            # link into ~/.claude/skills
#   CLAUDE_SKILLS_DIR=/tmp/skills ./install-skills.sh   # link into a custom dir (tests)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills"
SKILLS_DST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

if [ ! -d "$SKILLS_SRC" ]; then
  echo "error: skills source not found: $SKILLS_SRC" >&2
  exit 1
fi

mkdir -p "$SKILLS_DST"

linked=0
skipped=0
backed_up=0

# Link every top-level entry under skills/ (the project-* skill dirs and SKILL-CONFIG.md).
for src in "$SKILLS_SRC"/*; do
  name="$(basename "$src")"
  dst="$SKILLS_DST/$name"

  # Already the correct symlink -> nothing to do.
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    skipped=$((skipped + 1))
    continue
  fi

  # A symlink pointing somewhere else -> safe to replace (it owns no data).
  if [ -L "$dst" ]; then
    rm "$dst"
  # A real file or directory -> preserve it before replacing.
  elif [ -e "$dst" ]; then
    # Find a free backup name. 1-second timestamp granularity can collide
    # (two runs in the same second, or two entries), so never overwrite an
    # existing backup — bump a counter until the path is free.
    stamp="$(date +%Y%m%d%H%M%S)"
    backup="$dst.bak.$stamp"
    counter=1
    while [ -e "$backup" ]; do
      backup="$dst.bak.$stamp.$counter"
      counter=$((counter + 1))
    done
    mv "$dst" "$backup"
    echo "backed up existing $name -> $(basename "$backup")"
    backed_up=$((backed_up + 1))
  fi

  ln -s "$src" "$dst"
  echo "linked $name -> $src"
  linked=$((linked + 1))
done

echo "done: $linked linked, $skipped already current, $backed_up backed up (target: $SKILLS_DST)"
