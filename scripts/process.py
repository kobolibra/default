#!/usr/bin/env python3
import os
import sys
import zipfile
import shutil
import re
from datetime import datetime
from bs4 import BeautifulSoup

def main():
    print("=" * 50)
    print("Starting EPUB processing...")
    print("=" * 50)
    
    # 清理
    if os.path.exists('output'):
        shutil.rmtree('output')
    if os.path.exists('temp_epub'):
        shutil.rmtree('temp_epub')
    
    os.makedirs('output/articles', exist_ok=True)
    os.makedirs('output/images', exist_ok=True)
    
    # 解压
    print("Extracting EPUB...")
    with zipfile.ZipFile('input/economist.epub', 'r') as z:
        z.extractall('temp_epub')
    
    # 找 content.opf
    opf_path = find_file('temp_epub', '.opf')
    epub_root = os.path.dirname(opf_path)
    
    # 复制图片
    copy_images(epub_root, 'output/images')
    
    # 解析文章（关键修改）
    articles = parse_articles_from_single_file(epub_root)
    
    print(f"\nTotal articles: {len(articles)}")
    
    if not articles:
        print("No articles found!")
        sys.exit(1)
    
    # 生成
    generate_index(articles)
    generate_rss(articles)
    
    shutil.rmtree('temp_epub')
    print("Done!")

def find_file(root, extension):
    for r, d, files in os.walk(root):
        for f in files:
            if f.endswith(extension):
                return os.path.join(r, f)
    return None

def copy_images(epub_root, output_dir):
    img_dirs = ['images', 'Images', 'OEBPS/images']
    for img_dir in img_dirs:
        img_path = os.path.join(epub_root, img_dir)
        if os.path.exists(img_path):
            for img in os.listdir(img_path):
                if img.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg')):
                    shutil.copy(os.path.join(img_path, img), output_dir)
            break

def parse_articles_from_single_file(epub_root):
    """从单个大文件中解析所有文章"""
    articles = []
    
    # 找包含主要内容的 HTML 文件（通常是最大的那个）
    html_files = []
    for r, d, files in os.walk(epub_root):
        for f in files:
            if f.endswith(('.html', '.xhtml', '.htm')):
                path = os.path.join(r, f)
                size = os.path.getsize(path)
                html_files.append((path, size))
    
    # 按大小排序，最大的应该是主内容文件
    html_files.sort(key=lambda x: x[1], reverse=True)
    
    if not html_files:
        return articles
    
    main_file = html_files[0][0]
    print(f"Main content file: {main_file} ({html_files[0][1]} bytes)")
    
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 用正则拆分文章
    # 模式：### 标题 ### 日期 或类似结构
    # 先找所有 ### 分隔的位置
    sections = re.split(r'\n(?=###)', content)
    
    current_section = ""
    current_subsection = ""
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
        
        # 检查是否是章节标题（如 # Leaders）
        if section.startswith('# ') and not section.startswith('###'):
            current_section = section.split('\n')[0].replace('# ', '').strip()
            print(f"  Section: {current_section}")
            continue
        
        # 检查是否是小节标题（如 ## The age of a treacherous...）
        if section.startswith('## ') and not section.startswith('###'):
            lines = section.split('\n')
            current_subsection = lines[0].replace('## ', '').strip()
            # 这可能就是文章标题
            continue
        
        # 解析文章（以 ### 开头）
        if section.startswith('###'):
            article = parse_single_article(section, current_section, current_subsection)
            if article:
                articles.append(article)
    
    return articles

