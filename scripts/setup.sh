#!/bin/zsh
# One-time setup on the Mac. Safe to re-run: present tools are left alone.
#   scripts/setup.sh             install tools, create config.toml
#   scripts/setup.sh --schedule  also load the every-2-hours launchd check
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f config.toml ]] || { cp config.example.toml config.toml; echo "created config.toml from config.example.toml"; }
uv sync
# Allowlisted tools install quietly; anything else asks on WhatsApp (skipped if WhatsApp isn't set up yet).
uv run research setup || echo "some tools failed to install; see above"

if [[ "${1:-}" == "--schedule" ]]; then
  plist=~/Library/LaunchAgents/com.yash.research-council.plist
  cp launchd/com.yash.research-council.plist "$plist"
  launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "scheduled: research next --ask-first every 2 hours"
fi

missing=()
for k in notion_token wa_token wa_phone_id wa_to relay_url relay_secret; do
  security find-generic-password -s research-council -a "$k" >/dev/null 2>&1 || missing+=("$k")
done
(( ${#missing} )) && echo "Keychain entries still needed: ${missing[*]} (see README)"
agy --version >/dev/null 2>&1 || echo "agy (Antigravity CLI) missing: curl -fsSL https://antigravity.google/cli/install.sh | bash, then run agy once to sign in"
echo "done. Try: uv run research next --dry-run"
