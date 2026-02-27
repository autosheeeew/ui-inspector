"""
Debug API responses
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("=" * 70)
print("Debug API Responses")
print("=" * 70)

# 1. Get devices
print("\n1. Getting devices...")
response = requests.get(f"{BASE_URL}/devices")
print(f"Status Code: {response.status_code}")
devices = response.json()
print(f"Response: {json.dumps(devices, indent=2)}")

if not devices:
    print("⚠️  No devices connected")
    exit(0)

serial = devices[0]['serial']
print(f"\nUsing device: {serial}")

# 2. Dump UI hierarchy
print("\n2. Dumping UI hierarchy...")
response = requests.get(f"{BASE_URL}/dump/{serial}")
print(f"Status Code: {response.status_code}")
print(f"Response Type: {type(response.text)}")

try:
    dump_result = response.json()
    print(f"Response Keys: {dump_result.keys()}")
    print(f"Response: {json.dumps(dump_result, indent=2)[:500]}...")  # First 500 chars
    
    # Save full response
    with open('debug_api_response.json', 'w') as f:
        json.dump(dump_result, f, indent=2)
    print(f"\n✅ Full response saved to: debug_api_response.json")
    
except Exception as e:
    print(f"❌ Error parsing JSON: {e}")
    print(f"Raw response: {response.text[:500]}")

print("\n" + "=" * 70)
