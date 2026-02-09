import os
import zipfile
import shutil
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

# --------------------------------------------------
# 配置与常量
# --------------------------------------------------

INPUT_EPUB = "input/economist.epub"

# 定义需要保留的 Section（全部小写，用于归一化匹配）
# 即使源文件大小写不同，只要字母对得上就能匹配
ALLOWED_SECTIONS = {
    "leaders", 
    "by invitation", 
    "briefing", 
    "china", 
    "international", 
    "business", 
    "finance & economics", 
    "science & technology", 
    "culture"
}

def main():
    # 1. 环境清理与初始化
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)

    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)
    os.makedirs("output/css", exist_ok=True)

    if not os.path.exists(INPUT_EPUB):
        print(f"Error: {INPUT_EPUB} not found.")
        return

    # 2. 解压 EPUB
    print("Unzipping epub...")
    unzip_epub()
    
    # 3. 提取资源（图片和CSS）
    copy_images()
    css_filename = copy_css() # 提取原书CSS以保持排版

    # 4. 获取正确的阅读顺序 (关键步骤：解决顺序乱的问题)
    print("Parsing reading order...")
    ordered_files = get_reading_order("temp_epub")
    
    articles = []
    current_section = "Unknown" 

    # 5. 按顺序解析 HTML 文件
    print(f"Processing {len(ordered_files)} files...")
    for html_file in ordered_files:
        full_path = os.path.join("temp_epub", html_file)
        if not os.path.exists(full_path):
            continue
            
        # 传入当前的 section 状态，返回解析出的文章列表和更新后的 section
        new_articles, current_section = parse_html_file(full_path, current_section, css_filename)
        
        # 过滤需要的板块
        for art in new_articles:
            # 归一化处理：去首尾空格，转小写
            sec_norm = art['section'].strip().lower()
            if sec_norm in ALLOWED_SECTIONS:
                articles.append(art)

    # 6. 生成索引页
    generate_index(articles)

    print(f"Done. Generated {len(articles)} articles.")


# --------------------------------------------------
# 核心逻辑
# --------------------------------------------------

def unzip_epub():
    with zipfile.ZipFile(INPUT_EPUB, "r") as z:
        z.extractall("temp_epub")

def copy_images():
    # 遍历所有文件夹寻找图片，并扁平化复制到 output/images
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
                src = os.path.join(root, f)
                dst = os.path.join("output/images", f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)

def copy_css():
    """提取 EPUB 中的 CSS 文件，用于还原排版"""
    css_name = None
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith(".css"):
                src = os.path.join(root, f)
                dst = os.path.join("output/css", f)
                shutil.copy2(src, dst)
                css_name = f 
                # 通常取第一个找到的 css 即可，或者全部复制
                # 这里返回文件名用于 link 标签
    return css_name

def get_reading_order(base_dir):
    """
    通过解析 content.opf 获取 spine (书脊) 的顺序。
    这是确保文章顺序与原书一致的唯一正确方法，
    完全替代原来的 os.walk 随机读取。
    """
    # 1. 找到 .opf 文件
    opf_path = None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".opf"):
                opf_path = os.path.join(root, f)
                break
        if opf_path: break
            
    if not opf_path:
        return []

    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()
        
        # 处理 XML 命名空间 (EPUB 标准通常有命名空间)
        # 这种方式可以兼容带有或不带有特定前缀的写法
        namespaces = {'opf': 'http://www.idpf.org/2007/opf'}
        
        # 获取 Manifest (ID -> 文件路径)
        manifest = {}
        # 查找所有 item 标签
        for item in root.findall(".//opf:item", namespaces):
            manifest[item.get("id")] = item.get("href")
        
        # 如果上面没找到（可能是命名空间问题），尝试不带命名空间查找
        if not manifest:
            for item in root.findall(".//item"):
                manifest[item.get("id")] = item.get("href")

        # 获取 Spine (ID 引用列表，代表阅读顺序)
        spine_ids = []
        for itemref in root.findall(".//opf:itemref", namespaces):
            spine_ids.append(itemref.get("idref"))
        if not spine_ids:
            for itemref in root.findall(".//itemref"):
                spine_ids.append(itemref.get("idref"))
            
        # 将 ID 转换为实际文件路径
        opf_dir = os.path.dirname(opf_path)
        ordered_files = []
        for spin_id in spine_ids:
            href = manifest.get(spin_id)
            if href:
                # 拼接完整路径
                full_path = os.path.join(opf_dir, href)
                # 转为相对于 temp_epub 的路径
                rel_path = os.path.relpath(full_path, base_dir)
                ordered_files.append(rel_path)
                
        return ordered_files
    except Exception as e:
        print(f"Error parsing OPF: {e}")
        return []


