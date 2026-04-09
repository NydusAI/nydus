# Nydus Examples

| Example | Directive | External deps | Deterministic? |
|---------|-----------|---------------|----------------|
| 01-redact-travel-agent | REDACT (gitleaks + Presidio) | gitleaks, spaCy model | Yes |
| 02-add-company-chatbot | FROM + ADD | None | Yes |
| 03-llm-refinement-compress | LLM refinement | OpenAI API key | Reproducible, not identical |

All examples use **OpenClaw → OpenClaw** (same platform, no cross-platform hatch).

## Quick start

    cd examples/01-redact-travel-agent
    ./run.sh

## Prerequisites

- pynydus installed: `uv pip install -e .` from repo root
- gitleaks v8+ (Example 01): https://github.com/gitleaks/gitleaks
- spaCy model (Example 01): `python -m spacy download en_core_web_lg`
- LLM API key (Example 03): `export NYDUS_LLM_TYPE=openai/gpt-4o`
