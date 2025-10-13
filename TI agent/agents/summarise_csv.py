"""
First-pass Summarization Agent

This agent summarizes text content from CSV files using a tech-intelligence focused prompt.
"""

from config.azure_model import model
from pydantic_ai import Agent
import pandas as pd
import logging
from pathlib import Path
from datetime import datetime
import time

# Tech Intelligence Summarization Prompt
TECH_INTEL_PROMPT = """
You are a technology intelligence analyst. Summarise raw scraped article text from news or aggregator sites 
into a short, factual brief capturing the core development and its implications.

Extract and retain only:
- Main technological development or event (what happened)
- Key actors (companies, institutions, researchers)
- Technology domain and maturity stage
- Quantitative or qualitative metrics (if available)
- Purpose and implications (why it matters, potential impact)
- Time and location (if mentioned)

Omit: marketing language, filler and unrelated content.

Output (150-200 words):
A single concise, neutral, and analytical paragraph focused on signal over noise.
"""

# Classification Categories
CLASSIFICATION_CATEGORIES = [
    "Carbon capture", "Direct air capture", "Carbon sequestration", "Carbon accounting",
    "Methane abatement", "Renewable energy", "Solar photovoltaics", "Solar thermal",
    "Wind energy", "Offshore wind", "Onshore wind", "Hydropower", "Ocean energy",
    "Tidal energy", "Geothermal energy", "Energy storage", "Battery technology",
    "Grid scale storage", "Hydrogen economy", "Green hydrogen", "Blue hydrogen",
    "Energy efficiency", "Smart grids", "Microgrids", "Virtual power plants",
    "Demand response", "Building decarbonization", "Heat pumps", "Green building materials",
    "Sustainable construction", "Net zero buildings", "Electrification", "Clean mobility",
    "Electric vehicles", "EV charging infrastructure", "Sustainable aviation fuel",
    "Biofuels", "Advanced bioenergy", "Circular economy", "Recycling technology",
    "Waste-to-energy", "Sustainable packaging", "Industrial decarbonization",
    "Green steel", "Green cement", "Clean manufacturing", "AgTech",
    "Precision agriculture", "Regenerative agriculture", "Alternative proteins",
    "Indoor farming", "Vertical farming", "Climate adaptation", "Drought resilience",
    "Flood mitigation", "Water management", "Climate risk modeling", "Remote sensing",
    "Environmental monitoring", "Earth observation", "Nature-based solutions",
    "Ecosystem restoration", "Blue carbon", "Forest carbon sinks", "Sustainable forestry",
    "Weather forecasting", "Climate finance", "Carbon markets", "Pilot projects", "Venture capital", "Funding",
    "Investments", "Acquisitions", "Mergers", "IPO", "Public offering", "Private offering",
    "Fundraising", "Funding round", "Series A", "Series B", "Series C", "Series D", "Series E",
    "Series F", "Series G", "Series H", "Series I", "Series J", "Series K", "Series L", "Series M",
    "Series N", "Series O", "Series P", "Series Q", "Series R", "Series S", "Series T", "Series U",
    "Series V", "Series W", "Series X", "Series Y", "Series Z", "Grants"
]

# Classification Prompt
CLASSIFICATION_PROMPT = f"""
You are a climate technology classification expert. Your task is to classify summarized content into one or more relevant categories.

Available categories:
{', '.join(CLASSIFICATION_CATEGORIES)}

Instructions:
1. Read the summary carefully
2. Identify ALL relevant categories that apply (can be multiple)
3. Return ONLY the category names, separated by semicolons
4. Use exact category names from the list above
5. If no categories apply, return "Uncategorized"
6. Be precise but inclusive - include all relevant categories

Example output formats:
- "Solar photovoltaics; Renewable energy; Energy efficiency"
- "Carbon capture; Industrial decarbonization"
- "Electric vehicles; Clean mobility; Battery technology"

Return only the categories, nothing else.
"""


