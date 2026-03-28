import asyncio
import json
import sys

from app.models import TravelIntent, Destination
from app.services.reddit_signals import get_reddit_place_signals

class MockVibe:
    value = "adventure"

async def test_extraction():
    # Construct a sample intent that failed previously
    intent = TravelIntent(
        destination=Destination(city=None, region="North East India"),
        vibe=[MockVibe()],
        interests=["culture"]
    )
    
    print("Fetching reddit extraction for 'North East India'...")
    try:
        result = await get_reddit_place_signals(intent)
        
        print("\n--- EXTRACTED SIGNALS (JSON) ---")
        signals = result.get("place_signals", {})
        if signals:
            print(json.dumps(signals, indent=2))
            print(f"✅ Successfully extracted data for {len(signals)} places!")
        else:
            print("⚠️ No place signals were extracted.")
            
        raw_text = result.get("raw_posts_text", "")
        print(f"\n--- RAW REDDIT TEXT LENGTH: {len(raw_text)} chars ---")
        if len(raw_text) > 0:
            print("✅ Successfully fetched raw posts from Reddit!")
        else:
            print("⚠️ No raw posts were fetched from Reddit.")
            
    except Exception as e:
        print(f"❌ Error during extraction: {e}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
