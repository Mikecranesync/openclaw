# OpenClaw — CLAUDE.md

## Git Workflow (MANDATORY)

1. **Never edit code without committing** — no orphaned changes on the VPS
2. **Branch from main** for features: `feat/<name>`, fixes: `fix/<name>`
3. **Commit message format**: `feat(scope):` / `fix(scope):` / `chore(scope):` / `ops:`
4. **Show diff before committing** — always review with Mike
5. **Push to remote + open PR** — no merging without approval
6. **No direct push to main** unless explicitly approved

## Ops Documentation (MANDATORY)

For every code/config change:
1. Write a brief note to `/tmp/ops-buffer.md` during work
2. After code is ready, flush the buffer:
   - Create/update workflow in `docs/ops/workflows/` if new operation
   - Add trace in `docs/ops/traces/` for the activity
3. If new dependencies are added: note them in the commit message AND the trace

## VPS-Specific Rules

- OpenClaw runs as systemd service via Doppler
- After editing code: `systemctl restart openclaw`
- Verify after restart: `journalctl -u openclaw -n 15 --no-pager`
- Health check: `curl -s http://localhost:8340/`
- Budget check: `curl -s http://localhost:8340/budget`
