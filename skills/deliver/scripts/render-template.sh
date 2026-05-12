#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  render-template.sh <template> <objective-html-file> <output> \
    --iter-used <n> --iter-budget <n> [--iter-remaining <n>]
EOF
}

if [ "$#" -lt 7 ]; then
  usage
  exit 2
fi

TEMPLATE=$1
OBJECTIVE_HTML_FILE=$2
OUTPUT=$3
shift 3

ITER_USED=
ITER_BUDGET=
ITER_REMAINING=
ITER_REMAINING_SEEN=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --iter-used)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      ITER_USED=$2
      shift 2
      ;;
    --iter-budget)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      ITER_BUDGET=$2
      shift 2
      ;;
    --iter-remaining)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      ITER_REMAINING_SEEN=1
      ITER_REMAINING=$2
      shift 2
      ;;
    *)
      echo "ERROR: unknown render-template argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

[ -f "$TEMPLATE" ] || { echo "ERROR: template not found at $TEMPLATE" >&2; exit 1; }
[ -f "$OBJECTIVE_HTML_FILE" ] || { echo "ERROR: objective HTML file not found at $OBJECTIVE_HTML_FILE" >&2; exit 1; }
[ -n "$ITER_USED" ] || { echo "ERROR: --iter-used is required" >&2; exit 2; }
[ -n "$ITER_BUDGET" ] || { echo "ERROR: --iter-budget is required" >&2; exit 2; }
case "$ITER_USED" in
  *[!0-9]*) echo "ERROR: --iter-used must be a non-negative integer" >&2; exit 2 ;;
esac
case "$ITER_BUDGET" in
  *[!0-9]*) echo "ERROR: --iter-budget must be a non-negative integer" >&2; exit 2 ;;
esac
if [ "$ITER_REMAINING_SEEN" -eq 1 ]; then
  [ -n "$ITER_REMAINING" ] || { echo "ERROR: --iter-remaining must be a non-negative integer" >&2; exit 2; }
  case "$ITER_REMAINING" in
    *[!0-9]*) echo "ERROR: --iter-remaining must be a non-negative integer" >&2; exit 2 ;;
  esac
fi
if [ "$ITER_REMAINING_SEEN" -eq 0 ] && grep -qF '{{ iter_remaining }}' "$TEMPLATE"; then
  echo "ERROR: template uses {{ iter_remaining }} but --iter-remaining was not provided" >&2
  exit 2
fi

mkdir -p "$(dirname "$OUTPUT")"

# Render iteration placeholders first, then insert the objective from the
# code-generated OBJECTIVE_HTML file. Every placeholder uses split/rejoin rather
# than awk gsub replacement strings, so literal "&" values are not expanded to
# the matched placeholder text.
awk \
  -v objective_file="$OBJECTIVE_HTML_FILE" \
  -v iter_used="$ITER_USED" \
  -v iter_budget="$ITER_BUDGET" \
  -v iter_remaining="$ITER_REMAINING" '
BEGIN {
  sep = ""
  while ((getline line < objective_file) > 0) {
    objective = objective sep line
    sep = "\n"
  }
  close(objective_file)
}
function replace_all(text, pattern, replacement, parts, n, i, rendered) {
  n = split(text, parts, pattern)
  if (n == 1) {
    return text
  }
  rendered = parts[1]
  for (i = 2; i <= n; i++) {
    rendered = rendered replacement parts[i]
  }
  return rendered
}
{
  $0 = replace_all($0, "\\{\\{ iter_used \\}\\}", iter_used)
  $0 = replace_all($0, "\\{\\{ iter_budget \\}\\}", iter_budget)
  $0 = replace_all($0, "\\{\\{ iter_remaining \\}\\}", iter_remaining)
  $0 = replace_all($0, "\\{\\{ objective \\}\\}", objective)
  print
}
' "$TEMPLATE" > "$OUTPUT"
