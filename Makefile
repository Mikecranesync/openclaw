.PHONY: install dev test lint run deploy

install:
	python3 -m venv .venv
	.venv/bin/pip install -e .

dev:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest tests/ -v

lint:
	.venv/bin/ruff check openclaw/
	.venv/bin/ruff format --check openclaw/

run:
	.venv/bin/python -m openclaw

deploy:
	sudo cp deploy/openclaw.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable openclaw
	sudo systemctl restart openclaw
