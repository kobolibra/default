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

ALLOWED_SECTIONS = {
    "leaders", 
    "by invitation", 
    "briefing", 
    "china", 
    "international", 
    "business", 
    "finance & economics", 
    "science & technology", 
    "culture", 
    "special reports",
    "technology quarterly",
    "essay",
    "the economist reads"
}

def main():
    # 环境初始化
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)
    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)
    os.makedirs("output/css", exist_ok=True)

    if not os.path.exists(INPUT_EPUB): 
        print(f"Error: {INPUT_EPUB} not found.")
        return

    unzip_epub()
    copy_images()
    css_filename = copy_css()
    ordered_files = get_reading_order("temp_epub")
    edition_date = extract_edition_date("temp_epub", ordered_files)

    articles = []
    current_section = "Unknown" 

    for html_file in ordered_files:
        full_path = os.path.join("temp_epub", html_file)
        if not os.path.exists(full_path): continue
        new_articles, current_section = parse_html_file(full_path, current_section, css_filename)
        for art in new_articles:
            if art['section'].strip().lower() in ALLOWED_SECTIONS:
                articles.append(art)

    generate_index(articles, edition_date)
    print(f"Done. Generated {len(articles)} articles.")

# --------------------------------------------------
# 基础功能 (保持稳定)
# --------------------------------------------------

def unzip_epub():
    with zipfile.ZipFile(INPUT_EPUB, "r") as z: z.extractall("temp_epub")

def copy_images():
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
                shutil.copy2(os.path.join(root, f), os.path.join("output/images", f))

def copy_css():
    css_name = None
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith(".css"):
                shutil.copy2(os.path.join(root, f), os.path.join("output/css", f))
                css_name = f
    return css_name

def get_reading_order(base_dir):
    opf_path = None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".opf"):
                opf_path = os.path.join(root, f)
                break
        if opf_path: break
    if not opf_path: return []
    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()
        ns = {'opf': 'http://www.idpf.org/2007/opf'}
        manifest = {item.get("id"): item.get("href") for item in root.findall(".//opf:item", ns)}
        if not manifest: manifest = {item.get("id"): item.get("href") for item in root.findall(".//item")}
        spine_ids = [ir.get("idref") for ir in root.findall(".//opf:itemref", ns)]
        if not spine_ids: spine_ids = [ir.get("idref") for ir in root.findall(".//itemref")]
        opf_dir = os.path.dirname(opf_path)
        return [os.path.relpath(os.path.join(opf_dir, manifest[sid]), base_dir) for sid in spine_ids if sid in manifest]
    except: return []

def extract_edition_date(base_dir, ordered_files):
    date_pattern = re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\s+20\d{2}', re.IGNORECASE)
    for fname in ordered_files[:5]:
        path = os.path.join(base_dir, fname)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                m = date_pattern.search(BeautifulSoup(f.read(), "html.parser").get_text(" ", strip=True))
                if m: return m.group(0)
        except: continue
    return ""

# --------------------------------------------------
# 针对性重构：核心解析逻辑
# --------------------------------------------------

