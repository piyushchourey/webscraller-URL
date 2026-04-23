# 🔍 Web Scraper + Gemini AI Analyzer

A powerful web scraping and AI analysis tool built with Streamlit that extracts content from any webpage and uses Google's Gemini AI to analyze it with custom prompts.

## 🚀 Features

- **Smart Web Scraping**: Extracts clean, readable text from any website
- **AI-Powered Analysis**: Uses Google's Gemini AI for intelligent content analysis
- **Multiple Analysis Templates**: Pre-built templates for common analysis tasks
- **Custom Prompts**: Write your own analysis instructions
- **Rich Metadata Extraction**: Captures title, description, author, publish date, and links
- **Streamlit UI**: Modern, responsive web interface
- **Download Support**: Export scraped content and analysis results
- **Bulk Processing**: Process hundreds of URLs from Excel files with batching
- **Scalable Pipeline**: Worker-based processing with progress tracking
- **Structured Data Extraction**: AI-powered company data enrichment

## 🏗️ Architecture

The project consists of four main components:

1. **Streamlit Frontend** (`app.py`, `pages/bulk_processing.py`) - User interface and workflow management
2. **Web Scraper** (`scraper/core.py`) - Handles URL fetching and content extraction
3. **AI Analyzer** (`scraper/ai_analyzer.py`) - Integrates with Gemini/Ollama AI for content analysis
4. **Bulk Processor** (`scraper/bulk_processor.py`) - Handles batch processing and Excel operations

## 📚 Libraries and Dependencies

### Core Libraries

#### **Streamlit** (`streamlit>=1.30.0`)
- **Purpose**: Creates the interactive web application interface
- **Usage**: Handles UI components, session state, file downloads, and user interactions
- **Key Features Used**:
  - `@st.cache_resource` for caching scraper instances
  - Session state management for storing scraped content and analysis history
  - File download functionality
  - Progress spinners and error handling

#### **Requests** (`requests>=2.31.0`)
- **Purpose**: Handles HTTP requests to fetch web pages
- **Usage**: Makes GET requests with proper headers and timeout handling
- **Key Features Used**:
  - Session management for connection reuse
  - Automatic encoding detection (`resp.apparent_encoding`)
  - Redirect following and status code checking

#### **BeautifulSoup4** (`beautifulsoup4>=4.12.0`)
- **Purpose**: HTML parsing and metadata extraction
- **Usage**: Parses HTML to extract structured metadata like descriptions, authors, and links
- **Key Features Used**:
  - CSS selector-based element finding
  - Meta tag extraction (Open Graph, standard meta tags)
  - Link and image URL resolution

#### **lxml** (`lxml>=5.1.0`)
- **Purpose**: Fast XML/HTML parsing library
- **Usage**: Backend parser for BeautifulSoup operations
- **Why Used**: Faster and more robust than standard library parsers

### Content Extraction Libraries

#### **Trafilatura** (`trafilatura>=1.6.0`)
- **Purpose**: Advanced web content extraction library
- **Usage**: Primary content extractor for article-like web pages
- **Key Features Used**:
  - Automatic content extraction from HTML
  - Metadata extraction (titles, dates)
  - Table content inclusion
  - Fallback handling for complex pages
  - URL-aware extraction for better context

#### **Readability-lxml** (`readability-lxml>=0.8.1`)
- **Purpose**: Mozilla Readability algorithm implementation
- **Usage**: Fallback content extractor when Trafilatura fails
- **Key Features Used**:
  - Content extraction using readability heuristics
  - Title extraction
  - HTML cleaning and text conversion

### AI and Validation Libraries

#### **Google GenAI** (`google-genai>=1.0.0`)
- **Purpose**: Official Google Gemini AI API client
- **Usage**: Sends content to Gemini models for analysis
- **Key Features Used**:
  - Content generation with custom prompts
  - System instructions for consistent behavior
  - Token usage tracking
  - Multiple model support (gemini-2.5-flash, gemini-2.0-flash, etc.)
  - Temperature and token limit configuration

#### **Validators** (`validators>=0.22.0`)
- **Purpose**: URL validation library
- **Usage**: Validates user-provided URLs before scraping
- **Key Features Used**:
  - URL format validation
  - Automatic HTTP/HTTPS prefix addition

#### **Python-dotenv** (`python-dotenv>=1.0.0`)
- **Purpose**: Environment variable management
- **Usage**: Loads API keys from .env files
- **Key Features Used**:
  - Automatic .env file loading
  - Secure API key storage

## 🔧 How It Works

### 1. Web Scraping Process

```python
# URL Validation
url = validators.url(url)  # Validate URL format

# HTTP Request
response = requests.get(url, headers=headers, timeout=15)

# Content Extraction (Trafilatura → Readability fallback)
extractors = [TrafilaturaExtractor(), ReadabilityExtractor()]
for extractor in extractors:
    text = extractor.extract_text(html, url)
    if text and len(text.split()) > 20:
        break

# Metadata Extraction
soup = BeautifulSoup(html, 'lxml')
meta_description = soup.find("meta", {"name": "description"})
links = [urljoin(base_url, a['href']) for a in soup.find_all('a', href=True)]

## 🧩 URL Fragment (`#id`) Handling (Token-Optimized)

If the input URL includes a fragment (e.g., `https://example.com/page#section`), this project now preserves that fragment and extracts the corresponding section only:

