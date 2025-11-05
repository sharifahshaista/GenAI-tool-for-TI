import os
import json
import time
import pandas as pd
from pathlib import Path
from openai import OpenAI
from typing import List, Optional, Callable
from pydantic import BaseModel, Field, ValidationError
import re

# Pydantic model for LLM output
class ArticleExtraction(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[str] = None
    main_content: str = ""
    tags: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    summary: str = ""

# Helper function to extract JSON from LLM response
def parse_llm_json(response_text: str):
    """Extract the first JSON object from the LLM response."""
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None
    return None

def llm_extract(client: OpenAI, model_name: str, source: str):
    """Use LLM to extract structured fields from markdown text."""
    prompt = f"""
You are an expert at extracting structured information from markdown documents.

Extract the following fields from the provided markdown content. Return ONLY what is explicitly present.

**OUTPUT FORMAT:**
Return a valid JSON object ONLY with these exact keys:
{{
"url": "string or null",
"title": "string or null",
"author": "string or null",
"publication_date": "string or null",
"main_content": "string",
"tags": ["array of strings"],
"categories": ["array of strings"],
"summary": "string"
}}

**SOURCE CONTENT:**
{source}
"""

    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}]
    )

    result_text = response.choices[0].message.content.strip()

    # Extract JSON safely
    result_json = parse_llm_json(result_text)
    if result_json is None:
        print("JSON parsing failed, returning empty ArticleExtraction")
        result_json = {}

    # Validate and coerce output using Pydantic
    try:
        article = ArticleExtraction(**result_json)
    except ValidationError as e:
        print(f"Validation error: {e}")
        article = ArticleExtraction()

    # Token usage handling
    token_usage = {}
    if hasattr(response, "usage") and response.usage:
        token_usage = {
            "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
            "completion_tokens": getattr(response.usage, "completion_tokens", None),
            "total_tokens": getattr(response.usage, "total_tokens", None),
        }

    return article, token_usage

async def process_folder_with_progress(
    folder_path: Path,
    output_dir: Path,
    client: OpenAI,
    model_name: str,
    progress_callback: Optional[Callable] = None
):
    """
    Process all markdown files in a folder using LLM extraction.

    Args:
        folder_path: Path to folder containing markdown files
        output_dir: Path to output directory for CSV/JSON
        client: OpenAI client (Azure or Ollama)
        model_name: Model name to use
        progress_callback: Optional callback function(message, current, total)

    Returns:
        tuple: (DataFrame, stats_dict)
    """
    start_time = time.time()
    table = []

    # Get all markdown files
    md_files = list(folder_path.rglob('*.md'))
    total_files = len(md_files)

    if total_files == 0:
        return pd.DataFrame(), {
            'total_files': 0,
            'processed': 0,
            'skipped_error': 0,
            'duration_seconds': 0
        }

    processed = 0
    failed = 0

    for idx, file_path in enumerate(md_files, 1):
        file_name = file_path.name

        # Update progress
        if progress_callback:
            elapsed = time.time() - start_time
            if processed > 0:
                avg_time = elapsed / processed
                remaining_estimate = avg_time * (total_files - processed)
            else:
                remaining_estimate = 0

            progress_callback(
                f"Processing: {file_name}",
                idx,
                total_files
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract using LLM
            result, token_usage = llm_extract(client, model_name, content)

            table.append({
                "file": file_name,
                "url": result.url,
                "title": result.title,
                "author": result.author,
                "publication_date": result.publication_date,
                "content": result.main_content,
                "tags": ', '.join(result.tags) if result.tags else '',
                "categories": ', '.join(result.categories) if result.categories else '',
                "summary": result.summary,
                "prompt_tokens": token_usage.get("prompt_tokens"),
                "completion_tokens": token_usage.get("completion_tokens"),
                "total_tokens": token_usage.get("total_tokens"),
                "success": True
            })
            processed += 1

        except Exception as e:
            print(f"Error processing {file_name}: {e}")
            table.append({
                "file": file_name,
                "url": None,
                "title": None,
                "author": None,
                "publication_date": None,
                "content": "",
                "tags": "",
                "categories": "",
                "summary": "",
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "success": False,
                "error": str(e)
            })
            failed += 1

    # Create DataFrame
    df = pd.DataFrame(table)

    # Save to output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save CSV
    csv_path = output_dir / f"llm_extraction_{int(time.time())}.csv"
    df.to_csv(csv_path, index=False)

    # Save JSON
    json_path = output_dir / f"llm_extraction_{int(time.time())}.json"
    df.to_json(json_path, orient='records', indent=2)

    end_time = time.time()
    duration = end_time - start_time

    stats = {
        'total_files': total_files,
        'processed': processed,
        'skipped_error': failed,
        'duration_seconds': duration,
        'output_csv': str(csv_path),
        'output_json': str(json_path)
    }

    return df, stats
