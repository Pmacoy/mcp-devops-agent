.PHONY: install lint typecheck test ci stack-up stack-down demo-readonly demo-operator demo clean

install:
	pip install -r requirements-dev.txt

lint:
	ruff check .

typecheck:
	mypy mcp_server demo tests

test:
	pytest -v

ci: lint typecheck test

# Builds and starts the target stack (api, worker, redis) that the MCP
# server inspects/remediates. Waits for redis and api's own healthchecks;
# worker starts healthy too -- the incident is triggered separately by
# demo/scenario.py, not by anything here.
stack-up:
	docker compose -f target-stack/docker-compose.yml up -d --build --wait

stack-down:
	docker compose -f target-stack/docker-compose.yml down -v

# Runs the scripted incident demo against an already-running stack
# (`make stack-up` first). readonly: the agent finds the problem, reads
# the logs, and is refused when it tries to fix it. operator: same
# investigation, but the restart is allowed and the worker recovers.
demo-readonly:
	python -m demo.run_incident_demo --role readonly

demo-operator:
	python -m demo.run_incident_demo --role operator

# Runs both roles back to back against a fresh stack -- the same thing
# .github/workflows/ci.yml's integration job does, useful for trying
# locally before pushing.
demo: stack-up
	$(MAKE) demo-readonly || true
	$(MAKE) stack-down
	$(MAKE) stack-up
	$(MAKE) demo-operator
	$(MAKE) stack-down

clean:
	find . -name '__pycache__' -type d -exec rm -rf {} +
	rm -rf .mypy_cache .ruff_cache .pytest_cache var
