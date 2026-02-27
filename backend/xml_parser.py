"""
XML Parser Module
Enhanced version with selector generation for both Android and iOS
"""
from lxml import etree
from typing import Dict, List, Optional, Any
import logging
import traceback

logger = logging.getLogger(__name__)


class XMLParser:
    """Parse and query UI hierarchy XML with selector generation"""

    @staticmethod
    def convert_node_to_class_tags(xml_content: str) -> str:
        """
        Convert <node class="xxx"> to <xxx> format
        
        This transforms UIAutomator XML format to a more standard format
        where the class attribute becomes the tag name.
        
        Before:
            <node class="android.widget.Button" text="Click" />
        
        After:
            <android.widget.Button text="Click" />
        
        Args:
            xml_content: Original XML string with <node> tags
        
        Returns:
            Converted XML string with class names as tags
        """
        try:
            from lxml import etree
            
            # Parse XML
            root = etree.fromstring(xml_content.encode('utf-8'))
            
            # Recursively convert nodes
            def convert_node(element):
                """Recursively convert node tags to class names"""
                # Get class attribute
                class_name = element.attrib.get('class')
                
                if class_name and element.tag == 'node':
                    # Create new element with class name as tag
                    new_element = etree.Element(class_name, attrib=element.attrib)
                    
                    # Copy text
                    new_element.text = element.text
                    new_element.tail = element.tail
                    
                    # Recursively convert children
                    for child in element:
                        converted_child = convert_node(child)
                        new_element.append(converted_child)
                    
                    return new_element
                else:
                    # Keep original element (like <hierarchy>)
                    new_element = etree.Element(element.tag, attrib=element.attrib)
                    new_element.text = element.text
                    new_element.tail = element.tail
                    
                    # Recursively convert children
                    for child in element:
                        converted_child = convert_node(child)
                        new_element.append(converted_child)
                    
                    return new_element
            
            # Convert root
            converted_root = convert_node(root)
            
            # Convert back to string
            converted_xml = etree.tostring(
                converted_root, 
                encoding='utf-8', 
                xml_declaration=True,
                pretty_print=True
            ).decode('utf-8')
            
            logger.info("Successfully converted XML from <node> to <class> format")
            return converted_xml
            
        except Exception as e:
            logger.error(f"Error converting XML format: {e}")
            logger.error(traceback.format_exc())
            # Return original XML if conversion fails
            return xml_content

    
    @staticmethod
    def _xpath_escape(value: str) -> str:
        """Return an XPath-safe quoted string for the given value."""
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        # Both quote types present → use XPath concat()
        parts = value.split("'")
        joined = ", \"'\", ".join(f"'{p}'" for p in parts)
        return f"concat({joined})"

    @staticmethod
    def _generate_xpath_absolute(node, root, platform: str = 'android') -> str:
        """
        Generate the shortest XPath that uniquely identifies `node` in the tree.

        Search order:
          1. self attrs:       //tag[@attr], //*[@attr], //tag[@a1][@a2]
          2. descendant attrs: //tag[.//desc_tag[@attr=val]]  (any depth)
          3. sibling attrs:    //sib[@attr]/following-or-preceding-sibling::tag[n]
          4. parent attrs:     //parent[@attr]//tag  (or positional)
          5. uncle attrs:      //uncle[@attr]/sibling::parent[n]//tag
          6. cousin attrs:     //cousin[@attr]/parent::sib/sibling::tag[n]
          (repeat 2-6 walking one level up per iteration)
          7. structural fallback: /hierarchy/Type[1]/Type[2]/…
        """
        try:
            escape = XMLParser._xpath_escape
            tag    = node.tag
            attrs  = dict(node.attrib)
            is_ios = platform == 'ios'

            # ── inner helpers ─────────────────────────────────────────────────

            def unique_for_node(expr: str) -> bool:
                try:
                    m = root.xpath(expr)
                    return len(m) == 1 and m[0] is node
                except Exception:
                    return False

            def id_attrs_for(ea: dict) -> List[tuple]:
                keys = ['name', 'label', 'value'] if is_ios \
                       else ['resource-id', 'content-desc', 'text']
                return [(k, ea[k]) for k in keys if ea.get(k, '').strip()]

            def unique_ref(elem) -> Optional[str]:
                """Return //tag[@attr=val] only if it uniquely identifies elem."""
                for k, v in id_attrs_for(dict(elem.attrib)):
                    expr = f"//{elem.tag}[@{k}={escape(v)}]"
                    try:
                        m = root.xpath(expr)
                        if len(m) == 1 and m[0] is elem:
                            return expr
                    except Exception:
                        pass
                return None

            def sibling_axis(target_elem, anchor_elem) -> tuple:
                """
                Both elements must be siblings (same parent).
                Returns (axis_name, count) to navigate from anchor to target.
                  anchor before target → ('following-sibling', n)
                  anchor after  target → ('preceding-sibling', n)
                """
                parent = anchor_elem.getparent()
                if parent is None:
                    return None, 0
                sibs = list(parent)
                try:
                    a_pos = sibs.index(anchor_elem)
                    t_pos = sibs.index(target_elem)
                except ValueError:
                    return None, 0
                t_tag = target_elem.tag
                if a_pos < t_pos:
                    count = sum(1 for s in sibs[a_pos + 1:t_pos + 1] if s.tag == t_tag)
                    return 'following-sibling', count
                else:
                    count = sum(1 for s in sibs[t_pos:a_pos] if s.tag == t_tag)
                    return 'preceding-sibling', count

            def qualify_under(anchor_expr: str, anchor_elem) -> Optional[str]:
                """
                Navigate from a uniquely-identified ancestor down to `node`.
                Tries: attr qualifier → tag-only → positional.
                """
                for k, v in node_id:
                    expr = f"{anchor_expr}//{tag}[@{k}={escape(v)}]"
                    if unique_for_node(expr):
                        return expr
                expr = f"{anchor_expr}//{tag}"
                if unique_for_node(expr):
                    return expr
                try:
                    desc = anchor_elem.xpath(f".//{tag}")
                    if node in desc:
                        idx = desc.index(node) + 1
                        expr = f"({anchor_expr}//{tag})[{idx}]"
                        if unique_for_node(expr):
                            return expr
                except Exception:
                    pass
                return None

            # ── pre-compute node's own identifying attrs ───────────────────────
            node_id = id_attrs_for(attrs)

            # ── Strategy 1: self attributes ───────────────────────────────────
            # 1a: //tag[@attr=val]
            for k, v in node_id:
                expr = f"//{tag}[@{k}={escape(v)}]"
                if unique_for_node(expr):
                    return expr
            # 1b: //*[@attr=val]
            for k, v in node_id:
                expr = f"//*[@{k}={escape(v)}]"
                if unique_for_node(expr):
                    return expr
            # 1c: //tag[@a1=v1][@a2=v2]
            for i in range(len(node_id)):
                for j in range(i + 1, len(node_id)):
                    k1, v1 = node_id[i]; k2, v2 = node_id[j]
                    expr = f"//{tag}[@{k1}={escape(v1)}][@{k2}={escape(v2)}]"
                    if unique_for_node(expr):
                        return expr

            # ── Strategies 2-6: axis-based, expanding outward level by level ──
            # At each iteration `target` is the element whose local context we search.
            # Initially target == node; after each pass target moves one level up.

            target = node
            for _depth in range(8):
                parent = target.getparent()
                if parent is None or parent is root:
                    break

                siblings = list(parent)

                # ── 2: any descendant of target has unique attrs ──────────────
                #    //target_tag[.//desc_tag[@attr=val]]
                #    (covers direct children, grandchildren, etc.)
                for desc in target.iter():
                    if desc is target:
                        continue
                    for k, v in id_attrs_for(dict(desc.attrib)):
                        esc_v = escape(v)
                        # Specific-tag predicate
                        expr = f"//{target.tag}[.//{desc.tag}[@{k}={esc_v}]]"
                        if unique_for_node(expr):
                            return expr
                        if target is not node:
                            result = qualify_under(expr, target)
                            if result:
                                return result
                        # Wildcard predicate (shorter when tag is irrelevant)
                        expr_w = f"//{target.tag}[.//*[@{k}={esc_v}]]"
                        if unique_for_node(expr_w):
                            return expr_w
                        if target is not node:
                            result = qualify_under(expr_w, target)
                            if result:
                                return result

                # ── 3: sibling of target has unique attrs ─────────────────────
                #    //sib[@attr]/following-or-preceding-sibling::target_tag[n]
                for sib in siblings:
                    if sib is target:
                        continue
                    ref = unique_ref(sib)
                    if ref is None:
                        continue
                    axis, count = sibling_axis(target, sib)
                    if axis and count > 0:
                        expr = f"{ref}/{axis}::{target.tag}[{count}]"
                        if unique_for_node(expr):
                            return expr
                        # target may be an ancestor of node; qualify down
                        if target is not node:
                            result = qualify_under(expr, target)
                            if result:
                                return result

                # ── 4: parent of target has unique attrs ──────────────────────
                #    //parent[@attr]//target  (or positional)
                ref = unique_ref(parent)
                if ref is not None:
                    result = qualify_under(ref, parent)
                    if result:
                        return result

                # ── 5: uncle (parent's sibling) has unique attrs ──────────────
                #    //uncle[@attr]/sibling::parent[n]//target
                grandparent = parent.getparent()
                if grandparent is not None and grandparent is not root:
                    for uncle in grandparent:
                        if uncle is parent:
                            continue
                        ref = unique_ref(uncle)
                        if ref is None:
                            continue
                        axis, count = sibling_axis(parent, uncle)
                        if not axis or count == 0:
                            continue
                        parent_nav = f"{ref}/{axis}::{parent.tag}[{count}]"
                        result = qualify_under(parent_nav, parent)
                        if result:
                            return result

                # ── 6: cousin (sibling's child) has unique attrs ──────────────
                #    //cousin[@attr]/parent::sib/sibling-axis::target[n]
                for sib in siblings:
                    if sib is target:
                        continue
                    for cousin in sib:
                        ref = unique_ref(cousin)
                        if ref is None:
                            continue
                        axis, count = sibling_axis(target, sib)
                        if not axis or count == 0:
                            continue
                        expr = f"{ref}/parent::{sib.tag}/{axis}::{target.tag}[{count}]"
                        if unique_for_node(expr):
                            return expr
                        # target may be an ancestor of node; qualify down
                        if target is not node:
                            result = qualify_under(expr, target)
                            if result:
                                return result

                # Move one level up and repeat
                target = parent

            # ── Strategy 7: structural fallback ───────────────────────────────
            path_parts: List[str] = []
            current = node
            while current is not None and current != root:
                par = current.getparent()
                if par is None:
                    break
                t = current.attrib.get('class') or current.tag
                sibs = [c for c in par if (c.attrib.get('class') or c.tag) == t]
                idx = sibs.index(current) + 1
                path_parts.insert(0, f"{t}[{idx}]")
                current = par

            if path_parts:
                return "/hierarchy/" + "/".join(path_parts)
            return f"//{tag}"

        except Exception as e:
            logger.error(f"Error generating unique XPath: {e}")
            return ""

    
    @staticmethod
    def _generate_xpath_relative(attributes: Dict[str, str], tag: str,
                                  platform: str = 'android') -> List[str]:
        """
        Generate relative (non-unique) XPath alternatives ordered by specificity.
        Uses native attribute names per platform:
          Android: @resource-id, @content-desc, @text
          iOS:     @name, @label, @value
        """
        escape = XMLParser._xpath_escape
        xpaths = []
        is_ios = platform == 'ios'

        if is_ios:
            name  = attributes.get('name')
            label = attributes.get('label')
            value = attributes.get('value')

            if name:
                xpaths.append(f"//*[@name={escape(name)}]")
            if label:
                xpaths.append(f"//*[@label={escape(label)}]")
            if value:
                xpaths.append(f"//*[@value={escape(value)}]")
            if tag and name:
                xpaths.append(f"//{tag}[@name={escape(name)}]")
            xpaths.append(f"//{tag}")
        else:
            resource_id  = attributes.get('resource-id')
            content_desc = attributes.get('content-desc')
            text         = attributes.get('text')

            if resource_id:
                xpaths.append(f"//*[@resource-id={escape(resource_id)}]")
            if content_desc:
                xpaths.append(f"//*[@content-desc={escape(content_desc)}]")
            if text:
                xpaths.append(f"//*[@text={escape(text)}]")
            if text:
                xpaths.append(f"//{tag}[@text={escape(text)}]")
            if resource_id:
                xpaths.append(f"//{tag}[@resource-id={escape(resource_id)}]")
            xpaths.append(f"//{tag}")

        return xpaths
    
    @staticmethod
    def _generate_android_uiautomator(attributes: Dict[str, str], tag: str) -> List[str]:
        """
        Generate Android UiAutomator selector expressions
        Returns multiple options in priority order
        """
        selectors = []
        
        # Priority 1: resourceId
        resource_id = attributes.get('resource-id')
        if resource_id:
            selectors.append(f'new UiSelector().resourceId("{resource_id}")')
        
        # Priority 2: text
        text = attributes.get('text')
        if text:
            selectors.append(f'new UiSelector().text("{text}")')
        
        # Priority 3: contentDescription
        content_desc = attributes.get('content-desc')
        if content_desc:
            selectors.append(f'new UiSelector().description("{content_desc}")')
        
        # Priority 4: className
        if tag:
            selectors.append(f'new UiSelector().className("{tag}")')
        
        # Priority 5: className + text
        if tag and text:
            selectors.append(f'new UiSelector().className("{tag}").text("{text}")')
        
        # Priority 6: className + resourceId
        if tag and resource_id:
            selectors.append(f'new UiSelector().className("{tag}").resourceId("{resource_id}")')
        
        return selectors
    
    @staticmethod
    def _generate_ios_predicate(attributes: Dict[str, str], tag: str) -> List[str]:
        """
        Generate iOS Predicate String expressions
        Returns multiple options in priority order
        """
        predicates = []
        
        # Priority 1: name
        name = attributes.get('name')
        if name:
            predicates.append(f"name == '{name}'")
        
        # Priority 2: label
        label = attributes.get('label')
        if label:
            predicates.append(f"label == '{label}'")
        
        # Priority 3: value
        value = attributes.get('value')
        if value:
            predicates.append(f"value == '{value}'")
        
        # Priority 4: type
        if tag:
            predicates.append(f"type == '{tag}'")
        
        # Priority 5: type + label
        if tag and label:
            predicates.append(f"type == '{tag}' AND label == '{label}'")
        
        return predicates
    
    @staticmethod
    def _generate_ios_class_chain(attributes: Dict[str, str], tag: str) -> List[str]:
        """
        Generate iOS Class Chain expressions
        """
        chains = []
        
        # Priority 1: type with name
        name = attributes.get('name')
        if tag and name:
            chains.append(f"**/{tag}[`name == '{name}'`]")
        
        # Priority 2: type with label
        label = attributes.get('label')
        if tag and label:
            chains.append(f"**/{tag}[`label == '{label}'`]")
        
        # Priority 3: type only
        if tag:
            chains.append(f"**/{tag}")
        
        return chains
    
    @staticmethod
    def _generate_selectors(node, root, platform: str = 'android') -> Dict:
        """
        Generate all possible selectors for a node.
        id / accessibility_id use platform-native attribute names.
        """
        attributes = dict(node.attrib)
        tag = node.tag
        is_ios = platform == 'ios'

        if is_ios:
            id_val = attributes.get('name')
            a11y_id = attributes.get('label')
        else:
            id_val = attributes.get('resource-id')
            a11y_id = attributes.get('content-desc')

        selectors = {
            'id': id_val,
            'accessibility_id': a11y_id,
            'class_name': tag,
            'xpath_absolute': XMLParser._generate_xpath_absolute(node, root, platform),
            'xpath_relative': XMLParser._generate_xpath_relative(attributes, tag, platform),
        }

        # Platform-specific selectors
        if platform == 'android':
            selectors['uiautomator'] = XMLParser._generate_android_uiautomator(attributes, tag)
        elif platform == 'ios':
            selectors['predicate'] = XMLParser._generate_ios_predicate(attributes, tag)
            selectors['class_chain'] = XMLParser._generate_ios_class_chain(attributes, tag)

        return selectors


    
    @staticmethod
    def _parse_bounds(bounds_str: str) -> Optional[Dict[str, int]]:
        """
        Parse bounds string to coordinates
        Android: [x1,y1][x2,y2]
        iOS: {{x,y},{w,h}}
        """
        try:
            if not bounds_str:
                return None
            
            # Android format: [x1,y1][x2,y2]
            if bounds_str.startswith('['):
                import re
                matches = re.findall(r'\[(\d+),(\d+)\]', bounds_str)
                if len(matches) == 2:
                    x1, y1 = map(int, matches[0])
                    x2, y2 = map(int, matches[1])
                    return {
                        'x': x1,
                        'y': y1,
                        'w': x2 - x1,
                        'h': y2 - y1
                    }
            
            # iOS format: {{x,y},{w,h}}
            elif bounds_str.startswith('{'):
                import re
                matches = re.findall(r'\{(\d+),(\d+)\}', bounds_str)
                if len(matches) == 2:
                    x, y = map(int, matches[0])
                    w, h = map(int, matches[1])
                    return {
                        'x': x,
                        'y': y,
                        'w': w,
                        'h': h
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing bounds: {e}")
            return None
    
    @staticmethod
    def _node_to_dict(node, root, node_path: List[int], platform: str = 'android') -> Dict:
        """
        Convert XML node to dictionary with enhanced information
        
        优化：优先使用 class 属性作为 tag 名字
        
        Args:
            node: XML node
            root: Root XML node
            node_path: Path from root to this node (list of indices)
            platform: 'android' or 'ios'
        """
        # Get all attributes
        attributes = dict(node.attrib)
        
        # ============================================================================
        # 优先使用 class 属性作为 tag（如果存在）
        # ============================================================================
        tag = node.tag
        
        # Parse bounds
        bounds_raw = attributes.get('bounds', '')
        bounds_computed = XMLParser._parse_bounds(bounds_raw)
        if bounds_computed:
            attributes['bounds_computed'] = bounds_computed
        
        # Generate selectors (现有方法会自动处理)
        selectors = XMLParser._generate_selectors(node, root, platform)
        
        # Build node dictionary
        node_dict = {
            'tag': tag,  # ✅ 使用 class 或原始 tag
            'attributes': attributes,
            'node_path': node_path,
            'selectors': selectors,
            'children': []
        }
        
        # Process children
        for index, child in enumerate(node):
            child_path = node_path + [index]
            child_dict = XMLParser._node_to_dict(child, root, child_path, platform)
            node_dict['children'].append(child_dict)
        
        return node_dict
    
    @staticmethod
    def parse_xml_to_json(xml_content: str, platform: str = 'android') -> Dict:
        """
        Parse XML content to JSON hierarchy with enhanced information
        
        Args:
            xml_content: XML string from UIAutomator/XCUITest
            platform: 'android' or 'ios'
        
        Returns:
            Dictionary with success status and parsed hierarchy
        """
        try:
            # 验证 XML 内容
            if not xml_content:
                logger.error("XML content is empty!")
                return {
                    'success': False,
                    'error': 'XML content is empty',
                    'hierarchy': None,
                    'total_nodes': 0
                }
            
            if not xml_content.strip().startswith('<'):
                logger.error(f"XML content does not start with '<'")
                return {
                    'success': False,
                    'error': f'Invalid XML format',
                    'hierarchy': None,
                    'total_nodes': 0
                }
            
            # 转换 XML 格式：<node class="xxx"> -> <xxx>
            logger.info("Converting XML format from <node> to <class> tags...")
            xml_content = XMLParser.convert_node_to_class_tags(xml_content)
            
            # Parse XML
            root = etree.fromstring(xml_content.encode('utf-8'))
            
            # Track total nodes
            node_count = 0
            
            # ✅ 修改：parse_node 接收 root 参数
            def parse_node(element, xml_root, parent_path: List[int], index: int) -> Dict[str, Any]:
                """Recursively parse XML element to JSON"""
                nonlocal node_count
                node_count += 1
                
                # 现在 element.tag 就是完整的类名了
                tag = element.tag
                
                # 获取所有属性
                attributes = dict(element.attrib)
                
                # 解析 bounds
                bounds_str = attributes.get('bounds')
                if bounds_str:
                    try:
                        import re
                        matches = re.findall(r'\[(\d+),(\d+)\]', bounds_str)
                        if len(matches) == 2:
                            x1, y1 = map(int, matches[0])
                            x2, y2 = map(int, matches[1])
                            attributes['bounds_computed'] = {
                                'x': x1,
                                'y': y1,
                                'w': x2 - x1,
                                'h': y2 - y1
                            }
                    except Exception as e:
                        logger.warning(f"Failed to parse bounds: {bounds_str}, error: {e}")
                
                # 当前节点路径
                current_path = parent_path + [index]
                
                # ✅ 调用现有的 _generate_selectors 方法
                selectors = XMLParser._generate_selectors(element, xml_root, platform)
                
                # 解析子节点
                children = []
                for child_index, child_element in enumerate(element):
                    child_node = parse_node(child_element, xml_root, current_path, child_index)
                    children.append(child_node)
                
                return {
                    'tag': tag,
                    'attributes': attributes,
                    'children': children,
                    'selectors': selectors,
                    'node_path': current_path
                }
            
            # ✅ 修复：处理所有并列的根节点
            # 如果 root 是 <hierarchy>，创建一个虚拟根节点包含所有子节点
            if root.tag == 'hierarchy':
                # 创建虚拟根节点
                node_count += 1  # 虚拟根节点也算一个
                hierarchy = {
                    'tag': 'hierarchy',
                    'attributes': dict(root.attrib),
                    'children': [],
                    'selectors': {},
                    'node_path': [0]
                }
                
                # 解析所有并列的子节点
                for child_index, child_element in enumerate(root):
                    child_node = parse_node(child_element, root, [0], child_index)
                    hierarchy['children'].append(child_node)
            else:
                # 直接解析根节点
                hierarchy = parse_node(root, root, [], 0)
            
            logger.info(f"Successfully parsed XML. Total nodes: {node_count}")
            
            return {
                'success': True,
                'platform': platform,
                'total_nodes': node_count,
                'hierarchy': hierarchy
            }
            
        except etree.XMLSyntaxError as e:
            logger.error(f"XML Syntax Error: {e}")
            return {
                'success': False,
                'error': f'XML Syntax Error: {str(e)}',
                'hierarchy': None,
                'total_nodes': 0
            }
        except Exception as e:
            logger.error(f"Error parsing XML: {e}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'hierarchy': None,
                'total_nodes': 0
            }



    @staticmethod
    def parse_xml_to_json1(xml_content: str, platform: str = 'android') -> Dict:
        """
        Parse XML content to JSON structure with selectors
        
        Args:
            xml_content: XML string
            platform: 'android' or 'ios'
        
        Returns:
            Dictionary with hierarchy and metadata
        """
        try:
            # Parse XML
            root = etree.fromstring(xml_content.encode('utf-8'))
            
            # Convert to dictionary
            hierarchy = XMLParser._node_to_dict(root, root, [0], platform)
            
            # Count nodes
            def count_nodes(node):
                count = 1
                for child in node.get('children', []):
                    count += count_nodes(child)
                return count
            
            total_nodes = count_nodes(hierarchy)
            
            return {
                'success': True,
                'platform': platform,
                'total_nodes': total_nodes,
                'hierarchy': hierarchy
            }
            
        except Exception as e:
            logger.error(f"Error parsing XML: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def query_xpath(xml_content: str, xpath_query: str) -> Dict:
        """
        Execute XPath query on XML content
        
        优化：先转换 XML 格式，然后执行查询
        
        Args:
            xml_content: XML string
            xpath_query: XPath expression
        
        Returns:
            Dictionary with matches
        """
        try:
            # ✅ 先转换 XML 格式：<node class="xxx"> -> <xxx>
            logger.info("Converting XML format for XPath query...")
            xml_content = XMLParser.convert_node_to_class_tags(xml_content)
            
            root = etree.fromstring(xml_content.encode('utf-8'))
            matches = root.xpath(xpath_query)
            
            results = []
            for match in matches:
                if isinstance(match, etree._Element):
                    attributes = dict(match.attrib)
                    bounds_computed = XMLParser._parse_bounds(attributes.get('bounds', ''))
                    
                    # ✅ 现在 match.tag 就是完整类名
                    tag = match.tag
                    
                    result = {
                        'tag': tag,
                        'attributes': attributes,
                        'bounds_computed': bounds_computed
                    }
                    results.append(result)
            
            logger.info(f"XPath query '{xpath_query}' found {len(results)} match(es)")
            
            return {
                'success': True,
                'count': len(results),
                'matches': results
            }
            
        except Exception as e:
            logger.error(f"Error executing XPath query: {e}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'count': 0,
                'matches': []
            }


    
    @staticmethod
    def find_node_by_path(hierarchy: Dict, node_path: List[int]) -> Optional[Dict]:
        """
        Find a node in hierarchy by its path
        
        Args:
            hierarchy: Parsed hierarchy dictionary
            node_path: List of indices from root to target node
        
        Returns:
            Node dictionary or None
        """
        try:
            current = hierarchy
            
            for index in node_path[1:]:  # Skip first index (root)
                if 'children' not in current or index >= len(current['children']):
                    return None
                current = current['children'][index]
            
            return current
            
        except Exception as e:
            logger.error(f"Error finding node by path: {e}")
            return None