def parse_html_file(filepath, current_section, css_filename):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return [], current_section

    articles = []
    
    # 查找所有 h1 和 h2，按出现顺序处理
    # Economist 的 epub 结构通常是：h2 是板块名，h1 是文章标题
    tags = body.find_all(["h1", "h2"])
    
    for tag in tags:
        # 遇到 h2，更新当前板块名称
        if tag.name == "h2":
            temp_section = tag.get_text(strip=True)
            if temp_section:
                current_section = temp_section
            continue

        # 遇到 h1，这是一篇文章的开始
        if tag.name == "h1":
            title = tag.get_text(strip=True)
            if not title:
                continue

            # 收集文章内容：从当前 h1 开始，直到下一个 h1 或 h2 结束
            content_nodes = [tag]
            for sib in tag.next_siblings:
                if getattr(sib, "name", None) in ["h1", "h2"]:
                    break
                content_nodes.append(sib)

            article_html = "".join(str(x) for x in content_nodes)

            # 修复图片路径：原文是相对路径，统一改为指向 ../images/
            article_html = re.sub(
                r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
                r'src="../images/\2"',
                article_html,
                flags=re.IGNORECASE
            )

            if len(article_html) < 200:
                continue

            # 生成文件名
            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            # 避免重名
            if os.path.exists(f"output/articles/{slug}.html"):
                slug = f"{slug}-{len(articles)}"
            
            path = f"articles/{slug}.html"

            write_article(path, article_html, title, css_filename)

            articles.append({
                "section": current_section,
                "title": title,
                "path": path
            })

    return articles, current_section


# --------------------------------------------------

def write_article(path, html_content, title, css_filename):
    # 引入 CSS
    css_link = f'<link rel="stylesheet" href="../css/{css_filename}" type="text/css"/>' if css_filename else ""
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"> <!-- 移动端适配 -->
<title>{title}</title>
{css_link}
<style>
    /* 补充一些基础样式，防止原书 CSS 不完整导致排版错乱 */
    body {{
        max-width: 900px;
        margin: 0 auto;
        padding: 20px;
        font-family: Georgia, serif; /* 保持 Economist 的衬线体风格 */
        background-color: #fdfdfd;
        color: #111;
    }}
    img {{
        max-width: 100%;
        height: auto;
        display: block;
        margin: 20px auto;
    }}
    /* 针对 Economist 常见类的简单修复 */
    .fly-title {{ 
        text-transform: uppercase; 
        font-size: 0.8em; 
        color: #e3120b; 
        margin-bottom: 5px;
        display: block;
    }}
</style>
</head>
<body class="article">
<div class="main-content">
{html_content}
</div>
</body>
</html>
"""

    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

def generate_index(articles):
    # 简单的美化索引页
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Economist</title>
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f4f4f4; }
    h1 { text-align: center; color: #e3120b; font-family: Georgia, serif; margin-bottom: 40px; }
    
    h2.section-header { 
        border-bottom: 2px solid #e3120b; 
        padding-bottom: 5px; 
        margin-top: 40px; 
        margin-bottom: 15px;
        font-size: 1.2em; 
        text-transform: uppercase; 
        letter-spacing: 0.05em;
        color: #333; 
    }
    
    div.article-link { 
        margin: 10px 0; 
        padding: 15px; 
        background: white; 
        border-radius: 4px; 
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); 
        transition: transform 0.1s;
    }
    div.article-link:hover { transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    
    a { text-decoration: none; color: #1a1a1a; font-weight: bold; font-size: 1.1em; display: block; }
    a:hover { color: #e3120b; }
</style>
</head>
<body>
<h1>The Economist</h1>
"""

    current_section = None

    # 因为 articles 是按 Spine 顺序遍历生成的，所以这里的顺序就是书里的顺序
    for a in articles:
        # 当 Section 变化时，插入 H2
        if a["section"] != current_section:
            current_section = a["section"]
            html += f'<h2 class="section-header">{current_section}</h2>'

        html += f'<div class="article-link"><a href="{a["path"]}">{a["title"]}</a></div>'

    html += "</body></html>"

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

if __name__ == "__main__":
    main()
