from fastmcp import tool
import asyncio
import asyncpraw
import time
from collections import Counter
import os
#from huggingface_hub import InferenceClient
import logging
import time
import requests
import json
import tiktoken
import aiohttp

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    if load_dotenv():
        logger.info("Loaded environment variables from .env file")
    else:
        logger.warning(".env file not found or not loaded.")
except ImportError:
    logger.warning("python-dotenv not installed. Please install it or set environment variables manually.")

# Create MCP server instance
#mcp = FastMCP("SocialTools")

# Reddit API credentials (replace with your real credentials or load from env)
CLIENT_ID = "-HzPQ6ejtqhohQGFFqqI-w"
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
USER_AGENT = "our_platform:roam_mate:v1.0 (by u/Admirable-Star-1447)"

API_KEY=os.getenv("GROQ_API")
URL="https://api.groq.com/openai/v1/chat/completions"

# Check if credentials are available
if not CLIENT_SECRET:
    logger.error("REDDIT_CLIENT_SECRET environment variable is not set!")
    logger.error("Please set it with: export REDDIT_CLIENT_SECRET='your_secret_here'")

#HF_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
#MODEL = "aws-prototyping/MegaBeam-Mistral-7B-512k"  # Change to your preferred small instruct model




import asyncio
from collections import Counter
import logging
import asyncpraw
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



async def get_reddit_insights(queries: List[str], post_limit: int = 15) -> Dict[str, list]:
    # ---------------- Input Validation ---------------- #
    if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
        raise ValueError("❌ 'queries' must be a list of strings.")
    if not isinstance(post_limit, int) or post_limit <= 0:
        raise ValueError("❌ 'post_limit' must be a positive integer.")

    # ---------------- Reddit Client ---------------- #
    try:
        reddit = asyncpraw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT
        )
        # Optional: force read-only to avoid accidental posting
        reddit.read_only = True
        logger.info("✅ Reddit client initialized successfully.")
    except Exception as e:
        logger.exception("❌ Failed to initialize Reddit client.")
        raise e
    semaphore = asyncio.Semaphore(3)
    subreddit_counter = Counter()
    all_submissions = []

    # ---------------- Search Query ---------------- #
    async def search_query(query: str, time_filter: str):
        submissions = []
        async with semaphore:
            try:
                subreddit = await reddit.subreddit("all")
                logger.info(f"🔍 Searching query: {query} | time_filter: {time_filter}")
                search_results = subreddit.search(
                    query,
                    sort="relevance",
                    limit=post_limit,
                    time_filter=time_filter
                )
                found = False
                async for submission in search_results:
                    found = True
                    try:
                        subreddit_name = getattr(submission.subreddit, "display_name", "Unknown")
                        subreddit_counter[subreddit_name] += 1
                        submissions.append({
                            "submission": submission,
                            "body": getattr(submission,"body","[No Title]"),
                            "subreddit_name": subreddit_name,
                            "score": getattr(submission, "score", 0),
                            "title": getattr(submission, "title", "[No Title]")
                        })
                        logger.debug(f"✨ Found: {submission.title}")
                    except Exception as inner_e:
                        logger.error(f"⚠️ Error processing submission: {inner_e}")
                if not found:
                    logger.warning(f"⚠️ No results found for query '{query}' with filter '{time_filter}'")
            except Exception as e:
                logger.error(f"❌ Error in query '{query}': {e}")
        return submissions

    # Run searches for both time filters
    try:
        search_tasks = [search_query(q, "all") for q in queries] + [search_query(q, "year") for q in queries]
        queries_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    except Exception as e:
        logger.exception("❌ Error while executing search tasks.")
        await reddit.close()
        raise e

    # Collect all submissions
    for result in queries_results:
        if isinstance(result, Exception):
            logger.error(f"⚠️ Search task failed: {result}")
        elif isinstance(result, list):
            all_submissions.extend(result)

    if not all_submissions:
        logger.warning("⚠️ No submissions found for any query.")
    # ---------------- Filter Top Subreddits ---------------- #
    top_subreddits = [name for name, _ in subreddit_counter.most_common(5)]
    logger.info(f"🎯 Top 5 subreddits across queries: {top_subreddits}")

    filtered_submissions = [sub for sub in all_submissions if sub["subreddit_name"] in top_subreddits]
    filtered_submissions.sort(key=lambda x: x["score"], reverse=True)
    filtered_submissions = filtered_submissions[:20]
    results = {"all_time_best": [], "recent_trends": []}

    # ---------------- Comments Fetcher ---------------- #
    async def get_limited_comments(submission, max_comments=4):
        try:
            await asyncio.wait_for(submission.load(), timeout=15)
            await submission.comments.replace_more(limit=0)
            comments = []
            for comment in submission.comments.list()[:10]:
                if hasattr(comment, "body") and len(comments) < max_comments:
                    comments.append(comment.body[:200])
                if len(comments) >= max_comments:
                    break
            return comments
        except asyncio.TimeoutError:
            logger.error(f"⏳ Timeout while loading comments for {getattr(submission, 'id', 'unknown')}")
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching comments for {getattr(submission, 'id', 'unknown')}: {e}")
            return []

    # ---------------- Process Submissions ---------------- #
    batch_size = 3
    for i in range(0, len(filtered_submissions), batch_size):
        batch = filtered_submissions[i:i + batch_size]

        async def process_post(post_data):
            submission = post_data["submission"]
            try:
                comments = await get_limited_comments(submission)
                post_info = {
                    "title": getattr(submission, "title", "[No Title]"),
                    "body": getattr(submission,"body","[No Title]"),
                    "score": getattr(submission, "score", 0),
                    "url": getattr(submission, "url", ""),
                    "id": getattr(submission, "id", ""),
                    "created_utc": getattr(submission, "created_utc", None),
                    "subreddit": getattr(submission.subreddit, "display_name", "Unknown"),
                    "author": str(submission.author) if submission.author else "[deleted]",
                    "selftext": getattr(submission, "selftext", ""),
                    "relevant_comments": comments,
                }
                formatted = (
                    f"TITLE: {post_info['title']}\n"
                    f"BODY: {post_info['body']}\n"
                    f"SUBREDDIT: r/{post_info['subreddit']}\n"
                    f"SCORE: {post_info['score']}\n"
                    f"TEXT: {post_info['selftext']}\n"
                    f"TOP COMMENTS: {' | '.join(post_info['relevant_comments'])}\n"
                    f"URL: {post_info['url']}"
                )
                return formatted
            except Exception as e:
                logger.error(f"❌ Error processing submission {getattr(submission, 'id', 'unknown')}: {e}")
                return None

        batch_tasks = [process_post(post) for post in batch]
        try:
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"❌ Error processing batch {i//batch_size}: {e}")
            batch_results = []

        for res in batch_results:
            if isinstance(res, Exception):
                logger.error(f"⚠️ Batch task exception: {res}")
            elif isinstance(res, str):
                if len(results["all_time_best"]) < 6:
                    results["all_time_best"].append(res)
                else:
                    results["recent_trends"].append(res)

        #await asyncio.sleep(0.5)  # Be polite to Reddit API

    # ---------------- Close Reddit Client ---------------- #
    try:
        await reddit.close()
        logger.info("✅ Reddit client closed.")
    except Exception as e:
        logger.error(f"⚠️ Error closing Reddit client: {e}")

    return results


