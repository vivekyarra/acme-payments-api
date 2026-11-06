#!/usr/bin/env bash
# Create the 10 demo issues from issues.yaml on a GitHub repo, in order,
# so they get numbers #1..#10.
#
#   scripts/create_issues.sh [--dry-run] <owner>/<repo>
#
# Needs: gh (logged in), and one of: python with PyYAML, uv, or yq.
# Only title, body and labels are sent; skills/paths/est_hours stay local.
set -euo pipefail

usage() {
  echo "usage: $0 [--dry-run] <owner>/<repo>" >&2
  exit 2
}

DRY_RUN=0
REPO=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage ;;
    -*) echo "unknown flag: $arg" >&2; usage ;;
    *) [[ -z "$REPO" ]] || usage; REPO="$arg" ;;
  esac
done
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || usage

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISSUES="$HERE/issues.yaml"
[[ -f "$ISSUES" ]] || { echo "missing $ISSUES" >&2; exit 1; }

# --- pick a Python (python3 first; on Windows "python3" may be a stub) ---
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' >/dev/null 2>&1; then
    PY="$cand"; break
  fi
done

# Prints one NUL-separated record per issue: title, body, labels (comma-separated).
EMIT='
import json, sys
def emit(issues):
    for i in issues:
        for field in (i["title"], i["body"], ",".join(i.get("labels") or [])):
            sys.stdout.write(field + "\0")
try:
    import yaml
    emit(yaml.safe_load(open(sys.argv[1], encoding="utf-8")))
except ImportError:
    emit(json.load(sys.stdin))
'

records() {
  if [[ -n "$PY" ]] && "$PY" -c 'import yaml' >/dev/null 2>&1; then
    "$PY" -c "$EMIT" "$ISSUES"
  elif command -v uv >/dev/null 2>&1; then
    uv run --quiet --no-project --with pyyaml python -c "$EMIT" "$ISSUES"
  elif command -v yq >/dev/null 2>&1 && [[ -n "$PY" ]]; then
    yq -o=json '.' "$ISSUES" | "$PY" -c "$EMIT" /dev/null
  else
    echo "need python with PyYAML, uv, or yq (plus python) to read issues.yaml" >&2
    exit 1
  fi
}

if [[ $DRY_RUN -eq 0 ]]; then
  command -v gh >/dev/null || { echo "gh is not installed" >&2; exit 1; }
  existing="$(gh issue list --repo "$REPO" --state all --limit 1 --json number --jq 'length')"
  if [[ "$existing" != "0" ]]; then
    echo "warning: $REPO already has issues, so numbers will not be #1..#10." >&2
  fi
fi

n=0
while IFS= read -r -d '' title && IFS= read -r -d '' body && IFS= read -r -d '' labels; do
  n=$((n + 1))
  cmd=(gh issue create --repo "$REPO" --title "$title" --body "$body")
  if [[ -n "$labels" ]]; then
    IFS=',' read -r -a label_list <<<"$labels"
    for l in "${label_list[@]}"; do cmd+=(--label "$l"); done
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '# issue #%d\n' "$n"
    printf 'gh issue create --repo %q --title %q --body <%d chars>' "$REPO" "$title" "${#body}"
    [[ -z "$labels" ]] || printf ' --label %q' "$labels"
    printf '\n'
  else
    echo "creating #$n: $title"
    "${cmd[@]}"
  fi
done < <(records)

[[ $n -gt 0 ]] || { echo "no issues read from $ISSUES" >&2; exit 1; }
echo "done: $n issues $([[ $DRY_RUN -eq 1 ]] && echo '(dry run, nothing created)' || echo "created on $REPO")"
