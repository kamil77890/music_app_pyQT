#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

OLLAMA_URL="${LOCAL_AI_OLLAMA_URL:-http://localhost:11434}"
MODEL="${LOCAL_AI_MODEL:-qwen3:1.7b}"

echo "Local AI metadata checker"
echo "========================="

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama CLI not found in PATH."
  echo "Install Ollama from https://ollama.com and ensure 'ollama' is available."
  exit 1
fi

echo "ollama CLI: found"

if curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  echo "Ollama API: reachable at ${OLLAMA_URL}"
else
  echo "Ollama API: not reachable at ${OLLAMA_URL}"
  echo "Run: ollama serve"
  exit 1
fi

if [ -z "$MODEL" ]; then
  echo "LOCAL_AI_MODEL is empty."
  echo "Set LOCAL_AI_MODEL in .env to a locally installed model."
  echo "Example: LOCAL_AI_MODEL=qwen3:1.7b"
  echo "Install: ollama pull qwen3:1.7b"
  echo "This script does not download models automatically."
  exit 1
fi

if ! ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$MODEL"; then
  echo "Model not found locally: ${MODEL}"
  echo "Run: ollama pull qwen3:1.7b"
  echo "This script does not download models automatically."
  exit 1
fi

echo "LOCAL_AI_MODEL: ${MODEL}"
echo "LOCAL_AI_METADATA_ENABLED: ${LOCAL_AI_METADATA_ENABLED:-true}"
echo
echo "Ready. Example dry run:"
echo "  .venv/bin/python scripts/run-local-ai-enrichment.py --dry-run --limit 5 --use-local-ai"
