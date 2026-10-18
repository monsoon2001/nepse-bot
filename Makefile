.PHONY: setup test lint run format

setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
	python -m pytest

lint:
	ruff check .

format:
	ruff format .

run:
	python -m nepse_sense run-bot
