install:
	uv sync
	cd frontend && npm install

# ---- Sugam UI (the custom React front end) --------------------------------- #
# Dev = two processes, run in two terminals:
#   make ui-api   -> agent + API on :8000
#   make ui-web   -> Vite UI on :5173, hot reload, proxies API calls to :8000
ui-api:
	uv run python -m app.server

ui-web:
	cd frontend && npm run dev

ui-build:
	cd frontend && npm run build

# Prod = one process. Build the SPA, then serve UI + API together on :8000.
# No Node at runtime.
ui:
	cd frontend && npm run build
	uv run python -m app.server

# ---- ADK built-ins --------------------------------------------------------- #
playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run adk run app

test:
	uv run pytest tests/
