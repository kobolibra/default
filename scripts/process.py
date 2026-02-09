import os
import zipfile
import shutil
import re
from bs4 import BeautifulSoup

INPUT_EPUB = "input/economist.epub"

# 需要保留的 sections，按优先级排序
TARGET_SECTIONS = [
    "Leaders",
    "By Invitation", 
    "Briefing",
    "China",
    "International",
    "Business",
    "Finance & economics",
    "Science & technology",
    "Culture"
]

def main():
    # 兼容旧版本 Python 的目录删除方式
    if os.path.exists("temp_epub"):
        shutil.rmtree("temp_epub")
    if os.path.exists("output"):
        shutil.rmtree("output")

    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)
    os.makedirs("output/sections", exist_ok=True)

    unzip_epub()
    copy_images()

    articles = []

    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.endswith((".html", ".xhtml")):
                path = os.path.join(root, f)
                articles.extend(parse_html_file(path))

    # 按 section 组织文章，保持顺序
    section_data = organize_by_section(articles)
    
    # 生成 section 页面（小目录）
    for section, section_articles in section_data.items():
        generate_section_page(section, section_articles)
    
    # 生成首页（大目录）
    generate_index(section_data)

    print("Done. Articles:", len(articles))
    print("Sections:", list(section_data.keys()))


# --------------------------------------------------

def unzip_epub():
    with zipfile.ZipFile(INPUT_EPUB, "r") as z:
        z.extractall("temp_epub")


# --------------------------------------------------

def copy_images():
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
                src = os.path.join(root, f)
                dst = os.path.join("output/images", f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)


# --------------------------------------------------

def parse_html_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return []

    articles = []
    current_section = None

    # 识别 section 标题
    for tag in body.find_all(["h1", "h2"]):

        # section header
        if tag.name == "h2":
            section_name = tag.get_text(strip=True)
            # 检查是否在目标 sections 中（不区分大小写匹配）
            for target in TARGET_SECTIONS:
                if section_name.lower() == target.lower():
                    current_section = target  # 使用标准化的名称
                    break
            else:
                current_section = None  # 不在目标列表中的 section
            continue

        if tag.name == "h1":
            # 跳过不在目标 section 中的文章
            if current_section is None:
                continue
                
            title = tag.get_text(strip=True)
            if not title:
                continue

            content_nodes = [tag]

            for sib in tag.next_siblings:
                if getattr(sib, "name", None) == "h1":
                    break
                if getattr(sib, "name", None) == "h2":
                    break
                content_nodes.append(sib)

            article_html = "".join(str(x) for x in content_nodes)

            # 修复图片路径
            article_html = re.sub(
                r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
                r'src="../images/\2"',
                article_html,
                flags=re.IGNORECASE
            )

            if len(article_html) < 200:
                continue

            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            path = f"articles/{slug}.html"

            write_article(path, title, article_html, current_section)

            articles.append({
                "section": current_section,
                "title": title,
                "path": path
            })

    return articles


# --------------------------------------------------

def organize_by_section(articles):
    """按 section 组织文章，保持 section 顺序和文章顺序"""
    section_order = []
    section_articles = {}
    
    for article in articles:
        section = article["section"]
        if section not in section_articles:
            section_articles[section] = []
            section_order.append(section)
        section_articles[section].append(article)
    
    # 按 section_order 返回有序字典
    return {section: section_articles[section] for section in section_order}


# --------------------------------------------------

