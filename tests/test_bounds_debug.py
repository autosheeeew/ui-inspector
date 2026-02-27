"""
Dump and inspect XML bounds
"""
import subprocess
import re

# Dump UI
subprocess.run(['adb', 'shell', 'uiautomator', 'dump', '/sdcard/window_dump.xml'])
result = subprocess.run(['adb', 'shell', 'cat', '/sdcard/window_dump.xml'], 
                       capture_output=True, text=True)

xml = result.stdout
print(xml)
# 查找 app_bottom_bar 相关的元素
pattern = r'<node[^>]*resource-id="jp\.co\.rakuten\.slide:id/app_bottom_bar"[^>]*>'
matches = re.findall(pattern, xml)

print("Found app_bottom_bar elements:")
print("="*70)
for i, match in enumerate(matches):
    print(f"\nMatch {i+1}:")
    print(match)
    
    # 提取 bounds
    bounds_match = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', match)
    if bounds_match:
        x1, y1, x2, y2 = map(int, bounds_match.groups())
        print(f"Bounds: [{x1},{y1}][{x2},{y2}]")
        print(f"Size: {x2-x1} × {y2-y1}")

# 查找该区域内的所有元素
print("\n" + "="*70)
print("All elements in bottom area (y > 2500):")
print("="*70)

pattern = r'<node[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*class="([^"]+)"[^>]*>'
matches = re.findall(pattern, xml)

for match in matches:
    x1, y1, x2, y2, class_name = match
    y1, y2 = int(y1), int(y2)
    if y1 > 2500:
        print(f"{class_name.split('.')[-1]}: [{x1},{y1}][{x2},{y2}]")
