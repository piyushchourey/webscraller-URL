# 🚀 Ollama Configuration - Quick Reference

## ✅ Setup Completed

Your Web Scraper project now supports both **Gemini** and **Ollama** AI providers!

## 📦 What Was Added

### 1. **Dependencies** (`requirements.txt`)
- `ollama>=0.1.0` - Ollama Python client

### 2. **Configuration** (`.env.example`)
```env
# Provider selection
AI_PROVIDER=ollama              # "gemini" or "ollama"
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b
AI_TEMPERATURE=0.3
AI_MAX_TOKENS=4096
```

### 3. **AI Analyzer Updates** (`scraper/ai_analyzer.py`)
- ✅ `OllamaAnalyzer` class - Local LLM support
- ✅ `get_analyzer()` factory function - Dynamic provider selection
- ✅ Multi-chunk analysis support for both providers
- ✅ Environment-based configuration

### 4. **Streamlit UI Updates** (`app.py`)
- ✅ AI Provider selector (Gemini / Ollama)
- ✅ Dynamic configuration per provider
- ✅ Provider-specific error handling

## 🎯 Getting Started

### Step 1: Install Ollama
Download: https://ollama.ai

### Step 2: Pull Model
```bash
ollama pull mistral:7b
```

### Step 3: Start Ollama Server
```bash
ollama serve
```
*(Server runs on port 11434 by default)*

### Step 4: Configure Project
Copy `.env.example` to `.env` and update:
```bash
cp .env.example .env
```

Edit `.env`:
```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b
```

### Step 5: Run App
```bash
streamlit run app.py
```

## 🎛️ In Streamlit

1. Open sidebar
2. Select **"Ollama"** from AI Provider radio
3. Verify Ollama Server URL
4. Enter model name (e.g., `mistral:7b`)
5. Use analysis templates or write custom prompts

## 📊 Architecture Overview

```
┌─────────────────────────────────────┐
│     Streamlit UI (app.py)           │
│  - AI Provider Selector             │
│  - Dynamic Configuration            │
└──────────────┬──────────────────────┘
               │
        ┌──────▼──────┐
        │ get_analyzer│ (Factory)
        └──┬────────┬─┘
           │        │
      ┌────▼──┐ ┌───▼──────┐
      │Gemini │ │  Ollama  │
      │Remote │ │  Local   │
      └───────┘ └──────────┘
           │        │
           └────┬───┘
      ┌────────▼────────┐
      │ Analysis Result │
      └─────────────────┘
```

## 🔧 Configuration Priority

1. **Streamlit Sidebar** (highest) - User input
2. **.env file** (middle) - Environment variables
3. **Defaults** (lowest) - Code defaults

Example:
```python
model = st.text_input("Model", value="mistral:7b")  # From UI
# Falls back to: os.getenv("OLLAMA_MODEL", "mistral:7b")  # From .env
# Falls back to: "mistral:7b"  # Default
```

## 📋 Key Files Modified

| File | Changes |
|------|---------|
| `requirements.txt` | Added `ollama>=0.1.0` |
| `.env.example` | New config template |
| `scraper/ai_analyzer.py` | New `OllamaAnalyzer` class, `get_analyzer()` factory |
| `app.py` | Provider selector UI, dynamic analyzer initialization |

## 🚀 Running Modes

### Mode 1: Gemini (Cloud)
```bash
# .env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key_here

# Streamlit: Select "Gemini" → Enter API key
```

### Mode 2: Ollama (Local)
```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Run app
AI_PROVIDER=ollama streamlit run app.py

# Streamlit: Select "Ollama" → Verify URL
```

### Mode 3: Switch Between
Just change `AI_PROVIDER` in `.env` or sidebar selector!

## 🎯 Recommended Models

| Use Case | Model | Speed |
|----------|-------|-------|
| Fast prototyping | `orca-mini:3b` | ⚡⚡⚡ |
| Balanced | `mistral:7b` | ⚡⚡ |
| High quality | `llama2:7b` | ⚡ |
| Very detailed | `dolphin-mixtral` | 🐢 |

Install additional models:
```bash
ollama pull orca-mini:3b
ollama pull llama2:7b
ollama pull neural-chat
```

## 🔍 Testing

### Test Ollama Connection
```bash
curl http://localhost:11434/api/tags
```

### Test in Python
```python
from scraper.ai_analyzer import get_analyzer

analyzer = get_analyzer(provider="ollama", model="mistral:7b")
result = analyzer.analyze(
    text="Sample content",
    user_prompt="Summarize this"
)
print(result.response_text)
```

### Test from Streamlit
1. Open http://localhost:8501
2. Select Ollama
3. Enter a URL and run analysis

## ⚙️ Environment Variables Reference

```env
# Provider
AI_PROVIDER=ollama              # "gemini" or "ollama"

# Ollama specific
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b

# Gemini specific
GEMINI_API_KEY=your_key_here

# Shared parameters
AI_TEMPERATURE=0.3              # 0.0-1.0 (lower = more consistent)
AI_MAX_TOKENS=4096              # Max output tokens
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot connect to Ollama" | Start Ollama: `ollama serve` |
| "Model not found" | Pull it: `ollama pull mistral:7b` |
| Slow responses | Use smaller model or reduce AI_MAX_TOKENS |
| High memory | Ollama auto-unloads after 5 min of inactivity |

## 📚 More Info

See **OLLAMA_SETUP.md** for detailed guide including:
- Full troubleshooting guide
- Performance optimization tips
- Production deployment setup
- Testing procedures

## ✨ Key Benefits

✅ **Cost-Free**: Run models locally with Ollama  
✅ **Privacy**: Keep data on your machine  
✅ **Flexible**: Switch providers anytime  
✅ **Fast**: Local inference latency ~2-5s  
✅ **Offline**: Works without internet  

---

**Next Steps:**
1. Install Ollama: https://ollama.ai
2. Pull a model: `ollama pull mistral:7b`
3. Start server: `ollama serve`
4. Copy .env: `cp .env.example .env`
5. Run app: `streamlit run app.py`
6. Select Ollama in sidebar ✨

