#!/bin/bash
set -e
cd /opt/openclaw

if doppler secrets download --no-file --format env --project openclaw --config dev_bot > .env.tmp 2>/dev/null; then
    mv .env.tmp .env
    chmod 600 .env
    echo "$(date): Synced Doppler -> .env" >> /var/log/openclaw-doppler.log
else
    echo "$(date): Doppler sync failed, .env unchanged" >> /var/log/openclaw-doppler.log
    rm -f .env.tmp
    exit 1
fi
