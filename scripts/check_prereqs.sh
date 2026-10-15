#!/usr/bin/env bash
# Verify the host has every prerequisite listed in PREREQUISITES.md.
#
# Prints a per-tool line and a final summary. Exit 0 only if everything is OK.

set -u

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
RESET=$'\033[0m'

fail=0
warn=0

check() {
  # check NAME MIN_VERSION COMMAND
  local name="$1"
  local min="$2"
  local cmd="$3"

  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf '  %s[fail]%s %-18s not installed\n' "$RED" "$RESET" "$name"
    fail=$((fail+1))
    return
  fi

  local ver
  case "$cmd" in
    rustc)    ver="$(rustc --version 2>/dev/null | awk '{print $2}')" ;;
    cargo)    ver="$(cargo --version 2>/dev/null | awk '{print $2}')" ;;
    python3)  ver="$(python3 --version 2>/dev/null | awk '{print $2}')" ;;
    uv)       ver="$(uv --version 2>/dev/null | awk '{print $2}')" ;;
    node)     ver="$(node --version 2>/dev/null | sed 's/^v//')" ;;
    pnpm)     ver="$(pnpm --version 2>/dev/null)" ;;
    git)      ver="$(git --version 2>/dev/null | awk '{print $3}')" ;;
    ollama)   ver="$(ollama --version 2>/dev/null | awk '{print $NF}')" ;;
    gh)       ver="$(gh --version 2>/dev/null | head -n1 | awk '{print $3}')" ;;
    make)     ver="$(make --version 2>/dev/null | head -n1 | awk '{print $3}')" ;;
    *)        ver="?" ;;
  esac

  printf '  %s[ ok ]%s %-18s %s\n' "$GREEN" "$RESET" "$name" "$ver"
}

check_optional() {
  local name="$1"
  local cmd="$2"

  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf '  %s[warn]%s %-18s optional, not installed\n' "$YELLOW" "$RESET" "$name"
    warn=$((warn+1))
    return
  fi
  printf '  %s[ ok ]%s %-18s found\n' "$GREEN" "$RESET" "$name"
}

echo "Arikizu prerequisite check"
echo
echo "Required:"
check "Rust (rustc)"    1.80 rustc
check "Rust (cargo)"    1.80 cargo
check "Python 3.11"     3.11 python3
check "uv"              0.4  uv
check "Node.js 20"      20   node
check "pnpm"            9    pnpm
check "git"             2    git
check "make"            3    make

echo
echo "Recommended:"
check_optional "Ollama"       ollama
check_optional "gh CLI"       gh

echo
echo "Build tools:"
if command -v cc >/dev/null 2>&1; then
  printf '  %s[ ok ]%s %-18s %s\n' "$GREEN" "$RESET" "C compiler" "$(cc --version 2>/dev/null | head -n1)"
else
  printf '  %s[fail]%s %-18s not installed\n' "$RED" "$RESET" "C compiler"
  fail=$((fail+1))
fi

echo
echo "Platform:"
case "$(uname -s)" in
  Linux)
    if [ -f /etc/nv_tegra_release ]; then
      printf '  %s[info]%s running on NVIDIA Jetson (%s)\n' "$GREEN" "$RESET" \
        "$(head -n1 /etc/nv_tegra_release | tr -d '\n')"
    fi
    if command -v nvidia-smi >/dev/null 2>&1; then
      printf '  %s[info]%s NVIDIA GPU detected\n' "$GREEN" "$RESET"
    fi
    ;;
  Darwin)
    printf '  %s[info]%s macOS build; GPU acceleration available via Metal\n' "$GREEN" "$RESET"
    ;;
esac

echo
if [ "$fail" -gt 0 ]; then
  echo "${RED}${fail} required tool(s) missing. See PREREQUISITES.md.${RESET}"
  exit 1
fi
if [ "$warn" -gt 0 ]; then
  echo "${YELLOW}all required tools found; ${warn} optional tool(s) missing.${RESET}"
else
  echo "${GREEN}all prerequisites satisfied.${RESET}"
fi
exit 0
