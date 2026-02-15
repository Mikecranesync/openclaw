# OpenClaw Resume Prompt

## What Was Done

### 1. Bug Fixes (committed: `334f224`)
Fixed 6 bugs in OpenClaw 1.0:
- Gemini provider: wrapped sync calls in `asyncio.to_thread()`, added token tracking
- NVIDIA provider: added missing `temperature` parameter to API request
- PLC connector: changed to `await self._client.close()` with try/except
- WhatsApp adapter: added error handling on `send()` so failures are logged
- WorkOrderSkill: moved `import json` to top, added warning log on JSON parse failure
- LLM router: included attempted provider names in exhaustion error

### 2. pyproject.toml fix (committed: `c087731`)
Added `[tool.setuptools.packages.find]` with `include = ["openclaw*"]` to fix flat-layout build error.

### 3. OpenRouter + Perplexity + Multi-Bot (committed: `8f324ef`)
Added OpenRouter as 6th LLM provider and Perplexity Sonar as 7th builtin skill:

**New files:**
- `openclaw/llm/providers/openrouter.py` — OpenRouter provider (AsyncOpenAI with custom base_url)
- `openclaw/skills/builtin/search.py` — Perplexity web search skill (Intent.SEARCH)
- `deploy/openclaw-personal.service` — Systemd + Doppler (port 8340)
- `deploy/openclaw-business.service` — Systemd + Doppler (port 8341)
- `deploy/openclaw-dev.service` — Systemd + Doppler (port 8342)

**Modified files:**
- `types.py` — Added `Intent.SEARCH`
- `intent.py` — Added `/search` command + keyword patterns
- `config.py` — Added openrouter + perplexity config fields
- `app.py` — Wired OpenRouter provider + budget
- `router.py` — OpenRouter primary for DIAGNOSE and WORK_ORDER
- `registry.py` — Registered SearchSkill
- `openclaw.yaml.example` — Added config examples
- `tests/` — Added 3 new tests (11 total, all passing)

### 4. Deployment to Jarvis (in progress)
- Doppler CLI installed and authenticated locally (WSL) as Mike
- API keys stored in Doppler project `voltron`, config `dev`
- Available keys: `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`
- Doppler CLI already authenticated on Jarvis VPS (`Voltronmatrix`)
- Deploy script was run on Jarvis using `doppler run --project voltron --config dev`
- **Status: needs debugging** — service not responding on port 8340 from Tailscale

## Current State

- **Branch:** `main` at commit `8f324ef`
- **Repo:** `Mikecranesync/openclaw` (pushed)
- **Tests:** 11/11 passing locally
- **Jarvis VPS:** 100.68.120.99 (Tailscale: `factorylm-prod`)
- **SSH:** Not working from WSL (key not authorized). User SSHs from another terminal.
- **Doppler:** Authenticated locally at `~/bin/doppler`. Project `voltron`, config `dev`.

## Next Steps

1. Debug why OpenClaw isn't responding on Jarvis (`systemctl status openclaw`, `journalctl -u openclaw -n 30`)
2. Likely issues: Python version mismatch (script uses `python3`, Jarvis may need `python3.11`), or missing `pyproject.toml` setuptools fix not yet on remote
3. Once first bot works, deploy business + dev instances on ports 8341/8342
4. Add `OPENROUTER_API_KEY` and `PERPLEXITY_API_KEY` to Doppler `voltron` project
5. Create 3 Telegram bots via @BotFather for personal/business/dev

## Key Commands

```bash
# Check Jarvis health from anywhere on Tailscale
curl http://100.68.120.99:8340/health

# On Jarvis — check logs
journalctl -u openclaw -f

# On Jarvis — restart
systemctl restart openclaw

# Local — run tests
cd /mnt/c/Users/hharp/Desktop/openclaw && .venv/bin/python -m pytest tests/ -v

# Local — Doppler
~/bin/doppler secrets --project voltron --config dev
```