def parse_single_article(section_text, section_name, subsection_name):
    """解析单篇文章"""
    lines = section_text.split('\n')
    
    # 第一行 ### 标题
    title_line = lines[0] if lines else ""
    title = title_line.replace('###', '').strip()
    
    # 找日期行（通常也是 ### 开头）
    date = ""
    content_start = 1
    
    for i, line in enumerate(lines[1:], 1):
        if line.startswith('###'):
            date = line.replace('###', '').strip()
            content_start = i + 1
            break
    
    # 剩余的是内容
    content = '\n'.join(lines[content_start:])
    
    # 清理内容
    content = clean_content(content)
    
    if len(content) < 100:
        return None
    
    # 生成 slug
    slug = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()[:50]
    slug = re.sub(r'-+', '-', slug)
    
    # 保存文件
    art_path = f'articles/{slug}.html'
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{title} | The Economist</title>
    <style>
        body {{ max-width: 720px; margin: 0 auto; padding: 40px 20px; 
               font-family: Georgia, serif; font-size: 18px; line-height: 1.6; }}
        h1 {{ font-size: 32px; margin-bottom: 10px; }}
        .meta {{ color: #666; font-size: 14px; margin-bottom: 30px; 
                border-bottom: 1px solid #ddd; padding-bottom: 20px; }}
        .section {{ color: #e3120b; font-size: 12px; text-transform: uppercase; 
                   letter-spacing: 1px; margin-bottom: 5px; }}
        img {{ max-width: 100%; height: auto; }}
        p {{ margin: 0 0 1em 0; }}
    </style>
</head>
<body>
    <div class="section">{section_name}</div>
    <h1>{title}</h1>
    <div class="meta">{date or "The Economist"}</div>
    {content}
</body>
</html>'''
    
    with open(f'output/{art_path}', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"  ✓ {title[:60]}...")
    
    return {
        'title': title,
        'slug': slug,
        'path': art_path,
        'date': datetime.now().isoformat(),
        'section': section_name
    }

def clean_content(content):
    """清理文章内容"""
    # 移除下载来源信息
    content = re.sub(r'This article was downloaded by zlibrary from https?://\S+', '', content)
    
    # 转换图片路径
    content = re.sub(r'!\[([^\]]*)\]\(static_images/([^)]+)\)', 
                     r'<img src="/images/\2" alt="\1"/>', content)
    
    # 转换 Markdown 链接
    content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', content)
    
    # 转换 **粗体**
    content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)
    
    return content.strip()

def generate_index(articles):
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>The Economist Weekly</title>
    <style>
        body {{ max-width: 800px; margin: 40px auto; padding: 0 20px; 
               font-family: -apple-system, sans-serif; }}
        h1 {{ color: #e3120b; }}
        .article {{ border-bottom: 1px solid #eee; padding: 15px 0; }}
        .article a {{ color: #222; text-decoration: none; font-size: 18px; }}
        .article a:hover {{ color: #e3120b; }}
        .section {{ color: #666; font-size: 13px; text-transform: uppercase; }}
    </style>
</head>
<body>
    <h1>The Economist</h1>
    <p>{len(articles)} articles • Updated {datetime.now().strftime("%Y-%m-%d")}</p>
'''
    
    for art in articles:
        html += f'''
    <div class="article">
        <div class="section">{art.get("section", "")}</div>
        <a href="{art["path"]}">{art["title"]}</a>
    </div>'''
    
    html += f'''
    <p><a href="feed.xml">📡 RSS Feed</a></p>
</body>
</html>'''
    
    with open('output/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

def generate_rss(articles):
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    items = []
    for art in articles[:20]:
        with open(f'output/{art["path"]}', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取 body
        match = re.search(r'<body>(.*?)</body>', content, re.DOTALL)
        body = match.group(1) if match else content
        
        items.append(f'''
    <item>
      <title><![CDATA[{art["title"]}]]></title>
      <link>{base_url}/{art["path"]}</link>
      <guid>{base_url}/{art["path"]}</guid>
      <description><![CDATA[{art["title"]}]]></description>
      <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
        <![CDATA[{body}]]>
      </content:encoded>
    </item>''')
    
    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0">
  <channel>
    <title>The Economist Weekly</title>
    <link>{base_url}/</link>
    <description>Full-text articles</description>
    {''.join(items)}
  </channel>
</rss>'''
    
    with open('output/feed.xml', 'w', encoding='utf-8') as f:
        f.write(rss)
    
    print(f"RSS: {base_url}/feed.xml")

if __name__ == '__main__':
    main()
