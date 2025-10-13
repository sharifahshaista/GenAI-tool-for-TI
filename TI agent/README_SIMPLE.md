# Research Agent - Simple Guide

An AI-powered research tool that automates web research and extracts structured insights.

## Overview

The Research Agent helps you conduct comprehensive research by:
1. **Clarifying** your research question
2. **Generating** optimized search queries
3. **Searching** the web via SearxNG
4. **Extracting** structured learnings with sources
5. **First-pass summarizing** CSV content with tech-intelligence analysis

## Requirements

- **Python 3.12+**
- **SearxNG** running at `http://localhost:32768`
- **Azure OpenAI** API credentials

## Installation

### 1. Install Python Packages

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install streamlit pydantic pydantic-ai pydantic-settings openai azure-identity httpx python-dotenv pandas
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
AZURE_OPENAI_API_KEY=your_api_key_here
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
MODEL_NAME=pmo-gpt-4.1-nano
```

### 3. Start SearxNG

```bash
docker run -d -p 32768:8080 searxng/searxng
```

## Usage

### Option 1: Web Interface (Recommended)

**Start the app:**
```bash
streamlit run app.py
```

**What happens:**
- Browser opens at `http://localhost:8501`
- Interactive web interface loads

**Research Pipeline Steps:**
1. Enter research topic
2. Click "Start Research"
3. Answer 1-4 clarification questions
4. Review generated search queries
5. Click "Execute Web Search"
6. Save results with filename
7. Go to "Learning Extraction" tab
8. Extract insights from results

**First-pass Summarization Steps:**
1. Go to "First-pass Summarization" tab
2. Select AI model provider (Azure OpenAI or LM Studio)
3. Upload CSV file with 'content' column
4. Preview data
5. Click "Start Summarization"
6. Review results and statistics
7. Save or download processed files
8. Access history of processed files

**Model Options:**
- **Azure OpenAI**: Cloud-based models (GPT-4, GPT-4o, etc.)
- **LM Studio**: Run local models for privacy and cost savings
- See `LM_STUDIO_SETUP.md` for detailed setup instructions

**Output:**
- `data/{filename}.json` - Search results
- `data/{filename}.md` - Learnings report
- `summarised_content/{filename}_summarized.csv` - Summarized CSV
- `summarised_content/{filename}_log.txt` - Processing log
- `research.log` - Application logs


---

### Option 2: Command Line

**Run the script:**
```bash
python main.py
```

**What happens:**
1. Runs on hardcoded topic: *"What is the expected growth rate of chinese tuition market in Singapore?"*
2. Prompts for clarification answers in terminal
3. Automatically generates and executes searches
4. Extracts learnings automatically
5. Saves results to `data/Chinese_tuition.json` and `.md`

**Customize:**
Edit lines 7-8 in `main.py`:
```python
topic = "Your research question here"
file_name = "your_output_name"
```


---

## Project Structure

```
research_agent/
├── agents/                    # AI agent implementations
│   ├── clarification.py      # Generates clarification questions
│   ├── serp.py              # Generates search queries
│   ├── learn.py             # Extracts learnings
│   └── summarise_csv.py     # First-pass summarization agent
│
├── config/                   # Configuration
│   ├── azure_model.py       # Azure OpenAI setup
│   └── searxng_tools.py     # SearxNG configuration
│
├── tools/
│   └── searxng_client.py    # SearxNG HTTP client
│
├── schemas/
│   └── datamodel.py         # Data validation models
│
├── data/                     # Research output (auto-created)
│   ├── *.json              # Search results
│   └── *.md                # Learning reports
│
├── summarised_content/       # CSV output (auto-created)
│   ├── *_summarized.csv    # Processed CSV files
│   ├── *_log.txt           # Processing logs
│   └── history.json        # Processing history
│
├── app.py                   # Streamlit web UI
├── main.py                  # CLI example
├── search.py                # Core search logic
├── learning_pts.py          # Learning extraction
├── sample_test.csv          # Sample CSV for testing
├── CSV_SUMMARIZATION_GUIDE.md  # CSV feature documentation
└── .env                     # Your credentials
```

## Output Files

### Search Results (`data/{filename}.json`)
```json
{
  "query 1": "Search results for query 1...",
  "query 2": "Search results for query 2...",
  ...
}
```

### Learning Report (`data/{filename}.md`)
Structured learnings with:
- Key insights
- Entities (companies, people, places)
- Metrics (numbers, dates, percentages)
- Source URLs

### Application Log (`research.log`)
Detailed execution logs for debugging

### Summarized CSV (`summarised_content/{filename}_summarized.csv`)
Original CSV with added 'summary' column containing tech-intel summaries

### Processing Log (`summarised_content/{filename}_log.txt`)
Statistics and metadata:
- Processing date and duration
- Success/failure counts
- Average time per row

## Expected Behavior

### app.py Flow
```
1. Browser opens → Streamlit UI loads
2. Enter topic → Start Research
3. Answer clarification questions → Submit
4. Review queries → Execute Web Search
5. Progress bar shows search execution
6. Browse results → Save with filename
7. Learning Extraction tab → Select file
8. Extract Learnings → Download report
```

### main.py Flow
```
1. Script starts
2. "I need some clarification:" (if needed)
3. Answer questions in terminal
4. "Searching for: [query 1]"
5. "Found results for query: [query 1]"
6. ... (repeats for all queries)
7. "Results saved to data/Chinese_tuition.json"
8. "Query: [query 1]"
9. "Learnings: [extracted content]"
10. ... (repeats for all queries)
11. "Learnings saved to Chinese_tuition.md"
```

## First-pass Summarization Feature

### Quick Start

1. **Prepare CSV file** with a 'content' column
2. **Run Streamlit**: `streamlit run app.py`
3. **Navigate** to "First-pass Summarization" tab
4. **Upload** your CSV file
5. **Process** and download results

### Sample Data

Use `sample_test.csv` to test the feature:
```bash
# It contains 5 tech news articles ready to be summarized
```

### Tech-Intelligence Focus

Summaries extract:
- Core technological developments
- Key companies and institutions
- Technical metrics and specifications
- Strategic implications
- Timeline and geography

Output: 150-200 word analytical paragraphs

### For More Details

See `CSV_SUMMARIZATION_GUIDE.md` for:
- Complete feature documentation
- Detailed usage instructions
- Troubleshooting guide
- Best practices

