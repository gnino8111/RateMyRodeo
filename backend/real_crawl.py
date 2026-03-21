import asyncio
from crawl4ai import AsyncWebCrawler
import requests
from bs4 import BeautifulSoup
import time

async def search_gmu_reddit(prof):
    """Search GMU subreddit for posts about a specific professor"""
    search_url = f"https://www.reddit.com/r/gmu/search.json?q={prof}&type=link&sort=new"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(search_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            posts = []
            for child in data['data']['children']:
                post = child['data']
                posts.append({
                    'title': post['title'],
                    'url': post['url'],
                    'permalink': f"https://www.reddit.com{post['permalink']}"
                })
            return posts
        else:
            print(f"Search failed with status code: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error during search: {e}")
        return []

async def crawl_post(url, crawler):
    """Crawl a single Reddit post and return markdown"""
    try:
        result = await crawler.arun(url=url)
        if result.success:
            return result.markdown
        else:
            print(f"Failed to crawl {url}: {result.error_message}")
            return None
    except Exception as e:
        print(f"Error crawling {url}: {e}")
        return None

async def main():
    # Variable to search for
    prof = "Wassim Masri"  # You can change this value
    
    print(f"Searching GMU subreddit for: {prof}")
    
    # Search for posts about the professor
    posts = await search_gmu_reddit(prof)
    
    if not posts:
        print(f"No posts found for {prof}")
        return
    
    print(f"Found {len(posts)} posts about {prof}")
    
    # Initialize the crawler
    async with AsyncWebCrawler() as crawler:
        # Prepare single output file
        filename = f"gmu_{prof.replace(' ', '_').lower()}_combined.md"
        
        with open(filename, "w", encoding="utf-8") as file:
            file.write(f"# Comments about {prof} from r/gmu\n\n")
            file.write(f"Generated from {len(posts)} search results\n\n")
            
            # Process each post
            for i, post in enumerate(posts, 1):
                print(f"\n--- Processing post {i}/{len(posts)}: {post['title']} ---")
                
                # Crawl the post
                markdown = await crawl_post(post['permalink'], crawler)
                
                if markdown:
                    # Add separator and post title
                    if i > 1:
                        file.write("\n\n***\n\n")
                    
                    file.write(f"## Post: {post['title']}\n\n")
                    file.write(f"Source: {post['permalink']}\n\n")
                    file.write(markdown)
                    
                    print(f"Added content from post {i} to {filename}")
                else:
                    print(f"Could not generate markdown for post {i}")
                
                # Be respectful to servers
                await asyncio.sleep(1)
        
        print(f"\nAll content combined and saved to: {filename}")

# Run the async function
if __name__ == "__main__":
    asyncio.run(main())
