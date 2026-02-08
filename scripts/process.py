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
    
    # 复制图片
    copy_images('temp_epub', 'output/images')
    
    # 收集所有 HTML 文件
    html_files = []
    for root, dirs, files in os.walk('temp_epub'):
        for f in files:
            if f.endswith(('.html', '.xhtml', '.htm')):
                # 跳过明显不是文章的文件
                if any(x in f.lower() for x in ['nav', 'toc', 'cover', 'copyright']):
                    continue
                filepath = os.path.join(root, f)
                html_files.append(filepath)
    
    print(f"\nFound {len(html_files)} HTML files")
    
    # 解析所有文件
    all_articles = []
    for filepath in sorted(html_files):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 检查是否包含 Economist 内容
            if 'The Economist' not in content and 'economist.com' not in content:
                continue
            
            articles = parse_html_file(content, filepath)
            all_articles.extend(articles)
            
        except Exception as e:
            print(f"Error in {os.path.basename(filepath)}: {e}")
    
    print(f"\nTotal articles: {len(all_articles)}")
    
    if not all_articles:
        print("ERROR: No articles found!")
        sys.exit(1)
    
    # 去重（按 slug）
    seen = set()
    unique_articles = []
    for art in all_articles:
        if art['slug'] not in seen:
            seen.add(art['slug'])
            unique_articles.append(art)
    
    print(f"Unique articles: {len(unique_articles)}")
    
    # 生成
    generate_index(unique_articles)
    generate_rss(unique_articles)
    
    shutil.rmtree('temp_epub')
    print(f"\nSuccess! Generated {len(unique_articles)} articles")

def copy_images(source_dir, output_dir):
    for root, dirs, files in os.walk(source_dir):
        if 'images' in root.lower():
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
                    src = os.path.join(root, f)
                    dst = os.path.join(output_dir, f)
                    shutil.copy2(src, dst)

def parse_html_file(html_content, source_file):
    """解析 HTML 文件，可能包含多篇文章"""
    articles = []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 移除 script 和 style
    for tag in soup(['script', 'style']):
        tag.decompose()
    
    # 获取所有文本
    full_text = soup.get_text('\n', strip=True)
    
    # 检查是否是目录页（包含大量链接，短内容）
    links = soup.find_all('a')
    text_content = soup.get_text(strip=True)
    
    # 如果是目录页（链接多，文本少），也保留作为导航
    is_toc = len(links) > 5 and len(text_content) < 2000
    
    # 找文章 - 可能一个文件有多篇，或者一篇长文
    
    # 策略1：按 h1/h2 分割
    # 策略2：查找特定模式 "Leaders |" 等
    
    # 先找 section 标记（如 "Leaders | Greenback danger"）
    section_pattern = r'(Leaders|Briefing|United States|China|Asia|Europe|Britain|International|Business|Finance|Science|Culture|Obituary|Letters|By Invitation|The Americas|Middle East|Africa)\s*\|\s*([^\n]+)'
    
    matches = list(re.finditer(section_pattern, full_text, re.IGNORECASE))
    
    if matches:
        # 有明确的 section 标记，按此分割
        for i, match in enumerate(matches):
            section_name = match.group(1)
            subtitle = match.group(2).strip()
            
            # 提取这段内容
            start = match.start()
            end = matches[i+1].start() if i+1 < len(matches) else len(full_text)
            section_text = full_text[start:end]
            
            # 找标题（通常在下一行）
            lines = section_text.split('\n')
            title = ""
            date = ""
            content_lines = []
            
            for j, line in enumerate(lines[1:], 1):
                line = line.strip()
                if not line:
                    continue
                
                # 跳过 subtitle 重复
                if line == subtitle or subtitle in line:
                    continue
                
                # 找标题（大写开头，较长）
                if not title and len(line) > 10 and line[0].isupper():
                    title = line
                    continue
                
                # 找日期
                if not date and ('2026' in line or '2025' in line or 'January' in line or 'February' in line):
                    date = line
                    continue
                
                # 其余是内容
                if title:
                    content_lines.append(line)
            
            if title and len('\n'.join(content_lines)) > 100:
                article = create_article(title, date, section_name, '\n'.join(content_lines))
                if article:
                    articles.append(article)
                    print(f"  ✓ [{section_name}] {title[:50]}...")
    
    else:
        # 没有 section 标记，尝试按 h1/h2 分割
        body = soup.find('body')
        if body:
            # 找所有标题
            headings = body.find_all(['h1', 'h2', 'h3'])
            
            for i, h in enumerate(headings):
                title = h.get_text(strip=True)
                
                # 获取这个标题到下一个标题之间的内容
                content = []
                for sibling in h.find_next_siblings():
                    if sibling.name in ['h1', 'h2', 'h3']:
                        break
                    text = sibling.get_text(strip=True)
                    if text:
                        content.append(text)
                
                content_text = '\n'.join(content)
                
                # 提取日期（如果有）
                date = ""
                date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(st|nd|rd|th)?\s+202[56]', content_text)
                if date_match:
                    date = date_match.group(0)
                
                if len(content_text) > 200 and title:
                    article = create_article(title, date, "", content_text)
                    if article:
                        articles.append(article)
                        print(f"  ✓ {title[:50]}...")
    
    # 如果以上都失败，把整个文件作为一篇文章
    if not articles and len(text_content) > 500:
        # 尝试提取标题
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else "Untitled"
        
        # 清理内容
        for tag in soup(['nav', 'header', 'footer']):
            tag.decompose()
        
        body = soup.find('body')
        if body:
            article = create_article(title, "", "", str(body))
            if article:
                articles.append(article)
                print(f"  ✓ [Full page] {title[:50]}...")
    
    return articles

