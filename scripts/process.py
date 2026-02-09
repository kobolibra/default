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
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)

    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)

    unzip_epub()
    copy_images()

    articles = []

    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.endswith((".html", ".xhtml")):
                path = os.path.join(root, f)
                articles.extend(parse_html_file(path))

    generate_index(articles)

    print("Done. Articles:", len(articles))


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

            write_article(path, title, article_html)

            articles.append({
                "section": current_section,
                "title": title,
                "path": path
            })

    return articles


# --------------------------------------------------

def write_article(path, title, html_content):
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
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
</style>
</head>
<body>
{html_content}
</body>
</html>
"""

    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

def generate_index(articles):
    # 按 TARGET_SECTIONS 的顺序组织文章
    # 使用列表保持 section 顺序和文章顺序
    section_order = []
    section_articles = {}
    
    for article in articles:
        section = article["section"]
        if section not in section_articles:
            section_articles[section] = []
            section_order.append(section)
        section_articles[section].append(article)
    
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Economist</title>
<style>
    body {
        font-family: "Georgia", "Times New Roman", serif;
        font-size: 16px;
        line-height: 1.6;
        color: #333;
        max-width: 900px;
        margin: 0 auto;
        padding: 40px 20px;
        background-color: #f5f5f5;
    }
    h1 {
        font-size: 42px;
        font-weight: bold;
        color: #e3120b;
        text-align: center;
        margin-bottom: 40px;
        border-bottom: 3px solid #e3120b;
        padding-bottom: 20px;
    }
    h2 {
        font-size: 24px;
        font-weight: bold;
        color: #333;
        margin-top: 40px;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 2px solid #ddd;
    }
    .article-list {
        background-color: #fff;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .article-item {
        margin-bottom: 15px;
        padding: 10px;
        border-left: 3px solid #e3120b;
        padding-left: 15px;
        transition: background-color 0.2s;
    }
    .article-item:hover {
        background-color: #f9f9f9;
    }
    a {
        color: #333;
        text-decoration: none;
        font-size: 18px;
        font-weight: 500;
    }
    a:hover {
        color: #e3120b;
    }
    .section-count {
        color: #666;
        font-size: 14px;
        margin-left: 10px;
    }
</style>
</head>
<body>
<h1>The Economist</h1>
"""

    for section in section_order:
        articles_in_section = section_articles[section]
        html += f'<h2>{section} <span class="section-count">({len(articles_in_section)} articles)</span></h2>'
        html += '<div class="article-list">'
        
        for a in articles_in_section:
            html += f'<div class="article-item"><a href="{a["path"]}">{a["title"]}</a></div>'
        
        html += '</div>'

    html += "</body></html>"

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

if __name__ == "__main__":
    main()
