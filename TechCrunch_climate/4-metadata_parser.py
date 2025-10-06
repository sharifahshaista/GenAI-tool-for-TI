"""
Script to extract metadata from TechCrunch markdown files.
Extracts URL, title, publication date+time, content, tags, and author.
"""

import os
import re
from pathlib import Path
from datetime import datetime
import pandas as pd


BLOCKED_URLS = set([])


def url_to_title(url):
    """Convert URL slug to proper sentence case title."""
    if not url:
        return None
    slug = url.split('/')[-1]
    words = slug.replace('.md', '').split('-')
    title_words = []
    for word in words:
        if word.upper() in ['EV', 'SUV', 'BMW', 'VW', 'ID', 'CEO', 'CFO', 'AI', 'US', 'USA', 'UK']:
            title_words.append(word.upper())
        elif word.lower() in ['and', 'or', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by']:
            if len(title_words) == 0:
                title_words.append(word.capitalize())
            else:
                title_words.append(word.lower())
        else:
            title_words.append(word.capitalize())
    return ' '.join(title_words)


def parse_markdown(file_path):
    """Parse a markdown file into structured metadata."""
    data = {
        "url": None,
        "title": None,
        "date": None,
        "content": None,
        "tags": "",
        "author": ""
    }

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()

    # --- URL ---
    for line in lines:
        if line.startswith("# https://techcrunch.com"):
            data["url"] = line.lstrip("# ").strip()
            break

    # --- Title (from URL slug) ---
    if data["url"]:
        data["title"] = url_to_title(data["url"])

    # --- Date + Time (from content block) ---
    # Example line: "6:00 AM PDT · September 12, 2025"
    datetime_match = re.search(r"(\d{1,2}:\d{2}\s*[AP]M\s*\w*)\s*·\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    if datetime_match:
        time_str, date_str = datetime_match.groups()
        try:
            dt_obj = datetime.strptime(f"{date_str} {time_str}", "%B %d, %Y %I:%M %p %Z")
            data["date"] = dt_obj.strftime("%d %B %Y, %I:%M %p %Z")
        except Exception:
            # fallback if timezone parsing fails
            data["date"] = f"{date_str}, {time_str}"

        # remove this line from content later
        text = text.replace(datetime_match.group(0), "")

    # --- Tags (after "Topics") ---
    tags_str = ""
    if "Topics" in text:
        topics_section = text.split("Topics", 1)[-1]
        tags = re.findall(r"\[([^\]]+)\]\([^)]+\)", topics_section)
        if tags:
            tags_str = ", ".join(tags)
    data["tags"] = tags_str

    # --- Author (lines immediately after Topics) ---
    if "Topics" in text:
        after_topics = text.split("Topics", 1)[-1].splitlines()
        author_lines = []
        for line in after_topics:
            line = line.strip()
            if not line:
                continue
            if line.startswith("["):  # skip links
                continue
            if line.lower().startswith("october") or line.lower().startswith("san francisco"):
                break
            author_lines.append(line)
            if len(author_lines) >= 3:
                break
        data["author"] = " ".join(author_lines).strip()

    # --- Content ---
    # Remove promotional, footer and most popular sections
    end_markers = ["## Most Popular", "Loading the next article"]
    end_index = len(text)
    for marker in end_markers:
        idx = text.find(marker)
        if idx != -1 and idx < end_index:
            end_index = idx
    content_text = text[:end_index].strip()

    # cleanup content lines
    content_lines = []
    for line in content_text.splitlines():
        line = line.strip()
        if not line:
            if not content_lines:
                continue
        if line.startswith("# https://") or line.startswith("Status:") or line.startswith("Crawl Depth:"):
            continue
        if line.startswith("Page Type:") or line.startswith("Discovered from:"):
            continue
        if line.startswith("---"):
            continue
        if line.startswith("# "):  # title already captured
            continue
        if line.startswith("Topics"):
            break
        content_lines.append(line)
    data["content"] = "\n".join(content_lines).strip()

    return data


def process_markdown_folder(root_folder):
    """Process all markdown files into a DataFrame, filtering out blocked URLs."""
    root = Path(root_folder)
    rows = []

    for md_file in root.rglob("*.md"):
        try:
            parsed = parse_markdown(md_file)
            if parsed["url"] in BLOCKED_URLS:
                continue
            if not parsed["url"] or not parsed["title"]:
                continue
            parsed["file_name"] = md_file.name
            parsed["folder"] = md_file.parent.name
            rows.append(parsed)
        except Exception as e:
            print(f"Error processing {md_file}: {e}")
            continue

    return pd.DataFrame(rows)


if __name__ == "__main__":
    folder = "/Users/sharifahshaista/GenAI-for-TI/techcrunch-climate/techcrunch_crawl_output"  # Change this to your folder path
    df = process_markdown_folder(folder)
    df.to_csv("techcrunch_raw.csv", index=False)
    print(f"Processed {len(df)} articles after filtering.")
    print(df.head())
