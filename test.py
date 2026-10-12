from curl_cffi import requests

r = requests.get(
    "https://api.wallapop.com/api/v3/search",
    params={"keywords": "iphone 13", "order_by": "newest",
            "source": "search_box", "latitude": 40.4168, "longitude": -3.7038},
    headers={"X-DeviceOS": "0"},
    impersonate="chrome",
)
print(r.json().get("meta"))