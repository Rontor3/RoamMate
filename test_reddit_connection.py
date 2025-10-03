#!/usr/bin/env python3
"""
Simple test file to test Reddit API connection
"""
import asyncio
import os
import asyncpraw
from asyncpraw.models import comment_forest
from dotenv import load_dotenv
import traceback


# Load environment variables from .env file
load_dotenv()

# Reddit API credentials
CLIENT_ID = "-HzPQ6ejtqhohQGFFqqI-w"
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
USER_AGENT = "our_platform:roam_mate:v1.0 (by u/Admirable-Star-1447)"

async def test_reddit_connection():
    """Test basic Reddit API connection"""
    print("Testing Reddit API connection...")
    print(f"CLIENT_ID: {CLIENT_ID}")
    print(f"CLIENT_ID: {CLIENT_SECRET}")
    print(f"CLIENT_SECRET: {'*' * len(CLIENT_SECRET) if CLIENT_SECRET else 'NOT SET'}")
    print(f"USER_AGENT: {USER_AGENT}")
    
    if not CLIENT_SECRET:
        print("❌ ERROR: REDDIT_CLIENT_SECRET is not set!")
        return False
    
    try:
        async with asyncpraw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT
        ) as reddit:
            print("✅ Successfully connected to Reddit API")
            
            # Test getting a subreddit
            subreddit = await reddit.subreddit("python")
            print(f"✅ Successfully accessed subreddit: {subreddit.display_name}")
            print(f"Subreddit object: {subreddit}")
            print(f"Subreddit type: {type(subreddit)}")
            
            # Test getting a few posts
            print("Testing post retrieval...")
            count = 0
            async for post in subreddit.hot(limit=3):
                print(f"  - {post.title[:50]}...")
                print(f"    Post object: {post}")
                print(f"    Post type: {type(post)}")
                count += 1
                if count >= 3:
                    break
            
            print(f"✅ Successfully retrieved {count} posts")
            return True
            
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return False

async def test_reddit_search():
    """Test Reddit search functionality"""
    print("\nTesting Reddit search...")
    
    if not CLIENT_SECRET:
        print("❌ ERROR: REDDIT_CLIENT_SECRET is not set!")
        return False
    
    try:
        async with asyncpraw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT
        ) as reddit:
            
            subreddit = await reddit.subreddit("all")
            print("✅ Successfully accessed r/all")
            
            # Test search with simpler query
            query = "Kasol"
            print(f"Searching for: '{query}'")
            
            count = 0
            async for post in subreddit.search(query, sort="top", limit=4):
                if post is None:
                    print("  - Received None post, skipping...")
                    continue
                submission = await reddit.submission(id=post.id)    
                print(f"  - {post.title[:60]}...")
                count += 1
                
                try:
                    # First, just print basic post info (no comments)
                    print(f"    Post ID: {submission.id}")
                    print(f"    Post Title: {submission.title}")
                    print(f"    Post Author: {submission.author}") 
                    print(f"    Post Score: {submission.score}")
                    print(f"    Post URL: {submission.url}")
                    print(f"    Post Created: {submission.created_utc}")
                    print(f"    Post Selftext: {submission.selftext[:100] if post.selftext else 'No text'}...")
                    print(f"    Post comments: {submission.comments}...")
                    #print(f"    Total comments initially: {post.comments.__len__})")
                    #print(f"    Total comments (without fetching): {len(post.comments)}")
                    try:
    # Expand and flatten comments
                        await submission.comments.replace_more(limit=10)
                        comment_list = submission.comments.list()

                        print(f"    ✅ Total comments fetched: {len(comment_list)}")

                        if comment_list:
                            for c in comment_list[:5]:
                                author = c.author if c.author else "[deleted]"
                                print(f"      - {author}: {c.body[:80]}...")
                        else:
                            print("    ⚠️ No comments found for this post.")

                    except Exception as e:
                        print(f"    Error while fetching comments: {e}")
                        traceback.print_exc()

                except Exception as e:   # <-- Python now says "expected except/finally"
                    print(e)
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return False

async def main():
    """Run all tests"""
    print("=" * 50)
    print("REDDIT API CONNECTION TEST")
    print("=" * 50)
    
    # Test basic connection
    connection_ok = await test_reddit_connection()
    
    if connection_ok:
        # Test search functionality
        search_ok = await test_reddit_search()
        
        if search_ok:
            print("\n🎉 ALL TESTS PASSED!")
            print("Your Reddit API credentials are working correctly.")
        else:
            print("\n⚠️  Connection works but search failed.")
    else:
        print("\n❌ CONNECTION FAILED!")
        print("Please check your Reddit API credentials.")
        print("\nTo fix:")
        print("1. Go to https://www.reddit.com/prefs/apps")
        print("2. Check your app's CLIENT_ID and CLIENT_SECRET")
        print("3. Update your .env file with the correct values")

if __name__ == "__main__":
    asyncio.run(main()) 