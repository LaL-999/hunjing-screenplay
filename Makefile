# ============================================================
# 浑晶 · 剧创态 — Makefile(跨平台)
# ============================================================

.PHONY: help install dev dev-backend dev-frontend test test-backend clean

help:
	@echo "Targets:"
	@echo "  install        - 安装前后端依赖"
	@echo "  dev            - 启动 backend + frontend(需要 2 个 shell)"
	@echo "  dev-backend    - 仅启动 backend (port 8002)"
	@echo "  dev-frontend   - 仅启动 frontend (port 5174)"
	@echo "  test           - 跑全部测试"
	@echo "  test-backend   - 跑 backend pytest"
	@echo "  clean          - 清理 __pycache__ / node_modules"

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8002

dev-frontend:
	cd frontend && npm run dev

dev:
	@echo "[ERROR] 'make dev' needs 2 shells. Run 'make dev-backend' and 'make dev-frontend' separately."
	@echo "Windows users: just double-click start-dev.bat"

test: test-backend

test-backend:
	cd backend && pytest tests/ -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf frontend/node_modules frontend/dist