- Network fetch uses `https://example.com/page` (fragment is client-side only)
- The processor then searches the HTML DOM for `id="section"`
- It returns minimal context text from that node (and nearest sibling body text for headings), instead of full-page content

This reduces token usage when sending content to Gemini, and gives more focused analysis.
```

### 2. AI Analysis Process

```python
# Text Chunking (for large content)
chunks = _chunk_text(text, max_chars=25000)

# Gemini API Call
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=full_prompt,
    config=GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.3,
        max_output_tokens=4096,
    )
)

# Multi-chunk Analysis (if needed)
if len(chunks) > 1:
    # Analyze each chunk separately
    # Then merge results with another Gemini call
```

### 3. Streamlit Workflow

```python
# Session State Management
st.session_state["scraped"] = scraped_content
st.session_state["analysis_history"] = [analysis_results]

# UI Components
with st.spinner("Fetching and extracting content…"):
    result = scraper.scrape(url)

# Template Selection
selected_template = st.button("Summarize")  # From ANALYSIS_TEMPLATES
```

## 📋 Analysis Templates

The application includes 6 pre-built analysis templates:

1. **Summarize**: Concise summary with main topic and conclusions
2. **Extract Key Facts**: Bullet-point list of facts, statistics, and data
3. **Sentiment Analysis**: Tone analysis with emotional language detection
4. **Extract Entities**: Named entities grouped by category
5. **Action Items/Takeaways**: Recommendations and action items
6. **Q&A Format**: Content converted to question-answer format

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.8+
- Gemini API key from [Google AI Studio](https://aistudio.google.com)

### Installation
```bash
# Clone repository
git clone https://github.com/piyushchourey/webscraller-URL.git
cd webscraller-URL

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
echo "GEMINI_API_KEY=your_api_key_here" > .env
```

### Database Configuration (SQLite or PostgreSQL)

The app now reads DB connection from `DATABASE_URL` (or `DB_URL`).

```bash
# SQLite (default)
DATABASE_URL=sqlite:///webscraper.db

# PostgreSQL
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/database_name
```

### Migrate existing SQLite records to PostgreSQL

```bash
python scripts/migrate_sqlite_to_postgres.py --source "sqlite:///webscraper.db" --target "postgresql+psycopg2://user:password@host:5432/database_name"
```

## 📊 Bulk Processing

Process hundreds of URLs from Excel files with intelligent batching and structured data extraction.

### Features
- **Batch Processing**: Process URLs in configurable batches (default: 50 URLs/batch)
- **Concurrent Workers**: Multiple URLs processed simultaneously per batch
- **Progress Tracking**: Real-time progress updates and status monitoring
- **Error Recovery**: Robust error handling with detailed error summaries
- **Structured Extraction**: AI-powered company data enrichment
- **Memory Efficient**: Batch-wise processing prevents memory overload

### Excel Format
Create an Excel file with a column named `URL` containing website addresses:

| URL |
|-----|
| https://www.company1.com |
| https://www.company2.com |
| https://www.company3.com |

### Output Format
The results Excel file contains structured company data:
- **Company Name**: Extracted company name
- **Location**: Headquarters or primary location
- **Website**: Official website URL
- **Industry**: Primary business sector
- **Key Persons**: CEO, CTO, founders with titles
- **Processing Status**: Success/failure status
- **Confidence Score**: AI extraction confidence (0.0-1.0)

### Usage
1. Navigate to **"Bulk Processing"** in the Streamlit app
2. Upload your Excel file with URLs
3. Configure batch size and AI provider
4. Click **"Start Bulk Processing"**
5. Monitor progress in real-time
6. Download the enriched results Excel file

### Configuration Options
- **Batch Size**: URLs per batch (10-100, default: 50)
- **Concurrent Workers**: Workers per batch (1-5, default: 3)
- **AI Provider**: Ollama (local) or Gemini (cloud)
- **AI Model**: Specific model to use for analysis

### Best Practices
- **Start Small**: Test with 20-30 URLs first
- **Batch Sizing**: Use smaller batches (20-30) for reliability
- **Rate Limiting**: Built-in delays prevent server blocking
- **Error Monitoring**: Check error summaries for common issues
- **Memory Management**: Large batches are processed sequentially

### Running the Application

#### Development Mode
```bash
streamlit run app.py
```

#### Production Mode (with nginx proxy)
```bash
# Start Streamlit server
streamlit run app.py --server.address 0.0.0.0 --server.port 8510 --server.headless true --server.enableCORS false --server.baseUrlPath /webscraller-URL/

# Configure nginx (see nginx.conf example)
nginx -s reload
```

## 🔒 Security & Best Practices

- **Rate Limiting**: Built-in delays and timeout handling
- **Content Size Limits**: 10MB maximum response size
- **URL Validation**: Strict URL format checking
- **Error Handling**: Comprehensive exception handling
- **Session Management**: Secure API key handling in Streamlit sessions

## 📊 Performance Optimizations

- **Caching**: Streamlit `@st.cache_resource` for scraper instances
- **Chunking**: Large content split into manageable pieces for AI analysis
- **Fallback Extraction**: Multiple extraction strategies for reliability
- **Connection Reuse**: Requests session management
- **Lazy Loading**: Content displayed on-demand in expandable sections

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

- **Trafilatura**: For robust web content extraction
- **Mozilla Readability**: For fallback content extraction
- **Google Gemini**: For powerful AI analysis capabilities
- **Streamlit**: For the excellent web app framework</content>
<parameter name="filePath">d:\projects\webscraller-URL\README.md