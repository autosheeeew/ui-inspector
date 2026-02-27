"""
Test XPath query with real device XML
"""
from xml_parser import XMLParser

# 使用你之前提供的真实 XML（简化版）
real_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" class="android.widget.FrameLayout" bounds="[0,0][1440,2621]">
    <node index="0" class="android.widget.LinearLayout" bounds="[0,0][1440,2621]">
      <node index="0" class="android.widget.FrameLayout" bounds="[0,171][1440,2621]">
        <node index="0" class="android.widget.LinearLayout" bounds="[0,171][1440,2621]">
          <node index="0" class="android.widget.FrameLayout" bounds="[0,171][1440,2621]">
            <node index="0" class="android.view.ViewGroup" bounds="[0,171][1440,2621]">
              <node index="4" class="android.view.View" bounds="[1132,381][1384,549]">
                <node index="0" text="ログイン" class="android.widget.TextView" bounds="[1188,441][1328,490]" />
                <node index="1" text="" resource-id="" class="android.widget.Button" bounds="[1132,402][1384,528]" />
              </node>
            </node>
          </node>
        </node>
      </node>
    </node>
  </node>
</hierarchy>
"""

print("=" * 70)
print("Testing XPath Query with Real Device XML")
print("=" * 70)

# Test 1: Query Button
print("\n1. Query: //android.widget.Button")
result = XMLParser.query_xpath(real_xml, "//android.widget.Button")
print(f"   Success: {result['success']}")
print(f"   Count: {result['count']}")
if result['matches']:
    match = result['matches'][0]
    print(f"   Tag: {match['tag']}")
    print(f"   Bounds: {match['bounds_computed']}")
else:
    print(f"   Error: {result.get('error', 'No matches found')}")

# Test 2: Query TextView with text
print("\n2. Query: //android.widget.TextView[@text='ログイン']")
result = XMLParser.query_xpath(real_xml, "//android.widget.TextView[@text='ログイン']")
print(f"   Success: {result['success']}")
print(f"   Count: {result['count']}")
if result['matches']:
    match = result['matches'][0]
    print(f"   Tag: {match['tag']}")
    print(f"   Text: {match['attributes'].get('text')}")

# Test 3: Query all clickable elements
print("\n3. Query: //*[@clickable='true']")
result = XMLParser.query_xpath(real_xml, "//*[@clickable='true']")
print(f"   Success: {result['success']}")
print(f"   Count: {result['count']}")

# Test 4: Query ViewGroup
print("\n4. Query: //android.view.ViewGroup")
result = XMLParser.query_xpath(real_xml, "//android.view.ViewGroup")
print(f"   Success: {result['success']}")
print(f"   Count: {result['count']}")

print("\n" + "=" * 70)
print("Test Complete!")
print("=" * 70)
