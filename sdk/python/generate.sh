#!/usr/bin/env bash
# Regenerate typed Python client from live OpenAPI spec.
# Requires: pip install openapi-python-client
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_URL="${SPEC_URL:-http://localhost:8000/api-catalog/openapi.json}"
OUT_DIR="${SCRIPT_DIR}/uzassets_sdk_generated"

echo "Generating Python client from ${SPEC_URL}…"
rm -rf "${OUT_DIR}"
openapi-python-client generate --url "${SPEC_URL}" --output-path "${OUT_DIR}"
echo "✓ Generated to ${OUT_DIR}"