def create_summarization_agent(custom_model=None):
    """
    Create the summarization agent for tech-intelligence content
    
    Args:
        custom_model: Optional custom model to use (overrides default)
    """
    agent_model = custom_model if custom_model is not None else model
    
    summarization_agent = Agent(
        model=agent_model,
        output_type=str,
        system_prompt=TECH_INTEL_PROMPT
    )
    return summarization_agent


def create_classification_agent(custom_model=None):
    """
    Create the classification agent for categorizing summaries
    
    Args:
        custom_model: Optional custom model to use (overrides default)
    """
    agent_model = custom_model if custom_model is not None else model
    
    classification_agent = Agent(
        model=agent_model,
        output_type=str,
        system_prompt=CLASSIFICATION_PROMPT
    )
    return classification_agent


async def summarize_content(content: str, custom_model=None) -> str:
    """
    Summarize a single piece of content using the tech-intel prompt
    
    Args:
        content: Raw text content to summarize
        custom_model: Optional custom model to use
        
    Returns:
        Summarized content as string
    """
    agent = create_summarization_agent(custom_model)
    
    try:
        result = await agent.run(content)
        return result.output
    except Exception as e:
        logging.error(f"Error summarizing content: {e}")
        return f"[Error: Could not summarize content - {str(e)}]"


async def classify_summary(summary: str, custom_model=None) -> str:
    """
    Classify a summary into one or more categories
    
    Args:
        summary: Summarized content to classify
        custom_model: Optional custom model to use
        
    Returns:
        Semicolon-separated list of categories
    """
    agent = create_classification_agent(custom_model)
    
    try:
        result = await agent.run(summary)
        # Clean up the output
        categories = result.output.strip()
        
        # Validate that categories are from the list
        category_list = [cat.strip() for cat in categories.split(';')]
        valid_categories = [cat for cat in category_list if cat in CLASSIFICATION_CATEGORIES or cat == "Uncategorized"]
        
        if valid_categories:
            return '; '.join(valid_categories)
        else:
            return "Uncategorized"
            
    except Exception as e:
        logging.error(f"Error classifying summary: {e}")
        return f"[Error: Could not classify - {str(e)}]"


async def summarize_csv_file(
    csv_file_path: Path,
    content_column: str = "content",
    progress_callback=None,
    custom_model=None
) -> tuple[pd.DataFrame, float, dict]:
    """
    Process a CSV file and summarize the content column
    
    Args:
        csv_file_path: Path to the CSV file
        content_column: Name of the column containing content to summarize
        progress_callback: Optional callback function(current, total, elapsed, est_remaining)
        custom_model: Optional custom model to use for summarization and classification
        
    Returns:
        Tuple of (processed_dataframe, duration_seconds, metadata)
    """
    start_time = time.time()
    
    # Read CSV file
    try:
        df = pd.read_csv(csv_file_path)
    except Exception as e:
        logging.error(f"Error reading CSV file: {e}")
        raise ValueError(f"Could not read CSV file: {e}")
    
    # Validate content column exists
    if content_column not in df.columns:
        raise ValueError(
            f"Column '{content_column}' not found in CSV. "
            f"Available columns: {', '.join(df.columns)}"
        )
    
    # Add summary and classification columns
    df['summary'] = None
    df['classification'] = None
    
    # Track processing stats
    total_rows = len(df)
    successful = 0
    failed = 0
    
    # Process each row
    for idx, row in df.iterrows():
        row_start_time = time.time()
        
        try:
            content = str(row[content_column])
            
            # Check if content is empty
            if not content or content.strip() == '' or content.lower() == 'nan':
                # Try to use 'content snippet' column if available
                if 'content snippet' in df.columns and pd.notna(row.get('content snippet')):
                    content_snippet = str(row['content snippet']).strip()
                    if content_snippet and content_snippet.lower() != 'nan':
                        # Use content snippet directly as summary
                        df.at[idx, 'summary'] = content_snippet
                        # Classify the content snippet
                        classification = await classify_summary(content_snippet, custom_model)
                        df.at[idx, 'classification'] = classification
                        successful += 1
                        logging.info(f"Processed row {idx + 1}/{total_rows} using content snippet")
                        continue
                
                # If no content snippet available, mark as empty
                df.at[idx, 'summary'] = "[Empty content - no summary generated]"
                df.at[idx, 'classification'] = "Uncategorized"
                failed += 1
                continue
            
            # Summarize content
            summary = await summarize_content(content, custom_model)
            df.at[idx, 'summary'] = summary
            
            # Classify the summary
            if summary and not summary.startswith("[Error"):
                classification = await classify_summary(summary, custom_model)
                df.at[idx, 'classification'] = classification
            else:
                df.at[idx, 'classification'] = "Uncategorized"
            
            successful += 1
            
            logging.info(f"Processed row {idx + 1}/{total_rows}")
            
        except Exception as e:
            logging.error(f"Error processing row {idx}: {e}")
            df.at[idx, 'summary'] = f"[Error: {str(e)}]"
            failed += 1
        
        # Calculate progress and time estimates
        current_row = idx + 1
        elapsed_time = time.time() - start_time
        rows_remaining = total_rows - current_row
        
        # Calculate estimated time remaining
        if current_row > 0:
            avg_time_per_row = elapsed_time / current_row
            est_remaining = avg_time_per_row * rows_remaining
        else:
            est_remaining = 0
        
        # Call progress callback if provided
        if progress_callback:
            progress_callback(current_row, total_rows, elapsed_time, est_remaining)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Create metadata
    metadata = {
        'total_rows': total_rows,
        'successful': successful,
        'failed': failed,
        'duration_seconds': duration,
        'timestamp': datetime.now(),
        'source_file': csv_file_path.name,
        'content_column': content_column
    }
    
    return df, duration, metadata


