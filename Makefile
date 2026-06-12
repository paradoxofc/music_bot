.PHONY: run.bot test import-users

run.bot:
	python3 -m telegram_bot

test:
	bash scripts/run-tests.sh

import-users:
	python3 scripts/import_legacy_users.py
