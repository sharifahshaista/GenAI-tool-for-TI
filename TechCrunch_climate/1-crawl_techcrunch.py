import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling.filters import (
    FilterChain,
    DomainFilter,
    URLPatternFilter,
    ContentTypeFilter
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from urllib.parse import urlparse
import os
import re
import time
from datetime import datetime

def create_safe_filename(url, index=0):
    """
    Create a safe filename from a URL.
    """
    parsed_url = urlparse(url)
    path = parsed_url.path.strip('/')
    if path:
        filename_base = path.split('/')[-1]
    else:
        filename_base = "index"
    filename_base = re.sub(r'[<>:"/\\|?*]', '_', filename_base)
    filename_base = re.sub(r'_+', '_', filename_base).strip('_')
    if not filename_base:
        filename_base = f"page_{index}"
    return f"{filename_base}.md"

async def crawl_single_url(crawler, url, base_output_dir="crawl_output", delay_between_requests=1):
    """
    Crawl a single URL and save results to a single output folder.
    Modified to only crawl URLs within the 'climate' path.
    """
    print(f"\n{'='*80}")
    print(f"STARTING CRAWL: {url}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        parsed_start_url = urlparse(url)
        base_domain = parsed_start_url.netloc

        # Strategy: Start from climate category and follow ALL article links found there
        # Use minimal filtering - let the crawler follow links from climate category to articles
        filter_chain = FilterChain([
            # Stay within the same domain
            DomainFilter(allowed_domains=[base_domain]),
            
            # Very broad patterns to capture all TechCrunch content:
            # 1. Climate category pages (starting point)
            # 2. Any article URLs that might be linked from there
            URLPatternFilter(patterns=[
                "*techcrunch.com/category/climate*",
                "*techcrunch.com/category/transportation*", 
                "*techcrunch.com/category/startups*",     
                "*techcrunch.com/2025*",
                "*techcrunch.com/category/hardware*"                  
            ]),
            
            # Only HTML content
            ContentTypeFilter(allowed_types=["text/html"], check_extension=True)
        ])

        markdown_generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.48, threshold_type="dynamic"),
            options={"ignore_links": False, "citations": True}
        )

        config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=20,  # Increased depth to ensure we reach articles: 0=category, 1=pagination, 2=articles
                filter_chain=filter_chain,
                include_external=False,
                max_pages=500,  # Increased limit to ensure we don't miss articles
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            markdown_generator=markdown_generator,
            verbose=True,  # Keep verbose to see what URLs are being processed
            exclude_external_links=True,
            excluded_tags=['nav', 'footer', 'header', 'aside'],
        )

        results = await crawler.arun(url, config=config)
        print(f"Crawled {len(results)} pages in total")
        
        # Debug: Print all discovered URLs to help troubleshoot
        print(f"\nDEBUG: All discovered URLs:")
        for i, result in enumerate(results):
            status = "✓" if result.success else "✗"
            depth = result.metadata.get('depth', 0)
            print(f"  {i+1:2d}. {status} Depth {depth}: {result.url}")
        print(f"End of discovered URLs\n")

        os.makedirs(base_output_dir, exist_ok=True)
        saved_count = 0
        filtered_count = 0

        for i, result in enumerate(results):
            if result.success and result.markdown:
                content = result.markdown.fit_markdown or result.markdown.raw_markdown
                if content and len(content.strip()) > 100:
                    filename = create_safe_filename(result.url, index=i)
                    filepath = os.path.join(base_output_dir, filename)
                    
                    # Handle duplicates
                    counter = 1
                    original_filepath = filepath
                    while os.path.exists(filepath):
                        name_parts = original_filepath.rsplit('.', 1)
                        filepath = f"{name_parts[0]}_{counter}.{name_parts[1]}"
                        counter += 1
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"# {result.url}\n\n")
                        f.write(f"Status: {result.status_code}\n")
                        f.write(f"Crawl Depth: {result.metadata.get('depth', 0)}\n")
                        f.write(f"Page Type: {'Climate Category' if '/category/climate' in result.url else 'Pagination' if '/page/' in result.url else 'Article'}\n")
                        f.write(f"Discovered from: Climate category navigation\n\n")
                        f.write("---\n\n")
                        f.write(content)
                    
                    saved_count += 1
                    print(f"  ✓ Saved: {filename}")
                else:
                    filtered_count += 1
                    print(f"  ✗ Filtered out (insufficient content)")
            else:
                print(f"  ✗ Failed or no content")

        end_time = time.time()
        crawl_duration = end_time - start_time

        # Save detailed summary for climate category crawl
        summary_file = os.path.join(base_output_dir, "_crawl_summary.txt")
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"TechCrunch Climate Category Crawl Summary\n")
            f.write(f"==========================================\n\n")
            f.write(f"Starting URL: {url}\n")
            f.write(f"Base domain: {base_domain}\n")
            f.write(f"Strategy: BFS crawl from climate category to discover all linked articles\n")
            f.write(f"Scope: Articles discovered through climate category navigation\n")
            f.write(f"Total pages crawled: {len(results)}\n")
            f.write(f"Pages saved: {saved_count}\n")
            f.write(f"Pages filtered: {filtered_count}\n")
            f.write(f"Crawl duration: {crawl_duration:.2f} seconds\n")
            f.write(f"Crawl date: {datetime.now().isoformat()}\n\n")
            
            # Add breakdown by page type and depth
            category_pages = sum(1 for r in results if r.success and '/category/climate' in r.url)
            pagination_pages = sum(1 for r in results if r.success and '/page/' in r.url)
            article_pages = saved_count - category_pages - pagination_pages
            
            f.write(f"Page breakdown:\n")
            f.write(f"- Climate category pages: {category_pages}\n")
            f.write(f"- Article pages: {article_pages}\n") 
            f.write(f"- Pagination pages: {pagination_pages}\n\n")
            
            # Breakdown by crawl depth
            depth_counts = {}
            for result in results:
                if result.success:
                    depth = result.metadata.get('depth', 0)
                    depth_counts[depth] = depth_counts.get(depth, 0) + 1
            
            f.write(f"Pages by crawl depth:\n")
            for depth in sorted(depth_counts.keys()):
                f.write(f"- Depth {depth}: {depth_counts[depth]} pages\n")
            f.write(f"\n")
            
            # List all crawled URLs organized by type
            f.write(f"All crawled URLs (organized by type):\n")
            f.write(f"====================================\n\n")
            
            # Category pages first
            category_results = [r for r in results if r.success and '/category/climate' in r.url]
            if category_results:
                f.write(f"CLIMATE CATEGORY PAGES ({len(category_results)}):\n")
                for i, result in enumerate(category_results, 1):
                    depth = result.metadata.get('depth', 0)
                    f.write(f"{i:2d}. Depth {depth} | {result.url}\n")
                f.write(f"\n")
            
            # Article pages
            article_results = [r for r in results if r.success and '/category/climate' not in r.url and '/page/' not in r.url]
            if article_results:
                f.write(f"ARTICLES DISCOVERED FROM CLIMATE CATEGORY ({len(article_results)}):\n")
                for i, result in enumerate(article_results, 1):
                    depth = result.metadata.get('depth', 0)
                    f.write(f"{i:2d}. Depth {depth} | {result.url}\n")
                f.write(f"\n")
            
            # Pagination pages
            pagination_results = [r for r in results if r.success and '/page/' in r.url]
            if pagination_results:
                f.write(f"PAGINATION PAGES ({len(pagination_results)}):\n")
                for i, result in enumerate(pagination_results, 1):
                    depth = result.metadata.get('depth', 0)
                    f.write(f"{i:2d}. Depth {depth} | {result.url}\n")
        
        print(f"  Summary saved: {summary_file}")

        return {
            'url': url,
            'total_pages': len(results),
            'saved_count': saved_count,
            'filtered_count': filtered_count,
            'duration': crawl_duration,
            'success': True
        }
        
    except Exception as e:
        print(f"ERROR crawling {url}: {str(e)}")
        return {
            'url': url,
            'total_pages': 0,
            'saved_count': 0,
            'filtered_count': 0,
            'duration': time.time() - start_time,
            'success': False,
            'error': str(e)
        }

