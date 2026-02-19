#!/bin/bash
if ! systemctl is-active --quiet openclaw; then
    echo "ALERT: OpenClaw service is down" | logger -t openclaw-health
    exit 1
fi

if ! DOPPLER_TOKEN=$(grep DOPPLER_TOKEN /etc/systemd/system/openclaw.service | head -1 | sed 's/.*="//;s/"//' ) doppler secrets --project openclaw --config dev_bot >/dev/null 2>&1; then
    echo "WARN: Doppler auth may be failing, .env fallback in use" | logger -t openclaw-health
fi

exit 0
