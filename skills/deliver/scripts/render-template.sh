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
: "${ITER_USED:?--iter-used is required}"
: "${ITER_BUDGET:?--iter-budget is required}"

mkdir -p "$(dirname "$OUTPUT")"

# Render iteration placeholders first, then insert the objective from the
# code-generated OBJECTIVE_HTML file. This prevents a user objective that
# contains literal strings like "{{ iter_used }}" from being substituted as a
# trusted template placeholder after insertion.
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
{
  gsub(/\{\{ iter_used \}\}/, iter_used)
  gsub(/\{\{ iter_budget \}\}/, iter_budget)
  gsub(/\{\{ iter_remaining \}\}/, iter_remaining)
  while ((at = index($0, "{{ objective }}")) > 0) {
    $0 = substr($0, 1, at - 1) objective substr($0, at + 15)
  }
  print
}
' "$TEMPLATE" > "$OUTPUT"