def write_article(path, title, html_content, section):
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | {section}</title>
<style>
    body {{
        font-family: "Georgia", "Times New Roman", serif;
        font-size: 18px;
        line-height: 1.8;
        color: #333;
        max-width: 800px;
        margin: 0 auto;
        padding: 40px 20px;
        background-color: #fff;
    }}
    .breadcrumb {{
        font-size: 14px;
        color: #666;
        margin-bottom: 30px;
        padding-bottom: 15px;
        border-bottom: 1px solid #eee;
    }}
    .breadcrumb a {{
        color: #e3120b;
        text-decoration: none;
    }}
    .breadcrumb a:hover {{
        text-decoration: underline;
    }}
    h1 {{
        font-size: 32px;
        font-weight: bold;
        color: #e3120b;
        margin-bottom: 20px;
        line-height: 1.3;
    }}
    h2 {{
        font-size: 24px;
        font-weight: bold;
        color: #333;
        margin-top: 30px;
        margin-bottom: 15px;
    }}
    h3 {{
        font-size: 20px;
        font-weight: bold;
        color: #555;
        margin-top: 25px;
        margin-bottom: 10px;
    }}
    p {{
        margin-bottom: 20px;
        text-align: justify;
        hyphens: auto;
    }}
    img {{
        max-width: 100%;
        height: auto;
        display: block;
        margin: 30px auto;
    }}
    figcaption {{
        font-size: 14px;
        color: #666;
        text-align: center;
        margin-top: -20px;
        margin-bottom: 20px;
        font-style: italic;
    }}
    .caption {{
        font-size: 14px;
        color: #666;
        text-align: center;
        margin-bottom: 20px;
    }}
    a {{
        color: #e3120b;
        text-decoration: none;
    }}
    a:hover {{
        text-decoration: underline;
    }}
    strong {{
        font-weight: bold;
    }}
    em {{
        font-style: italic;
    }}
    blockquote {{
        border-left: 4px solid #e3120b;
        margin: 20px 0;
        padding-left: 20px;
        color: #555;
        font-style: italic;
    }}
    ul, ol {{
        margin-bottom: 20px;
        padding-left: 30px;
    }}
    li {{
        margin-bottom: 10px;
    }}
    .nav-links {{
        margin-top: 40px;
        padding-top: 20px;
        border-top: 2px solid #eee;
        display: flex;
        justify-content: space-between;
    }}
    .nav-links a {{
        color: #e3120b;
        font-weight: bold;
    }}
</style>
</head>
<body>
<div class="breadcrumb">
    <a href="../index.html">Home</a> &gt; 
    <a href="sections/{section.replace(" ", "-").lower()}.html">{section}</a> &gt; 
    <span>{title}</span>
</div>
{html_content}
<div class="nav-links">
    <a href="sections/{section.replace(" ", "-").lower()}.html">← Back to {section}</a>
    <a href="../index.html">Home →</a>