async def crawl_multiple_urls(urls, base_output_dir="crawl_output", delay_between_crawls=5, delay_between_requests=1):
    """
    Crawl multiple URLs sequentially into a single output folder.
    Modified to only crawl climate-related content.
    """
    os.makedirs(base_output_dir, exist_ok=True)
    crawl_results = []

    async with AsyncWebCrawler() as crawler:
        for i, url in enumerate(urls, 1):
            print(f"\n{'#'*100}")
            print(f"CRAWL {i}/{len(urls)}: {url}")
            print(f"{'#'*100}")
            
            result = await crawl_single_url(
                crawler, 
                url, 
                base_output_dir=base_output_dir,
                delay_between_requests=delay_between_requests
            )
            crawl_results.append(result)

            if i < len(urls) and delay_between_crawls > 0:
                print(f"\n Wait {delay_between_crawls} seconds before next crawl.")
                await asyncio.sleep(delay_between_crawls)

    return crawl_results

async def main():
    urls_to_crawl = [
        "https://techcrunch.com/category/climate/",
        "https://techcrunch.com/category/transportation/",
        "https://techcrunch.com/category/startups/"
    ]
    base_output_dir = "techcrunch_crawl_output"  # Changed output directory name for clarity
    results = await crawl_multiple_urls(urls=urls_to_crawl, base_output_dir=base_output_dir)
    
    # Print summary of all crawls
    print(f"\n{'='*100}")
    print("FINAL CRAWL SUMMARY")
    print(f"{'='*100}")
    
    total_pages = sum(r['total_pages'] for r in results)
    total_saved = sum(r['saved_count'] for r in results)
    total_duration = sum(r['duration'] for r in results)
    
    print(f"URLs crawled: {len(results)}")
    print(f"Total pages found: {total_pages}")
    print(f"Total pages saved: {total_saved}")
    print(f"Total duration: {total_duration:.2f} seconds")
    print(f"Success rate: {sum(1 for r in results if r['success'])}/{len(results)}")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(main())