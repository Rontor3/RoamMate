from mcp.tools import tool
import requests

@tool()
def get_current_location() -> str:
    """
    Returns the user's current location based on IP address.
    """
    try:
        response = requests.get("https://ipinfo.io/json")
        data = response.json()
        city = data.get("city", "")
        region = data.get("region", "")
        country = data.get("country", "")
        return f"{city}, {region}, {country}".strip(", ")
    except Exception as e:
        return f"Could not fetch location. Error: {e}"
