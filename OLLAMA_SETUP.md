# 🔧 Ollama Integration Setup Guide

This guide explains how to set up and use Ollama (local AI model) with the Web Scraper project as an alternative to Gemini.

## 📋 Prerequisites

1. **Ollama installed**: Download from [ollama.ai](https://ollama.ai)
2. **Mistral model pulled**: Run `ollama pull mistral:7b` (or your preferred model)
3. **Python packages**: `pip install ollama requests`

## 🚀 Quick Start

### 1. Start Ollama Server

Open a terminal and run:
```bash
ollama serve
```

The server will start on `http://localhost:11434` by default.

### 2. Configure Environment Variables

Create or update `.env` file in your project root:

```env
# Choose AI provider: "gemini" or "ollama"
AI_PROVIDER=ollama

# Ollama configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b

# AI parameters
AI_TEMPERATURE=0.3
AI_MAX_TOKENS=4096

# Gemini (optional, if keeping Gemini as backup)
GEMINI_API_KEY=your_key_here
```

### 3. Run Streamlit App

```bash
streamlit run app.py
```

### 4. Select Ollama in UI

In Streamlit sidebar:
- Select **"Ollama"** from AI Provider radio button
- Verify Ollama Server URL matches your `.env`
- Enter the model name (e.g., `mistral:7b`)

## 🔌 Supported Ollama Models

Popular models you can use with Ollama:

| Model | Size | Best For | Speed |
|-------|------|----------|-------|
| `mistral:7b` | 5GB | General purpose, fast | ⚡ Fast |
| `llama2:7b` | 4GB | Balanced, versatile | ⚡ Fast |
| `neural-chat` | 4GB | Chat-focused | ⚡ Fast |
| `mistral:latest` | 5GB | Latest Mistral version | ⚡ Fast |
| `dolphin-mixtral` | 26GB | High quality | 🐢 Slow |
| `orca-mini:3b` | 2GB | Lightweight | ⚡⚡ Very Fast |

Pull a model with:
```bash
ollama pull mistral:7b
ollama pull llama2:7b
ollama pull neural-chat
```

List installed models:
```bash
ollama list
```

## 🔄 How It Works

### Architecture Flow

```
User Input (Streamlit UI)
    ↓
Web Scraper (gets content)
    ↓
AI Provider Selection (Gemini vs Ollama)
    ↓
Content Chunking (if > 25k chars)
    ↓
Ollama/Gemini Analysis
    ↓
Display Results
```

### Key Implementation Details

#### Environment-Based Configuration
```python
# From .env file
ai_provider = os.getenv("AI_PROVIDER", "gemini")  # "gemini" or "ollama"
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ollama_model = os.getenv("OLLAMA_MODEL", "mistral:7b")
temperature = float(os.getenv("AI_TEMPERATURE", "0.3"))
max_tokens = int(os.getenv("AI_MAX_TOKENS", "4096"))
```

#### Factory Pattern for Analyzer Selection
```python
def get_analyzer(provider: str | None = None, **kwargs) -> BaseAnalyzer:
    """Get appropriate analyzer based on provider"""
    provider = provider or os.getenv("AI_PROVIDER", "gemini").lower()
    
    if provider == "ollama":
        return OllamaAnalyzer(**kwargs)
    elif provider == "gemini":
        return GeminiAnalyzer(**kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")
```

#### Ollama Connection Verification
```python
# OllamaAnalyzer validates connection on init
try:
    response = requests.get(f"{base_url}/api/tags", timeout=5)
    response.raise_for_status()
except requests.RequestException:
    raise ConnectionError("Cannot connect to Ollama server")
```

## 📊 Comparison: Gemini vs Ollama

| Feature | Gemini | Ollama |
|---------|--------|--------|
| **Setup** | API key only | Local installation |
| **Cost** | Pay per token | Free (once installed) |
| **Speed** | ~5-10s (network) | ~2-5s (local) |
| **Privacy** | Cloud-based | 100% local, offline |
| **Model Choice** | Limited | Unlimited models |
| **Context Window** | Large | Model-dependent |
| **Best For** | Cloud apps, production | Local dev, privacy |

## 🛠️ Troubleshooting

### "Cannot connect to Ollama server"

**Problem**: Ollama server not running
```bash
# Solution 1: Start Ollama
ollama serve

# Solution 2: Verify running (in new terminal)
curl http://localhost:11434/api/tags
```

### "Model not found" error

**Problem**: Requested model not pulled
```bash
# Solution: Pull the model
ollama pull mistral:7b
ollama pull llama2:7b
```

### Slow response times

**Problem**: Large model or insufficient RAM
```bash
# Solution 1: Use smaller model
ollama pull orca-mini:3b

# Solution 2: Reduce context size
# Edit AI_MAX_TOKENS in .env
AI_MAX_TOKENS=2048
```

### High memory usage

**Problem**: Ollama using too much RAM
```bash
# Solution: Unload model when not in use
# Ollama auto-unloads after 5 minutes of inactivity
# Or restart Ollama server: ollama serve
```

## 📈 Performance Tips

### 1. Reduce Content Size
```env
# Limit chunks sent to AI
_MAX_CHARS_PER_CHUNK=15000  # Default: 25000
```

### 2. Use Smaller Model
```env
OLLAMA_MODEL=orca-mini:3b  # Faster, uses less RAM
```

### 3. Lower Temperature for Consistency
```env
AI_TEMPERATURE=0.1  # More consistent results
```

### 4. Limit Output Tokens
```env
AI_MAX_TOKENS=2048  # Faster responses
```

## 🔍 Testing Ollama Integration

### Test Connection
```bash
curl http://localhost:11434/api/tags
```

### Test Model Generation
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "mistral:7b",
  "prompt": "What is 2+2?",
  "stream": false
}'
```

### Test via Python
```python
from scraper.ai_analyzer import get_analyzer

analyzer = get_analyzer(provider="ollama", model="mistral:7b")
result = analyzer.analyze(
    text="Your content here",
    user_prompt="Summarize this content"
)
print(result.response_text)
```

## 🚀 Production Deployment

For production use with Ollama:

1. **Remote Ollama Server**: Configure `OLLAMA_BASE_URL` to remote host
2. **Load Balancing**: Use multiple Ollama servers
3. **Caching**: Cache frequent analyses
4. **Rate Limiting**: Implement request throttling
5. **Monitoring**: Track response times and errors

```env
# Production config example
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama-server.internal:11434
OLLAMA_MODEL=mistral:7b
AI_TEMPERATURE=0.2
AI_MAX_TOKENS=2048
```

## 📚 Useful Resources

- **Ollama Official**: https://ollama.ai
- **Ollama Models**: https://ollama.ai/library
- **Ollama Python Client**: https://github.com/ollama/ollama-python
- **Mistral Model**: https://mistral.ai

## ✅ Verification Checklist

- [ ] Ollama installed and running
- [ ] Model pulled (`ollama pull mistral:7b`)
- [ ] `.env` file configured with `AI_PROVIDER=ollama`
- [ ] Streamlit app starts without errors
- [ ] Ollama option visible in sidebar
- [ ] Test analysis completes successfully

---

For questions or issues, check Ollama docs or raise an issue in the project repository.
