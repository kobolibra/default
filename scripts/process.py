import os
import zipfile
import shutil
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import requests

# --------------------------------------------------
# 配置与常量 (保持你的原始设置)
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

    # 1. 解压 EPUB
    unzip_epub()

    # 2. 【新增针对性修改】删除广告页逻辑
    remove_ads_from_epub("temp_epub")

    # 3. 【新增针对性修改】重新打包干净的 EPUB 覆盖原文件，供后续推送
    repack_epub("temp_epub", INPUT_EPUB)

    # 4. 后续生成网页逻辑 (保持原样)
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
    print(f"✅ Done. Generated {len(articles)} articles.")
    
    # 5. 上传推送 (现在推送的是 repack 后的干净 EPUB)
    upload_to_nextcloud(INPUT_EPUB, edition_date)

# --------------------------------------------------
# 新增功能：广告页清洗与重新打包
# --------------------------------------------------

def remove_ads_from_epub(base_dir):
    """扫描并删除包含广告关键词的 HTML 页面"""
    print("🛡️ Scanning for ad pages...")
    removed_any = False
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith((".html", ".xhtml")):
                file_path = os.path.join(root, f)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as fr:
                        content = fr.read()
                        # 针对性匹配“优质App推荐”
                        if "优质App推荐" in content or "优质 App 推荐" in content:
                            print(f"🗑️ Found and removing ad page: {f}")
                            os.remove(file_path)
                            removed_any = True
                except:
                    continue
    
    if removed_any:
        # 如果删除了文件，必须清理 OPF 引用，否则 EPUB 会损坏
        clean_opf_references(base_dir)

def clean_opf_references(base_dir):
    """从 content.opf 中注销已删除的文件引用"""
    opf_path = None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".opf"):
                opf_path = os.path.join(root, f)
                break
    if not opf_path: return

    ET.register_namespace('', "http://www.idpf.org/2007/opf")
    tree = ET.parse(opf_path)
    root_node = tree.getroot()
    ns = {'opf': 'http://www.idpf.org/2007/opf'}

    # 1. 记录并删除 manifest 中对应的 item
    manifest = root_node.find("opf:manifest", ns)
    if manifest is None: manifest = root_node.find("manifest")
    
    deleted_ids = []
    opf_dir = os.path.dirname(opf_path)
    
    for item in list(manifest):
        href = item.get("href")
        full_href_path = os.path.abspath(os.path.join(opf_dir, href))
        if not os.path.exists(full_href_path):
            deleted_ids.append(item.get("id"))
            manifest.remove(item)

    # 2. 从 spine (阅读顺序) 中移除对应的条目
    spine = root_node.find("opf:spine", ns)
    if spine is None: spine = root_node.find("spine")
    for itemref in list(spine):
        if itemref.get("idref") in deleted_ids:
            spine.remove(itemref)

    tree.write(opf_path, encoding="utf-8", xml_declaration=True)
    print("✨ EPUB manifest references cleaned.")

def repack_epub(source_dir, output_file):
    """将修改后的文件夹重新压成 EPUB 格式"""
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(source_dir):
            for f in files:
                abs_path = os.path.join(root, f)
                rel_path = os.path.relpath(abs_path, source_dir)
                z.write(abs_path, rel_path)
    print(f"📦 Repacked clean EPUB to {output_file}")

# --------------------------------------------------
# 核心上传功能 (保持你运行成功的版本)
# --------------------------------------------------

def upload_to_nextcloud(local_file, edition_date):
    nc_url = os.getenv("NC_URL")
    nc_user = os.getenv("NC_USER")
    nc_pass = os.getenv("NC_PASS")

    if not all([nc_url, nc_user, nc_pass]):
        print("⚠️ Warning: Nextcloud Secrets are missing.")
        return

    base_url = nc_url.strip().rstrip('/')
    clean_date = re.sub(r'[^\w\s-]', '', edition_date).replace(' ', '_') if edition_date else "latest"
    remote_file_name = f"The_Economist_{clean_date}.epub"
    target_url = f"{base_url}/Economist/{remote_file_name}"
    
    print(f"🚀 Attempting direct upload to: {target_url}")

    try:
        with open(local_file, 'rb') as f:
            response = requests.put(
                target_url, 
                data=f, 
                auth=(nc_user, nc_pass),
                timeout=120
            )
        
        if response.status_code in [201, 204]:
            print(f"✅ Successfully uploaded to Nextcloud!")
        elif response.status_code == 404:
            print("⚠️ Folder 'Economist' not found. Trying root directory...")
            fallback_url = f"{base_url}/{remote_file_name}"
            with open(local_file, 'rb') as f:
                fb_res = requests.put(fallback_url, data=f, auth=(nc_user, nc_pass))
            if fb_res.status_code in [201, 204]:
                print(f"✅ Success! Uploaded to root directory.")
            else:
                print(f"❌ Fallback failed. Code: {fb_res.status_code}")
        else:
            print(f"❌ Upload Failed. Status Code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Network/Request Error: {str(e)}")

# --------------------------------------------------
# 基础解析功能 (完全保留你的原始代码)
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

def parse_html_file(filepath, current_section, css_filename):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    body = soup.find("body")
    if not body: return [], current_section

    articles = []
    last_found_rubric = "" 

    for tag in body.find_all(True):
        cls_list = tag.get("class", [])
        if isinstance(cls_list, str): cls_list = [cls_list]
        cls = " ".join(cls_list).lower()
        
        is_section = False
        if tag.name == "h2":
            txt = tag.get_text(strip=True)
            if any(x in cls for x in ["section", "department", "part", "header"]):
                is_section = True
            elif txt and len(txt) < 30 and txt.isupper():
                is_section = True
                
        if is_section:
            current_section = tag.get_text(strip=True)
            last_found_rubric = "" 
            continue

        is_rubric = any(x in cls for x in ["rubric", "kicker", "teaser", "flytitle", "deck", "subhead"])
        if not is_rubric and tag.name == "h2":
            txt = tag.get_text(strip=True)
            if txt and (len(txt) < 100 or "|" in txt):
                is_rubric = True
                
        if is_rubric:
            last_found_rubric = tag.get_text(strip=True)
            continue

        if tag.name == "h1":
            title = tag.get_text(strip=True)
            if not title: continue

            clean_sec = current_section.strip()
            clean_rub = last_found_rubric.strip()
            
            if clean_rub:
                if "|" in clean_rub:
                    rub_parts = [p.strip() for p in clean_rub.split("|", 1)]
                    if rub_parts[0].lower() == clean_sec.lower():
                        header_display = clean_rub
                    else:
                        header_display = f"{clean_sec} | {clean_rub}"
                elif clean_rub.lower().startswith(clean_sec.lower()):
                    header_display = clean_rub
                elif clean_rub.lower() != clean_sec.lower():
                    header_display = f"{clean_sec} | {clean_rub}"
                else:
                    header_display = clean_sec
            else:
                header_display = clean_sec

            fly_title_html = f'<div class="fly-title">{header_display}</div>'
            
            content_nodes = [tag]
            for sib in tag.next_siblings:
                if getattr(sib, "name", None) in ["h1", "h2"]: break
                content_nodes.append(sib)

            article_html = fly_title_html + "".join(str(x) for x in content_nodes)
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
