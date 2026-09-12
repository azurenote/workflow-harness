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
# After linking, it reports which tools declared in skills/dependencies.yaml are
# missing. That check is a REPORT, never a gate: it installs nothing and always
# exits 0. These skills also run on hosts with none of these plugins (Codex, CI),
# where the fallback path is a first-class path, not a degraded one.
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

# ---------------------------------------------------------------------------
# Prerequisite tool report (never a gate)
#
# Two axes, and this script can only answer the first:
#   presence — installed on this machine. Checked below.
#   probe    — usable by the agent that is actually running. Host-dependent
#              (terminal Claude Code / Desktop / Codex / CI) and not knowable
#              from here. Declared per tool in the manifest for the agent to
#              observe at run time.
# A clean report below does NOT mean the tools are reachable at run time.
# ---------------------------------------------------------------------------

MANIFEST="$SCRIPT_DIR/skills/dependencies.yaml"
PLUGIN_DB="${CLAUDE_PLUGIN_DB:-$HOME/.claude/plugins/installed_plugins.json}"

# No manifest -> nothing declared, nothing to report.
[ -f "$MANIFEST" ] || exit 0

# No plugin database -> a host that does not use Claude Code plugins (Codex, CI).
# Absence of the check must never surface as a missing prerequisite.
if [ ! -f "$PLUGIN_DB" ]; then
  echo "prerequisites: skipped (no plugin database at $PLUGIN_DB)"
  exit 0
fi

# Flatten the manifest to one record per tool: id, requirement, presence, install,
# members, degrades. The manifest is deliberately a flat scalar-only subset of YAML
# so this works without a YAML parser. Keep it that way.
#
# Fields are separated by ASCII US (\037), not tab: tab is IFS whitespace, so
# `read` collapses runs of it and an empty optional field (members) would silently
# shift every field after it.
manifest_tsv() {
  awk '
    function val(line,   v) {
      v = line
      sub(/^[[:space:]]*(- )?[a-z_]+:[[:space:]]*/, "", v)
      gsub(/^"|"$/, "", v)
      return v
    }
    function flush() {
      if (id != "") printf "%s\037%s\037%s\037%s\037%s\037%s\n", id, req, pres, inst, memb, deg
      id = ""; req = ""; pres = ""; inst = ""; memb = ""; deg = ""
    }
    /^  - id:/          { flush(); id = val($0); next }
    /^    requirement:/ { req  = val($0); next }
    /^    presence:/    { pres = val($0); next }
    /^    install:/     { inst = val($0); next }
    /^    members:/     { memb = val($0); next }
    /^    degrades:/    { deg  = val($0); next }
    END { flush() }
  ' "$MANIFEST"
}

# Is one plugin id present in the plugin database? The database keys them
# verbatim as "<name>@<marketplace>", so a fixed-string match is exact enough
# and needs no JSON parser.
plugin_installed() {
  grep -qF "\"$1\"" "$PLUGIN_DB"
}

echo
echo "prerequisites (report only — nothing is installed, exit is always 0):"

missing=0
while IFS=$'\037' read -r id req pres inst memb deg; do
  [ -n "$id" ] || continue
  present=unknown
  case "$pres" in
    installed_plugins)
      if plugin_installed "$id"; then present=yes; else present=no; fi
      ;;
    installed_plugins_any)
      present=no
      # Any one member satisfies the group; which member is the right one is
      # language-specific, and only the consuming project knows that.
      old_ifs="$IFS"; IFS=','
      for m in $memb; do
        m="$(echo "$m" | tr -d '[:space:]')"
        [ -n "$m" ] || continue
        if plugin_installed "$m"; then present=yes; break; fi
      done
      IFS="$old_ifs"
      ;;
    env)
      if [ -n "$(eval "printf '%s' \"\${$id:-}\"")" ]; then present=yes; else present=no; fi
      ;;
  esac

  case "$present" in
    yes)     printf '  ok       %s (%s)\n' "$id" "$req" ;;
    unknown) printf '  unknown  %s (%s) — unrecognized presence check "%s"\n' "$id" "$req" "$pres" ;;
    no)
      missing=$((missing + 1))
      printf '  MISSING  %s (%s)\n' "$id" "$req"
      printf '           degrade: %s\n' "$deg"
      printf '           install: %s\n' "$inst"
      ;;
  esac
done < <(manifest_tsv)

if [ "$missing" -gt 0 ]; then
  echo "  ($missing missing — skills fall back; run the install commands above to restore the default path)"
fi
echo "  presence only. Whether the running agent can actually reach these is a"
echo "  separate axis this script cannot check — see 'probe' in skills/dependencies.yaml."

exit 0
