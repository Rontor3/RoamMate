# Google Custom Search API Setup

Add these credentials to your `.env` file:

```bash
# Google Custom Search API
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_cx_id_here
```

## How to Get Credentials

### 1. Google API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable "Custom Search API"
4. Go to "Credentials" → "Create Credentials" → "API Key"
5. Copy your API key

### 2. Search Engine ID (CX)
1. Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Click "Add" to create a new search engine
3. Set "Sites to search" to "Search the entire web"
4. Create and get your Search Engine ID (cx parameter)

The app will work with a fallback message if these aren't configured, but for best results, add them to your `.env` file.
