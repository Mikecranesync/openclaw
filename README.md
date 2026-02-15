# OpenClaw 1.0

**Industrial AI gateway** — intent-aware LLM routing for factory floor diagnostics.

OpenClaw receives messages from any channel (Telegram, WhatsApp, HTTP, WebSocket), classifies intent, routes through the right LLM provider, pulls live PLC data, and returns actionable diagnosis to the technician's phone in under 3 seconds.

## Quick Start

```bash
git clone https://github.com/Mikecranesync/openclaw.git
cd openclaw
make install
cp openclaw.yaml.example openclaw.yaml
# Edit openclaw.yaml with your settings
# Set env vars: GROQ_API_KEY, TELEGRAM_BOT_TOKEN
make run
```

## Architecture

```
Telegram/WhatsApp/HTTP → Channel Gateway → Intent Classifier → Skill Router
                                                                    ↓
                                            DiagnoseSkill ← LLM Router (Groq/Claude/Gemini)
                                                ↓
                                          Matrix API (live PLC tags)
                                                ↓
                                      Rule-based fault detection + LLM analysis
                                                ↓
                                         Technician gets answer in <3s
```

## LLM Routing

| Intent | Primary | Fallback | Why |
|--------|---------|----------|-----|
| diagnose | Groq (Llama 3.3 70B) | NVIDIA, OpenAI | Speed — technician is waiting |
| photo | Gemini (vision) | OpenAI (GPT-4o) | Vision required |
| work_order | Claude | OpenAI | Complex structured output |
| chat | Groq | OpenAI | General, speed preferred |

## Skills

- **diagnose** — Pull live PLC tags, run fault detection, ask LLM for diagnosis
- **status** — Show current tag values
- **photo** — Analyze equipment photos with Gemini Vision
- **work_order** — Create CMMS work orders from natural language
- **admin** — Health checks, budget tracking, connector status
- **chat** — General conversation with factory context

## API

```bash
# Health check
curl http://localhost:8340/health

# Send a message
curl -X POST http://localhost:8340/api/v1/message \
  -H "Content-Type: application/json" \
  -d '{"text": "Why is conveyor 1 stopped?"}'

# Direct diagnosis
curl -X POST http://localhost:8340/api/v1/diagnose \
  -H "Content-Type: application/json" \
  -d '{"text": "What is wrong with the motor?"}'
```

## Deploy

```bash
# On VPS
curl -sSL https://raw.githubusercontent.com/Mikecranesync/openclaw/main/deploy/install.sh | bash
```

## License

MIT