def save_summarized_csv(
    df: pd.DataFrame,
    metadata: dict,
    output_dir: Path = Path("summarised_content")
) -> tuple[Path, Path]:
    """
    Save the summarized CSV and create a log file
    
    Args:
        df: Processed DataFrame with summaries
        metadata: Processing metadata
        output_dir: Directory to save files
        
    Returns:
        Tuple of (csv_path, log_path)
    """
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp_str = metadata['timestamp'].strftime('%Y%m%d_%H%M%S')
    original_name = Path(metadata['source_file']).stem
    
    csv_filename = f"{original_name}_summarized_{timestamp_str}.csv"
    log_filename = f"{original_name}_log_{timestamp_str}.txt"
    
    csv_path = output_dir / csv_filename
    log_path = output_dir / log_filename
    
    # Save CSV
    df.to_csv(csv_path, index=False, encoding='utf-8')
    
    # Create log file
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("FIRST-PASS SUMMARIZATION LOG\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Source File: {metadata['source_file']}\n")
        f.write(f"Date: {metadata['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Content Column: {metadata['content_column']}\n\n")
        f.write("-" * 60 + "\n")
        f.write("PROCESSING STATISTICS\n")
        f.write("-" * 60 + "\n")
        f.write(f"Total Rows: {metadata['total_rows']}\n")
        f.write(f"Successfully Processed: {metadata['successful']}\n")
        f.write(f"Failed: {metadata['failed']}\n")
        f.write(f"Success Rate: {(metadata['successful'] / metadata['total_rows'] * 100):.2f}%\n\n")
        f.write("-" * 60 + "\n")
        f.write("DURATION\n")
        f.write("-" * 60 + "\n")
        f.write(f"Total Duration: {metadata['duration_seconds']:.2f} seconds\n")
        f.write(f"Average per Row: {(metadata['duration_seconds'] / metadata['total_rows']):.2f} seconds\n\n")
        f.write("-" * 60 + "\n")
        f.write("OUTPUT FILES\n")
        f.write("-" * 60 + "\n")
        f.write(f"Summarized CSV: {csv_filename}\n")
        f.write(f"Log File: {log_filename}\n")
        f.write("\n" + "=" * 60 + "\n")
    
    logging.info(f"Saved summarized CSV to: {csv_path}")
    logging.info(f"Saved log to: {log_path}")
    
    return csv_path, log_path

