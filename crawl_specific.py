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

async def main(url):
    # Parse the starting URL to get the base domain
    parsed_start_url = urlparse(url)
    base_domain = parsed_start_url.netloc # canarymedia.com
    focused_path = parsed_start_url.path # /articles/solar
    scheme = parsed_start_url.scheme #http or https
    base_domain_path = base_domain + focused_path # canarymedia.com/articles/solar


    print(base_domain)
    print(focused_path)
    print(scheme)
    print(base_domain_path)
    
    # Create a filter chain with domain and pattern filters
    filter_chain = FilterChain([
        # Domain filter - stays within the same domain
        DomainFilter(
            allowed_domains=[base_domain],  # Only crawl within the starting domain
        ),
        
        # URL pattern filter - include only article/blog pages
        URLPatternFilter(
            patterns=[
                f"*{base_domain}{focused_path}*",                    # Anything containing this path
                f"*{focused_path}/p[0-9]*",                          # Numbered pagination
                f"*{focused_path}?*page=*",                          # Query param pagination
            ],
        ),
        
        # Content type filter - only HTML content
        ContentTypeFilter(
            allowed_types=["text/html"],
            check_extension=True
        )
    ])
    
    # Configure markdown generation with pruning filter
    markdown_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.48,  # Relevance threshold (0.0 to 1.0)
            threshold_type="dynamic",  # or "dynamic" for adaptive threshold
        ),
        options={
            "ignore_links": False,
            "citations": True
        }
    )
    
    # Configure the deep crawl strategy with filters
    config = CrawlerRunConfig(
        deep_crawl_strategy=BFSDeepCrawlStrategy(
            max_depth=5,
            filter_chain=filter_chain,  # Apply the filter chain
            include_external=False,  # Don't follow external links
        ),
        scraping_strategy=LXMLWebScrapingStrategy(),
        markdown_generator=markdown_generator,  # Add pruning through markdown generator
        verbose=True,
        # Additional crawl configuration
        exclude_external_links=True,  # Remove external links from content
        excluded_tags=['nav', 'footer', 'header', 'aside'],  # Skip navigation elements
    )

    async with AsyncWebCrawler() as crawler:
        results = await crawler.arun(url, config=config)
        print(f"Crawled {len(results)} pages in total")

        # Track statistics
        filtered_count = 0
        saved_count = 0

        # Access individual results
        for i, result in enumerate(results):
            print(f"URL: {result.url}")
            print(f"Status: {result.status_code}")
            
            # Check if content was successfully extracted
            if result.success and result.markdown:
                # Use filtered markdown if available, otherwise raw markdown
                content = result.markdown.fit_markdown or result.markdown.raw_markdown
                
                # Only save if content meets minimum threshold
                if content and len(content.strip()) > 100:  # Minimum content length
                    # Create a clean filename from the URL
                    parsed_url = urlparse(result.url)
                    
                    # Create filename
                    filename = parsed_url.netloc + parsed_url.path
                    filename = filename.replace('/', '_').replace(':', '').replace('.', '_')
                    if not filename:
                        filename = f"page_{i}"
                    filename = f"{filename}.md"

                    # Save the markdown content
                    os.makedirs("saved_md", exist_ok=True)
                    with open(f"saved_md/{filename}", "w", encoding="utf-8") as f:
                        f.write(f"# {result.url}\n\n")
                        f.write(f"Status: {result.status_code}\n")
                        f.write(f"Crawl Depth: {result.metadata.get('depth', 0)}\n\n")
                        f.write("---\n\n")
                        f.write(content)
                    
                    saved_count += 1
                    print(f"  ✓ Saved: {filename}")
                else:
                    filtered_count += 1
                    print(f"  ✗ Filtered out (insufficient content)")
            else:
                print(f"  ✗ Failed or no content")
        
        print(f"\nSummary:")
        print(f"  Total pages crawled: {len(results)}")
        print(f"  Pages saved: {saved_count}")
        print(f"  Pages filtered: {filtered_count}")

if __name__ == "__main__":
    url = "https://www.canarymedia.com/articles/solar"
    asyncio.run(main(url))