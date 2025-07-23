import requests

response = requests.get("https://ipinfo.io/json")
print(response.status_code)   # Check if 200 OK
print(response.json())        # Print the actual data