</div>
</body>
</html>
"""

    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

def generate_section_page(section, articles):
    """生成每个 section 的小目录页面"""
    section_slug = section.replace(" ", "-").lower()
    
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{section} | The Economist</title>
<style>
    body {{
        font-family: "Georgia", "Times New Roman", serif;
        font-size: 16px;
        line-height: 1.6;
        color: #333;
        max-width: 900px;
        margin: 0 auto;
        padding: 40px 20px;
        background-color: #f5f5f5;
    }}
    .breadcrumb {{
        font-size: 14px;
        color: #666;
        margin-bottom: 20px;
    }}
    .breadcrumb a {{
        color: #e3120b;
        text-decoration: none;
    }}
    .breadcrumb a:hover {{
        text-decoration: underline;
    }}
    h1 {{
        font-size: 42px;
        font-weight: bold;
        color: #e3120b;
        margin-bottom: 10px;
        border-bottom: 3px solid #e3120b;
        padding-bottom: 20px;
    }}
    .section-desc {{
        font-size: 18px;
        color: #666;
        margin-bottom: 30px;
        font-style: italic;
    }}
    .article-count {{
        font-size: 16px;
        color: #666;
        margin-bottom: 30px;
    }}
    .article-list {{
        background-color: #fff;
        padding: 30px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    .article-item {{
        margin-bottom: 20px;
        padding: 15px;
        border-left: 4px solid #e3120b;
        padding-left: 20px;
        transition: background-color 0.2s;
        border-bottom: 1px solid #eee;
    }}
    .article-item:last-child {{
        border-bottom: none;
    }}
    .article-item:hover {{
        background-color: #f9f9f9;
    }}
    .article-item a {{
        color: #333;
        text-decoration: none;
        font-size: 20px;
        font-weight: 500;
        display: block;
        margin-bottom: 5px;
    }}
    .article-item a:hover {{
        color: #e3120b;
    }}
    .article-index {{
        font-size: 14px;
        color: #999;
        font-weight: normal;
    }}
    .back-link {{
        margin-top: 30px;
        text-align: center;
    }}
    .back-link a {{
        color: #e3120b;
        font-weight: bold;
        font-size: 16px;
    }}
</style>
</head>
<body>
<div class="breadcrumb">
    <a href="../index.html">Home</a> &gt; 
    <span>{section}</span>
</div>
<h1>{section}</h1>
<div class="section-desc">The Economist - Weekly Edition</div>
<div class="article-count">{len(articles)} articles in this section</div>
<div class="article-list">
"""

    for idx, article in enumerate(articles, 1):
        html += f'''
    <div class="article-item">
        <span class="article-index">{idx}.</span>
        <a href="../{article["path"]}">{article["title"]}</a>
    </div>
'''

    html += f'''
</div>
<div class="back-link">
    <a href="../index.html">← Back to All Sections</a>
</div>
</body>
</html>
'''

    with open(f"output/sections/{section_slug}.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

def generate_index(section_data):
    """生成首页 - 大目录，展示所有 sections"""
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Economist - Weekly Edition</title>
<style>
    body {
        font-family: "Georgia", "Times New Roman", serif;
        font-size: 16px;
        line-height: 1.6;
        color: #333;
        max-width: 1000px;
        margin: 0 auto;
        padding: 40px 20px;
        background-color: #f5f5f5;
    }
    .header {
        text-align: center;
        margin-bottom: 50px;
        padding-bottom: 30px;
        border-bottom: 4px solid #e3120b;
    }
    h1 {
        font-size: 52px;
        font-weight: bold;
        color: #e3120b;
        margin-bottom: 10px;
        letter-spacing: -1px;
    }
    .subtitle {
        font-size: 20px;
        color: #666;
        font-style: italic;
    }
    .date {
        font-size: 16px;
        color: #999;
        margin-top: 10px;
    }
    .sections-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 25px;
        margin-top: 30px;
    }
    .section-card {
        background-color: #fff;
        padding: 25px;
        border-radius: 10px;
        box-shadow: 0 3px 6px rgba(0,0,0,0.1);
        transition: transform 0.2s, box-shadow 0.2s;
        border-top: 4px solid #e3120b;
    }
    .section-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.15);
    }
    .section-card h2 {
        font-size: 24px;
        font-weight: bold;
        color: #333;
        margin-bottom: 10px;
        margin-top: 0;
    }
    .section-card h2 a {
        color: #333;
        text-decoration: none;
    }
    .section-card h2 a:hover {
        color: #e3120b;
    }
    .article-count {
        font-size: 14px;
        color: #666;
        margin-bottom: 15px;
        font-weight: 500;
    }
    .preview {
        font-size: 14px;
        color: #666;
        line-height: 1.5;
    }
    .preview-item {
        margin-bottom: 8px;
        padding-left: 15px;
        position: relative;
    }
    .preview-item:before {
        content: "•";
        color: #e3120b;
        position: absolute;
        left: 0;
    }
    .view-all {
        margin-top: 15px;
        font-size: 14px;
        font-weight: bold;
    }
    .view-all a {
        color: #e3120b;
        text-decoration: none;
    }
    .view-all a:hover {
        text-decoration: underline;
    }
    .footer {
        margin-top: 50px;
        text-align: center;
        padding-top: 30px;
        border-top: 2px solid #ddd;
        color: #666;
        font-size: 14px;
    }
</style>
</head>
<body>
<div class="header">
    <h1>The Economist</h1>
    <div class="subtitle">Weekly Edition</div>
    <div class="date">February 7th 2026</div>
</div>
<div class="sections-grid">
"""

    for section, articles in section_data.items():
        section_slug = section.replace(" ", "-").lower()
        article_count = len(articles)
        
        # 显示前3篇文章标题作为预览
        preview_articles = articles[:3]
        preview_html = ""
        for article in preview_articles:
            preview_html += f'<div class="preview-item">{article["title"][:60]}{"..." if len(article["title"]) > 60 else ""}</div>\n'
        
        html += f'''
    <div class="section-card">
        <h2><a href="sections/{section_slug}.html">{section}</a></h2>
        <div class="article-count">{article_count} articles</div>
        <div class="preview">
            {preview_html}
        </div>
        <div class="view-all"><a href="sections/{section_slug}.html">View all →</a></div>
    </div>
'''

    html += """
</div>
<div class="footer">
    <p>© The Economist Newspaper Limited 2026. All rights reserved.</p>
    <p>Automatically generated from EPUB</p>
</div>
</body>
</html>
"""

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

if __name__ == "__main__":
    main()
