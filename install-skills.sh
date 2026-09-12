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

# Link every top-level entry under skills/: the project-* skill dirs, SKILL-CONFIG.md,
# the _shared/ reference tree, and dependencies.yaml. The last two are not skills, but
# the skills address them at ~/.claude/skills/..., so they have to land there too.
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
      # A block scalar has no value on this line; its body would be dropped
      # silently, so refuse the manifest instead of reporting a truncated one.
      if (v == ">" || v == "|" || v == ">-" || v == "|-") {
        print "  ERROR: skills/dependencies.yaml uses a YAML block scalar (" v ") at:" > "/dev/stderr"
        print "         " line > "/dev/stderr"
        print "         This reader is scalar-only and would drop the body silently." > "/dev/stderr"
        exit 1
      }
      if (v ~ /^"/) {                      # quoted: take the quoted span verbatim
        sub(/^"/, "", v)
        sub(/"[[:space:]]*(#.*)?$/, "", v)
      } else {                             # bare: a trailing # starts a comment
        sub(/[[:space:]]+#.*$/, "", v)
        sub(/[[:space:]]+$/, "", v)
      }
      return v
    }
    function flush() {
      if (id != "") { printf "%s\037%s\037%s\037%s\037%s\037%s\n", id, req, pres, inst, memb, deg; n++ }
      id = ""; req = ""; pres = ""; inst = ""; memb = ""; deg = ""
    }
    /^[[:space:]]*- id:/          { flush(); id   = val($0); next }
    /^[[:space:]]*requirement:/   { req  = val($0); next }
    /^[[:space:]]*presence:/      { pres = val($0); next }
    /^[[:space:]]*install:/       { inst = val($0); next }
    /^[[:space:]]*members:/       { memb = val($0); next }
    /^[[:space:]]*degrades:/      { deg  = val($0); next }
    END { flush() }
  ' "$MANIFEST"
}

# Is one plugin id present in the plugin database? The database keys them
# verbatim as "<name>@<marketplace>", so an exact-key match needs no JSON parser.
# Match the closing quote and colon too: a bare substring match would let
# "code-review@mk" be satisfied by "code-review@mk-fork".
plugin_installed() {
  grep -qF "\"$1\":" "$PLUGIN_DB"
}

# yes | no | unknown
resolve_presence() {
  local id="$1" pres="$2" memb="$3" m
  case "$pres" in
    installed_plugins)
      plugin_installed "$id" && echo yes || echo no
      ;;
    installed_plugins_any)
      # Any one member satisfies the group; which member is the right one is
      # language-specific, and only the consuming project knows that.
      # `read -ra` splits without globbing — an unquoted `for` would let a
      # member like `*@mk` expand against the invoker's cwd.
      local -a members=()
      IFS=',' read -ra members <<< "$memb"
      for m in "${members[@]}"; do
        m="${m//[[:space:]]/}"
        [ -n "$m" ] || continue
        if plugin_installed "$m"; then echo yes; return; fi
      done
      echo no
      ;;
    env)
      # Indirect expansion, never `eval`: $id comes from a data file, and eval
      # would execute whatever that file says.
      [ -n "${!id:-}" ] && echo yes || echo no
      ;;
    *)
      echo unknown
      ;;
  esac
}

echo
echo "prerequisites (report only — nothing is installed, exit is always 0):"

declared=$(grep -c '^[[:space:]]*- id:' "$MANIFEST" || true)
missing=0
unknown=0
seen=0

while IFS=$'\037' read -r id req pres inst memb deg; do
  [ -n "$id" ] || continue
  seen=$((seen + 1))
  case "$(resolve_presence "$id" "$pres" "$memb")" in
    yes)
      printf '  ok       %s (%s)\n' "$id" "$req"
      ;;
    unknown)
      unknown=$((unknown + 1))
      printf '  unknown  %s (%s) — unrecognized presence check "%s"\n' "$id" "$req" "$pres"
      ;;
    no)
      missing=$((missing + 1))
      printf '  MISSING  %s (%s)\n' "$id" "$req"
      printf '           degrade: %s\n' "$deg"
      printf '           install: %s\n' "$inst"
      ;;
  esac
done < <(manifest_tsv)

# A reader that produced nothing looks exactly like a manifest with nothing
# missing. Compare what the manifest declares against what the reader emitted,
# and say so loudly when they disagree — a reformatted manifest that still
# parses as valid YAML can silently stop matching the awk anchors.
if [ "$seen" -ne "${declared:-0}" ]; then
  echo "  ERROR: manifest declares $declared tool(s) but the reader produced $seen row(s)."
  echo "         The report above is incomplete. Check skills/dependencies.yaml formatting"
  echo "         (flat, scalar-only, two-space indent) against the awk reader in this script."
fi

if [ "$missing" -gt 0 ]; then
  echo "  ($missing missing — skills fall back; run the install commands above to restore the default path)"
fi
if [ "$unknown" -gt 0 ]; then
  echo "  ($unknown with an unrecognized presence check — those were not verified either way)"
fi
echo "  presence only. Whether the running agent can actually reach these is a"
echo "  separate axis this script cannot check — see 'probe' in skills/dependencies.yaml."

exit 0
