.PHONY: install test run run-server run-unified run-mcp clean docker-build deploy

install:
	@pip install -q -r requirements.txt 2>/dev/null || true

test:
	@python hello_rewards.py

run:
	@python hello_rewards.py

run-server:
	@python -c "import uvicorn; from server import app; uvicorn.run(app, host='0.0.0.0', port=8000, log_level='info')"

run-unified:
	@python unified_hello.py

run-mcp:
	@python mcp_stdio.py

clean:
	rm -rf __pycache__ .pytest_cache

docker-build:
	docker build --platform linux/amd64 -t sovsrc-si-core:local .

deploy:
	npm install --no-audit --no-fund
	npx wrangler deploy