def create_article(title, date, section, content):
    """创建文章文件"""
    
    # 清理标题
    title = re.sub(r'\s+', ' ', title).strip()
    if len(title) > 150:
        title = title[:147] + "..."
    
    # 生成 slug
    slug = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()[:50]
    slug = re.sub(r'-+', '-', slug)
    
    # 确保唯一
    base_slug = slug
    counter = 1
    while os.path.exists(f'output/articles/{slug}.html'):
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    # 清理内容
    content = clean_content(content)
    
    art_path = f'articles/{slug}.html'
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} | The Economist</title>
    <style>
        body {{
            max-width: 720px;
            margin: 0 auto;
            padding: 40px 20px;
            font-family: Georgia, "Times New Roman", serif;
            font-size: 18px;
            line-height: 1.6;
            color: #222;
        }}
        .section {{
            color: #e3120b;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        h1 {{
            font-size: 32px;
            margin: 0 0 10px 0;
            line-height: 1.2;
            font-weight: normal;
        }}
        .date {{
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #ddd;
        }}
        p {{
            margin: 0 0 1em 0;
            text-align: justify;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
        }}
        a {{
            color: #e3120b;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    {f'<div class="section">{section}</div>' if section else ''}
    <h1>{title}</h1>
    {f'<div class="date">{date}</div>' if date else ''}
    {content}
</body>
</html>'''
    
    with open(f'output/{art_path}', 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {
        'title': title,
        'slug': slug,
        'path': art_path,
        'date': datetime.now().isoformat(),
        'section': section
    }

def clean_content(content):
    """清理内容"""
    # 如果是纯文本，包装成段落
    if not content.strip().startswith('<'):
        paragraphs = content.split('\n\n')
        paragraphs = [f'<p>{p.strip()}</p>' for p in paragraphs if p.strip()]
        content = '\n'.join(paragraphs)
    
    # 修复图片路径
    content = re.sub(r'src=["\']static_images/', 'src="/images/', content)
    content = re.sub(r'src=["\']../static_images/', 'src="/images/', content)
    
    # 移除下载信息
    content = re.sub(r'This article was downloaded by zlibrary from https?://\S+', '', content)
    
    return content

def generate_index(articles):
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    # 按 section 分组
    by_section = {}
    for art in articles:
        sec = art.get('section', 'Other')
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(art)
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>The Economist Weekly</title>
    <style>
        body {{
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #e3120b;
            margin-bottom: 8px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
        }}
        .section-title {{
            color: #e3120b;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 30px 0 15px 0;
            padding-bottom: 5px;
            border-bottom: 2px solid #e3120b;
        }}
        .article {{
            border-bottom: 1px solid #eee;
            padding: 12px 0;
        }}
        .article:hover {{
            background: #fafafa;
            margin: 0 -40px;
            padding-left: 40px;
            padding-right: 40px;
        }}
        .article a {{
            color: #222;
            text-decoration: none;
            font-size: 16px;
            display: block;
        }}
        .article a:hover {{
            color: #e3120b;
        }}
        .rss {{
            display: inline-block;
            margin-top: 30px;
            padding: 12px 24px;
            background: #e3120b;
            color: white;
            text-decoration: none;
            border-radius: 6px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>The Economist</h1>
        <div class="subtitle">{len(articles)} articles • Updated {datetime.now().strftime("%Y-%m-%d")}</div>
'''
    
    for sec in sorted(by_section.keys()):
        html += f'<div class="section-title">{sec or "Other"}</div>\n'
        for art in by_section[sec]:
            html += f'<div class="article"><a href="{art["path"]}">{art["title"]}</a></div>\n'
    
    html += f'''
        <a href="feed.xml" class="rss">📡 Subscribe via RSS</a>
    </div>
</body>
</html>'''
    
    with open('output/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

def generate_rss(articles):
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    items = []
    for art in articles[:30]:  # RSS 最多 30 篇
        try:
            with open(f'output/{art["path"]}', 'r', encoding='utf-8') as f:
                content = f.read()
            
            match = re.search(r'<body>(.*?)</body>', content, re.DOTALL)
            body = match.group(1) if match else content
            
            items.append(f'''
    <item>
      <title><![CDATA[{art["title"]}]]></title>
      <link>{base_url}/{art["path"]}</link>
      <guid>{base_url}/{art["path"]}</guid>
      <description><![CDATA[{art.get("section", "")} - {art["title"]}]]></description>
      <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
        <![CDATA[{body}]]>
      </content:encoded>
    </item>''')
        except Exception as e:
            print(f"Warning: RSS error for {art['title']}: {e}")
    
    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0">
  <channel>
    <title>The Economist Weekly</title>
    <link>{base_url}/</link>
    <description>Full-text articles from The Economist</description>
    <language>en</language>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
    {''.join(items)}
  </channel>
</rss>'''
    
    with open('output/feed.xml', 'w', encoding='utf-8') as f:
        f.write(rss)
    
    print(f"RSS: {base_url}/feed.xml")

if __name__ == '__main__':
    main()