def generate_reddit_search_queries(user_prefs) -> list[str]:
    """
    Generate 2-3 relevant Reddit search queries based on user preferences.

    Args:
        user_prefs: dict with at least 'location', optionally 'interests' and 'trip_style'.

    Returns:
        List of up to 3 tailored query strings for Reddit search.
    """
    location = user_prefs.get("location", "").strip()
    interests = user_prefs.get("interests", [])
    trip_style = user_prefs.get("trip_style", "").strip().lower()

    queries = []

    # Always include a general travel query for the location
    if location:
        queries.append(f"travel {location}")

    # Add the most important or first interest as a targeted query
    if interests:
        queries.append(f"best {interests[0]} in {location}")
        if len(interests) > 1:
            queries.append(f"{location} {interests[1]}")
        else:
            queries.append(f"{location} itinerary")
    else:
        # If no interests, add an itinerary or tips query
        queries.append(f"{location} itinerary")
        queries.append(f"food in {location}")

    # Optional: Add a trip style-specific query if not already full
    if trip_style and len(queries) < 3:
        queries.append(f"{trip_style} travel {location}")

    # Limit to 3 queries max
    return queries[:3]


def split_into_batches(user_pref:str,text: str, max_input_tokens: int = 4500, model_name="gpt-4o"):
    """
    Split text into batches of roughly max_input_tokens tokens,
    cutting only at paragraph breaks when possible.
    """


    enc = tiktoken.encoding_for_model(model_name)
    paragraphs = text.split("\n\n")
    batches, current_batch, current_tokens = [], [], 0 

    for para in paragraphs:
        tok_count = len(enc.encode(para))
        # if a single paragraph is too long, fall back to sentence split
        if tok_count > max_input_tokens:
            sentences = para.split(". ")
            for sent in sentences:
                s_tok = len(enc.encode(sent))
                if current_tokens + s_tok > max_input_tokens:
                    batches.append("\n\n".join(current_batch))
                    current_batch, current_tokens = [], 0
                current_batch.append(sent)
                current_tokens += s_tok
        else:
            if current_tokens + tok_count > max_input_tokens:
                batches.append("\n\n".join(current_batch))
                current_batch, current_tokens = [], 0
            current_batch.append(para)
            current_tokens += tok_count

    if current_batch:
        batches.append("\n\n".join(current_batch))
    final_batch=[]    
    for batch in batches:
        final_batch.append(build_llm_prompt(user_pref,batch))
    return batches
