#!/usr/bin/env bash
# PreToolUse(Bash): blocks any command that invokes git or gh to change repository state.
#
# A short allow-list of read-only commands is permitted -- but only as a single, unchained
# command (no ; & | ` $( anywhere in it), so a read-only command can't be used to smuggle a
# mutating one alongside it. Ambiguous subcommands that have destructive flag forms
# (git branch -D, gh pr merge) require an exact match with nothing trailing; safe ones
# (log/diff/show) may take trailing arguments.
#
# THIS IS THE HOOK THAT MAKES BROAD PERMISSIONS SAFE. The one genuinely irreversible,
# outward-facing verb is blocked here, so everything else can be auto-approved in
# settings.json without you becoming the gate on `ls`.
set -uo pipefail

deny() {
  jq -n --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

if ! CMD=$(jq -r '.tool_input.command // empty' 2>/dev/null); then
  deny "Blocked: .claude/hooks/no-git.sh could not parse the hook input, so it cannot confirm this command is not a mutating git or gh invocation."
fi

TRIMMED="$(printf '%s' "$CMD" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"

GIT_EXACT_ALLOWED='^git (status|branch)$'
GIT_PREFIX_ALLOWED='^git (log|diff|show|rev-parse|remote -v)([[:space:]].*)?$'
GH_EXACT_ALLOWED='^gh status$'
GH_PREFIX_ALLOWED='^gh (pr view|pr list|pr diff|issue view|issue list|repo view|run list|run view)([[:space:]].*)?$'

if ! printf '%s' "$CMD" | grep -Eq '[;&|`]|\$\('; then
  if printf '%s' "$TRIMMED" | grep -Eq "$GIT_EXACT_ALLOWED|$GIT_PREFIX_ALLOWED|$GH_EXACT_ALLOWED|$GH_PREFIX_ALLOWED"; then
    exit 0   # allow: a single, unchained, read-only command
  fi
fi

if printf '%s' "$CMD" | grep -Eq '(^|[[:space:];&|(`])(git|gh)([[:space:];&|)]|$)'; then
  deny "Blocked by .claude/hooks/no-git.sh: only a short allow-list of single, unchained read-only commands is permitted (git status/branch/log/diff/show/rev-parse/remote -v; gh status/pr view/pr list/pr diff/issue view/issue list/repo view/run list/run view). Everything else -- the owner performs personally. Tell the owner the exact command you wanted, and let them run it."
fi

exit 0   # allow
