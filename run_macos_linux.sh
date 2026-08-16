#!/usr/bin/env sh
# Run the static checks before opening a browser: a bad edit should be caught
# here, not by hunting a ClientError halfway through a quest load.
#
# Opens the challenge-mode test page with the opening-skill-gauge dev aid, which
# is what the current work is verified against. Pass --page to open something
# else, e.g.  ./run_macos_linux.sh --page index.html
cd "$(dirname "$0")" || exit 1
./tools/verify_all.sh || {
	echo
	echo "静态检查未通过，未启动服务。"
	echo "修好上面的问题后重试，或直接运行 python3 ./run_server_nocache.py 跳过检查。"
	exit 1
}
echo
exec python3 ./run_server_nocache.py "$@"