def parse_html_file(filepath, current_section, css_filename):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    body = soup.find("body")
    if not body: return [], current_section

    articles = []
    last_found_rubric = "" # 缓存副标题

    # 按照文档流遍历所有标签
    for tag in body.find_all(True):
        # 获取 class 字符串
        cls_list = tag.get("class", [])
        if isinstance(cls_list, str): cls_list = [cls_list]
        cls = " ".join(cls_list).lower()
        
        # 1. 识别 Section (板块名)
        # 根据分析：除了 class 匹配，增加全大写/短文本判断
        is_section = False
        if tag.name == "h2":
            txt = tag.get_text(strip=True)
            # 条件：包含 section 相关类名，或者 (长度短 且 全大写)
            if any(x in cls for x in ["section", "department", "part", "header"]):
                is_section = True
            elif txt and len(txt) < 30 and txt.isupper():
                is_section = True
                
        if is_section:
            current_section = tag.get_text(strip=True)
            last_found_rubric = "" # 遇到新板块，清空旧副标题
            continue

        # 2. 识别 Rubric/Kicker (页眉描述部分)
        # 增加 subhead, deck, teaser, flytitle, kicker 等常见类名匹配
        is_rubric = any(x in cls for x in ["rubric", "kicker", "teaser", "flytitle", "deck", "subhead"])
        # 备选判断：如果是一个不带 section 类的 h2 且在板块内，也可能是副标题
        if not is_rubric and tag.name == "h2":
            txt = tag.get_text(strip=True)
            if txt and (len(txt) < 100 or "|" in txt):
                is_rubric = True
                
        if is_rubric:
            last_found_rubric = tag.get_text(strip=True)
            continue

        # 3. 捕捉到文章主标题 h1
        if tag.name == "h1":
            title = tag.get_text(strip=True)
            if not title: continue

            # --- 按照分析建议改进的去重逻辑 ---
            clean_sec = current_section.strip()
            clean_rub = last_found_rubric.strip()
            
            if clean_rub:
                # 检查 Rubric 是否已经包含管道符
                if "|" in clean_rub:
                    rub_parts = [p.strip() for p in clean_rub.split("|", 1)]
                    if rub_parts[0].lower() == clean_sec.lower():
                        # Rubric 已经是 "Section | Something" 格式，直接使用
                        header_display = clean_rub
                    else:
                        # 包含 | 但前面不是当前 section，进行组合
                        header_display = f"{clean_sec} | {clean_rub}"
                elif clean_rub.lower().startswith(clean_sec.lower()):
                    # Rubric 以 Section 开头 (如 "Leaders ...")
                    header_display = clean_rub
                elif clean_rub.lower() != clean_sec.lower():
                    # 组合显示
                    header_display = f"{clean_sec} | {clean_rub}"
                else:
                    # 相等，只用 Section
                    header_display = clean_sec
            else:
                header_display = clean_sec

            fly_title_html = f'<div class="fly-title">{header_display}</div>'
            
            # 收集正文内容 (直到下一个 h1 或 h2)
            content_nodes = [tag]
            for sib in tag.next_siblings:
                if getattr(sib, "name", None) in ["h1", "h2"]: break
                content_nodes.append(sib)

            article_html = fly_title_html + "".join(str(x) for x in content_nodes)
            # 修复图片路径
            article_html = re.sub(
                r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']', 
                r'src="../images/\2"', 
                article_html, 
                flags=re.IGNORECASE
            )

            if len(article_html) < 200: continue
            
            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            if os.path.exists(f"output/articles/{slug}.html"): slug = f"{slug}-{len(articles)}"
            path = f"articles/{slug}.html"
            
            write_article(path, article_html, title, css_filename)
            articles.append({"section": current_section, "title": title, "path": path})
            
            # 处理完文章，重置副标题
            last_found_rubric = ""

    return articles, current_section

def write_article(path, html_content, title, css_filename):
    css_link = f'<link rel="stylesheet" href="../css/{css_filename}" type="text/css"/>' if css_filename else ""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{css_link}
<style>
    body {{ max-width: 800px; margin: 0 auto; padding: 30px 20px; font-family: Georgia, serif; background-color: #fdfdfd; color: #111; line-height: 1.6; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 25px auto; }}
    .fly-title {{ 
        font-size: 0.95em; 
        color: #e3120b; 
        margin-bottom: 15px;
        border-bottom: 1px solid #ddd;
        padding-bottom: 8px;
        font-family: sans-serif;
        font-weight: bold;
    }}
    h1 {{ font-size: 2.2em; line-height: 1.2; margin: 20px 0; color: #000; }}
</style>
</head>
<body class="article">
<div class="main-content">{html_content}</div>
</body>
</html>"""
    with open(f"output/{path}", "w", encoding="utf-8") as f: f.write(html)

def generate_index(articles, edition_date):
    date_html = f'<span class="edition-date">{edition_date}</span>' if edition_date else ""
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Economist</title>
<style>
    body {{ font-family: sans-serif; max-width: 750px; margin: 0 auto; padding: 20px; background-color: #f8f9fa; }}
    h1 {{ text-align: center; color: #e3120b; font-family: Georgia, serif; margin-bottom: 40px; font-size: 2.4em; }}
    .edition-date {{ display: block; font-size: 0.6em; color: #666; margin-top: 10px; font-weight: normal; }}
    h2.section-header {{ background: #2c2c2c; color: #fff; padding: 12px 15px; margin-top: 50px; font-size: 1.2em; text-transform: uppercase; border-radius: 4px; }}
    div.article-link {{ margin: 12px 0; padding: 20px; background: #fff; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 5px solid transparent; }}
    div.article-link:hover {{ border-left-color: #e3120b; transform: translateY(-2px); }}
    a {{ text-decoration: none; color: #111; font-weight: bold; font-size: 1.15em; display: block; }}
</style>
</head>
<body>
<h1>The Economist {date_html}</h1>
"""
    current_section = None
    for a in articles:
        if a["section"] != current_section:
            current_section = a["section"]
            html += f'<h2 class="section-header">{current_section}</h2>'
        html += f'<div class="article-link"><a href="{a["path"]}">{a["title"]}</a></div>'
    html += "</body></html>"
    with open("output/index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__":
    main()
