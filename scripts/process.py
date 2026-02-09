import os
import zipfile
import shutil
import re
from bs4 import BeautifulSoup

INPUT_EPUB = "input/economist.epub"

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

    h1s = body.find_all("h1")

    for h1 in h1s:
        title = h1.get_text(strip=True)
        if not title:
            continue

        content_nodes = []

        for sib in h1.next_siblings:
            if getattr(sib, "name", None) == "h1":
                break
            content_nodes.append(str(sib))

        content_html = "".join(content_nodes).strip()

        if len(content_html) < 200:
            continue

        # ✅ 修复图片路径
        content_html = re.sub(
            r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
            r'src="../images/\2"',
            content_html,
            flags=re.IGNORECASE
        )

        slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
        path = f"articles/{slug}.html"

        write_article(path, title, content_html)

        articles.append({
            "title": title,
            "path": path
        })

    return articles


# --------------------------------------------------

def write_article(path, title, content):
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body>
<h1>{title}</h1>
{content}
</body>
</html>
"""

    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

def generate_index(articles):
    html = "<html><body><h1>Economist</h1>"

    for a in articles:
        html += f'<div><a href="{a["path"]}">{a["title"]}</a></div>'

    html += "</body></html>"

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

if __name__ == "__main__":
    main()