async def call_llm(session, prompt):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes Reddit discussions."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 3000  # room for ~3k token output
    }
    async with session.post(URL, headers=headers, json=body) as r:
        return await r.json()    
async def summarize_in_batches(total_data,user_pref):
    batches = split_into_batches(user_pref,total_data)
    async with aiohttp.ClientSession() as session:
        tasks = [
            call_llm(session, f"{chunk}")
            for chunk in (batches)
        ]
        results = await asyncio.gather(*tasks)

    # Extract text from each response and merge
    partials = [r["choices"][0]["message"]["content"] for r in results]
    return "\n\n".join(partials)  
def build_llm_prompt(user_prefs, all_posts_text):
    """
    Build a comprehensive extraction prompt for the Phi-3 model.
    Args:
        user_prefs: dict (user's location, interests, trip style, etc.)
        all_posts_text: list of strings containing Reddit post content
    Returns:
        A formatted prompt string for the LLM
    """
    prefs_text = (
        f"User Preferences:\n"
        f"- Location: {user_prefs.get('location','')}\n"
        f"- Interests: {', '.join(user_prefs.get('interests', []))}\n"
        f"- Trip Style: {user_prefs.get('trip_style', '')}\n"
    )
    instruction = (
        "Your task:\n"
        "Given the following Reddit posts and comments, extract and summarize ONLY:\n"
        "1. Place/Location names (hotels, neighborhoods, attractions, etc.)\n"
        "2. Food/cafe/restaurant reviews or recommendations\n"
        "3. Step-by-step itineraries or trip planning advice\n"
        "Organize your output in clear sections and be concise.\n"
    )
    return f"{prefs_text}\n\n{all_posts_text}\n\n{instruction}\n\n"


@tool(
    name="scrape_and_extract_travel_advice",
    description="Scrapes Reddit for travel advice based on user preferences and subreddit, then extracts insights using a language model.",
    input_schema={
        "type": "object",
        "properties": {
            "user_prefs": {
                "type": "object",
                "description": "User preferences for travel advice extraction.",
                "properties": {
                    "location": {"type": "string", "description": "Preferred travel location."},
                    "interest": {"type": "string", "description": "User interests related to travel."},
                    "trip_style": {"type": "string", "description": "Preferred style of trip."}
                },
                "required": ["location", "interest", "trip_style"],
                "additionalProperties": False
            },
            "post_limit": {
                "type": "integer",
                "description": "The maximum number of posts to retrieve."
            }
        },
        "required": ["user_prefs", "post_limit"]
    }
)
async def scrape_and_extract_travel_advice(user_prefs: dict, post_limit: int) -> dict:
    """Scrape Reddit for travel advice and extract insights using LLM."""
    logger.info(f"Tool called with post_limit: {post_limit}")
    
    try:
        queries = generate_reddit_search_queries(user_prefs)   ##used for extracting the queries from the user preferences
        logger.info(f"Generated queries: {queries}")

        print(f"Queries: {queries}")
        
        try:
            all_posts_text = await get_reddit_insights(queries, post_limit)
        except Exception as e:
            logger.exception("❗ get_reddit_insights failed")
            raise
        #logger.info(f"All posts text: {all_posts_text}")         ##used for getting the posts from the queries
        logger.info(f"Retrieved {len(all_posts_text.get('all_time_best', [])) + len(all_posts_text.get('recent_trends', []))} posts")
        
        if not all_posts_text.get('all_time_best') and not all_posts_text.get('recent_trends'):
            return {"insights": "No Reddit posts found. Please check your Reddit API credentials and try again."}

        logger.info(all_posts_text.keys())
        #prompt = build_llm_prompt(user_prefs, all_posts_text)
            
        total_data='\n\n'.join('\n'.join(v) for _, v in all_posts_text.items())
        logger.info(type(total_data))
        try:
            extraction = await summarize_in_batches(total_data,user_prefs) ##used for extracting the insights from the LLM
        except Exception as e:
            logger.exception("❗ summarize_in_batches ")  
            raise
        return {
                "status": "success",
                "message": "Reddit aggregated data",
                "data":  extraction           # posts is a list/dict of your results
            }
        
    except Exception as e:
        logger.error(f"Error in scrape_and_extract_travel_advice: {e}")
        return {"insights": f"Error occurred while processing: {str(e)}"}   

    


