"""
Test XPath query with class attribute
"""
from xml_parser import XMLParser

# Sample XML with node tags but class attributes
xml_content = """
<hierarchy rotation="0">
  <node index="0" class="android.widget.FrameLayout" bounds="[0,0][1080,1920]">
    <node index="0" class="android.widget.LinearLayout" bounds="[0,0][1080,200]">
      <node index="0" class="android.widget.TextView" 
            text="Hello World" 
            resource-id="com.example.app:id/title" 
            content-desc="Title text"
            bounds="[20,50][500,150]" />
      <node index="1" class="android.widget.Button" 
            text="Click Me" 
            resource-id="com.example.app:id/button" 
            bounds="[20,200][500,300]" />
    </node>
  </node>
</hierarchy>
"""

print("=" * 70)
print("Testing XPath Query with Class Attributes")
print("=" * 70)

# Test 1: Query by class name
print("\n1. Query by class name: //android.widget.Button")
result = XMLParser.query_xpath(xml_content, "//android.widget.TextView")
print(f"Success: {result['success']}")
print(f"Count: {result['count']}")
if result['matches']:
    match = result['matches'][0]
    print(f"Tag: {match['tag']}")  # Should be "android.widget.TextView"
    print(f"Text: {match['attributes'].get('text')}")

# Test 2: Query by resource-id
print("\n2. Query by resource-id: //*[@resource-id='com.example.app:id/button']")
result = XMLParser.query_xpath(xml_content, "//*[@resource-id='com.example.app:id/button']")
print(f"Success: {result['success']}")
print(f"Count: {result['count']}")
if result['matches']:
    match = result['matches'][0]
    print(f"Tag: {match['tag']}")  # Should be "android.widget.Button"
    print(f"Text: {match['attributes'].get('text')}")

# Test 3: Query by text
print("\n3. Query by text: //*[@text='Hello World']")
result = XMLParser.query_xpath(xml_content, "//*[@text='Hello World']")
print(f"Success: {result['success']}")
print(f"Count: {result['count']}")
if result['matches']:
    match = result['matches'][0]
    print(f"Tag: {match['tag']}")  # Should be "android.widget.TextView"
    print(f"Resource ID: {match['attributes'].get('resource-id')}")

print("\n" + "=" * 70)
print("Test Complete!")
print("=" * 70)
