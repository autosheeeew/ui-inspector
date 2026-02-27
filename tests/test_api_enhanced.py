"""
Test enhanced API endpoints
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("=" * 70)
print("Testing Enhanced API Endpoints")
print("=" * 70)

# 1. Get devices
print("\n1. Getting devices...")
response = requests.get(f"{BASE_URL}/devices")
devices = response.json()
print(f"✅ Found {len(devices)} device(s)")

if not devices:
    print("⚠️  No devices connected. Please connect a device.")
    exit(0)

serial = devices[0]['serial']
platform = devices[0]['platform']
print(f"   Using device: {serial} ({platform})")

# 2. Dump UI hierarchy (enhanced)
print("\n2. Dumping UI hierarchy (enhanced)...")
response = requests.get(f"{BASE_URL}/dump/{serial}")
dump_result = response.json()

if dump_result['success']:
    print(f"✅ Dump successful")
    print(f"   Platform: {dump_result['platform']}")
    print(f"   Total nodes: {dump_result['total_nodes']}")
    
    # Save for inspection
    with open('test_api_dump.json', 'w') as f:
        json.dump(dump_result, f, indent=2)
    print(f"   Saved to: test_api_dump.json")
    
    # Find a clickable element
    def find_clickable(node):
        if node['attributes'].get('clickable') == 'true':
            return node
        for child in node.get('children', []):
            result = find_clickable(child)
            if result:
                return result
        return None
    
    clickable = find_clickable(dump_result['hierarchy'])
    
    if clickable:
        print(f"\n3. Found clickable element:")
        print(f"   Tag: {clickable['tag']}")
        print(f"   Text: {clickable['attributes'].get('text', 'N/A')}")
        print(f"   Resource ID: {clickable['attributes'].get('resource-id', 'N/A')}")
        print(f"   Node Path: {clickable['node_path']}")
        
        # Test get element info
        print(f"\n4. Getting element info by path...")
        response = requests.post(
            f"{BASE_URL}/element/info",
            json={
                "serial": serial,
                "node_path": clickable['node_path']
            }
        )
        
        element_info = response.json()
        
        if element_info['success']:
            print(f"✅ Element info retrieved")
            selectors = element_info['element']['selectors']
            
            print(f"\n   Generated Selectors:")
            print(f"   - ID: {selectors.get('id')}")
            print(f"   - Accessibility ID: {selectors.get('accessibility_id')}")
            print(f"   - XPath: {selectors['xpath_absolute']}")
            
            if platform == 'android':
                print(f"   - UiAutomator: {selectors['uiautomator'][0] if selectors['uiautomator'] else 'N/A'}")
        
        # Test find by coordinate
        bounds = clickable['attributes'].get('bounds_computed')
        if bounds:
            center_x = bounds['x'] + bounds['w'] // 2
            center_y = bounds['y'] + bounds['h'] // 2
            
            print(f"\n5. Finding element by coordinate ({center_x}, {center_y})...")
            response = requests.post(
                f"{BASE_URL}/element/find-by-coordinate",
                json={
                    "serial": serial,
                    "x": center_x,
                    "y": center_y
                }
            )
            
            coord_result = response.json()
            
            if coord_result['success']:
                print(f"✅ Found element at coordinate")
                print(f"   Tag: {coord_result['element']['tag']}")
                print(f"   Text: {coord_result['element']['attributes'].get('text', 'N/A')}")
    
else:
    print(f"❌ Dump failed: {dump_result.get('error')}")

print("\n" + "=" * 70)
print("Test Complete!")
print("=" * 70)
