#!/usr/bin/env bash
# Every static check this project has, in one command.
#
#   ./tools/verify_all.sh
#
# What it does NOT cover: anything that needs the game actually running. The
# browser regression - tutorial boots, challenge reaches all four quests, AUTO
# works, battles finish, no ClientError in the console - stays manual.
set -uo pipefail
cd "$(dirname "$0")/.."

status=0
run() {
	echo
	echo "=============================================================="
	echo "== $1"
	echo "=============================================================="
	shift
	"$@" || status=1
}

run "tree vs the pristine archive" python3 tools/verify_tree.py
run "patch table and runtime hooks" node tools/verify_patches.mjs
run "orderedmap lossless round-trip" bash -c \
	'python3 tools/orderedmap.py roundtrip $(find WFTest/assets -name "*.orderedmap" | sort)'
run "browser reader vs python reader" node tools/verify_orderedmap_js.mjs

echo
if [ "$status" -ne 0 ]; then
	echo "FAILED: at least one check did not pass"
else
	echo "all static checks passed - browser regression is still manual"
fi
exit "$status"
