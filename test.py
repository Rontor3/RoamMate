import asyncpraw
import asyncio

async def main():
    async with asyncpraw.Reddit(
        client_id="oFMO4ZLCcBlIBA-mm8S0Lg",
        client_secret="btVC-TdjvvFIPdbQo5mqogYdWdULTw",
        user_agent="your_platform:roam_mate:v1.0 (by u/Admirable-Star-1447)"
    ) as reddit:
        subreddit = await reddit.subreddit("Kasol")
        async for submission in subreddit.hot(limit=5):
            print(f"Post Title: {submission.title}")
            # Load comments
            await submission.load()  # Ensure submission is fully loaded (optional but recommended)

            # Replace 'MoreComments' objects to get all comments
            await submission.comments.replace_more(limit=0)

            # Iterate over all comments (flat)
            for comment in submission.comments.list():
                # You can filter deleted or removed comments
                if comment.body and comment.body.lower() not in ['[deleted]', '[removed]']:
                    print(f"  Comment by {comment.author}: {comment.body[:100]}")  # Print first 100 chars

            print("\n" + "-"*50 + "\n")



asyncio.run(main())
