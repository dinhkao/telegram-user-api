#!/bin/zsh
# Quick one-shot pi command with Fireworks API key
# Usage: ./pi-fireworks.sh "your question here"
export FIREWORKS_API_KEY=fw_GKVCJweZbamTCgKcVnbpts && pi -p --model fireworks/accounts/fireworks/routers/kimi-k2p5-turbo "$@"
