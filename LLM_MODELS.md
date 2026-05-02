# LLM Model Configuration

## Primary Provider: OpenRouter

All LLM calls route through OpenRouter (https://openrouter.ai/api/v1).

### Model Selection

- **Generation**: `openai/gpt-oss-120b:free`
  - Used for test generation and code synthesis
  
- **Reasoning**: `openai/gpt-oss-120b:free` with high-reasoning prompt mode
  - Used for analysis, debugging, and complex decision-making
  
- **Fallback (Paid)**: `anthropic/claude-sonnet-4.6`
  - Activated when paid fallback is enabled in settings
  - Higher accuracy for edge cases

### Configuration

Set in `.env`:
```
OPENROUTER_API_KEY=<your-key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

See `src/config/settings.py` for the Settings class that loads these variables.
