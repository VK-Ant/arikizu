#!/usr/bin/env bash
# Run every Pi e2e test in order; exit non-zero on any FAIL.

set -u
cd "$(dirname "$0")/../.."

RED=$'\033[31m'; GREEN=$'\033[32m'; RESET=$'\033[0m'
FAIL=0

echo "== 1. probe =="
python3 demo/raspberrypi/probe.py || FAIL=1

echo
echo "== 2. vision_pi =="
python3 demo/raspberrypi/vision_pi.py "$@" || FAIL=1

echo
echo "== 3. audio_pi =="
python3 demo/raspberrypi/audio_pi.py "$@" || FAIL=1

echo
if [ $FAIL -eq 0 ]; then
  echo "${GREEN}all pi e2e checks returned without FAIL${RESET}"
else
  echo "${RED}one or more checks returned FAIL (see above)${RESET}"
fi
exit $FAIL
