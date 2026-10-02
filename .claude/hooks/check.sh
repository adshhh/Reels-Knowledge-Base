#!/usr/bin/env bash
# PostToolUse(Write|Edit): formats, type-checks and tests after every source edit, BLOCKING
# (exit 2) on failure so the agent fixes it before moving on -- the machine owns the boring
# failure modes, so a non-code-reading reviewer can trust "done". DUAL STACK (Python + the
# JS/TS branch below): the kit's original version exited before running either check if
# package.json was absent, silently passing every Python edit. Both branches are real here,
# and skip cleanly (not as a failure) when a tool or package.json is genuinely missing.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

cd "$CLAUDE_PROJECT_DIR" || exit 0

# Prefer the project venv's tools over anything global.
if [ -d ".venv/bin" ]; then
  export PATH="$CLAUDE_PROJECT_DIR/.venv/bin:$PATH"
fi

FAILURES=""

record_failure() {
  FAILURES="${FAILURES}
- $1 failed:
$2"
}

# ---------------------------------------------------------------- python branch

# Parallel builders (DESIGN_RATIONALE §4) each own one area, e.g. src/reelkb/serve + tests/serve.
# An edit inside an area checks that area plus the shared contract, so one builder's
# half-finished file can't block another's. Edits anywhere else (contract, conftest, config)
# check everything. The lead runs the full suite at every integration point.
AREA=""
case "$FILE" in
  "$CLAUDE_PROJECT_DIR"/src/reelkb/*/*) AREA="${FILE#"$CLAUDE_PROJECT_DIR"/src/reelkb/}"; AREA="${AREA%%/*}" ;;
  "$CLAUDE_PROJECT_DIR"/tests/*/*) AREA="${FILE#"$CLAUDE_PROJECT_DIR"/tests/}"; AREA="${AREA%%/*}" ;;
esac
case "$AREA" in contract|testing) AREA="" ;; esac

MYPY_TARGETS=(.)
PYTEST_TARGETS=()
if [ -n "$AREA" ]; then
  MYPY_TARGETS=(src/reelkb/contract src/reelkb/testing)
  [ -d "src/reelkb/$AREA" ] && MYPY_TARGETS+=("src/reelkb/$AREA")
  [ -d "tests/$AREA" ] && MYPY_TARGETS+=("tests/$AREA")
  PYTEST_TARGETS=(tests/contract tests/test_guards.py)
  [ -d "tests/$AREA" ] && PYTEST_TARGETS+=("tests/$AREA")
fi

run_python_checks() {
  local output

  # Format first, so the agent never fights the formatter over whitespace.
  if command -v ruff >/dev/null 2>&1; then
    if ! output=$(ruff format --force-exclude "$FILE" 2>&1); then
      record_failure "ruff format" "$output"
    fi
    if ! output=$(ruff check --force-exclude --fix "$FILE" 2>&1); then
      record_failure "ruff check" "$output"
    fi
  fi

  # Typecheck the whole project, not just this file -- an edit here breaks callers there.
  if command -v pyright >/dev/null 2>&1; then
    if ! output=$(pyright 2>&1); then
      record_failure "pyright" "$output"
    fi
  elif command -v mypy >/dev/null 2>&1; then
    if ! output=$(mypy "${MYPY_TARGETS[@]}" 2>&1); then
      record_failure "mypy" "$output"
    fi
  fi

  # pytest exit code 5 == "no tests collected", which is a normal state early on.
  if command -v pytest >/dev/null 2>&1; then
    output=$(pytest -q --no-header ${PYTEST_TARGETS[@]+"${PYTEST_TARGETS[@]}"} 2>&1)
    local code=$?
    if [ $code -ne 0 ] && [ $code -ne 5 ]; then
      record_failure "pytest" "$output"
    fi
  fi
}

# ------------------------------------------------------------- javascript branch

run_npm_script_if_present() {
  local script_name="$1"
  local output
  if jq -e --arg s "$script_name" '.scripts[$s]' package.json >/dev/null 2>&1; then
    if ! output=$(npm run --silent "$script_name" 2>&1); then
      record_failure "npm run $script_name" "$output"
    fi
  fi
}

run_js_checks() {
  [ -f package.json ] || return 0
  run_npm_script_if_present "format"
  run_npm_script_if_present "typecheck"
  run_npm_script_if_present "test"
}

# ---------------------------------------------------------------------- dispatch

case "$FILE" in
  *.py|pyproject.toml)
    run_python_checks
    ;;
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|package.json|tsconfig.json)
    run_js_checks
    ;;
  *)
    exit 0   # docs, images, lockfiles, fixtures -- nothing to check
    ;;
esac

if [ -n "$FAILURES" ]; then
  echo "Post-edit checks failed on $FILE:$FAILURES" >&2
  exit 2
fi

exit 0
