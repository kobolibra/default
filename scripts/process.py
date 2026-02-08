#!/usr/bin/env python3
import os
import sys
import zipfile
import shutil
import re
from datetime import datetime
from bs4 import BeautifulSoup, NavigableString

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
    
    # 先读取目录页，获取 section 顺序
    sections_order = extract_toc_structure('temp_epub')
    print(f"\nFound sections: {list(sections_order.keys())}")
    
    # 收集所有 HTML 文件，按文件名排序保持顺序
    html_files = []
    for root, dirs, files in os.walk('temp_epub'):
        for f in sorted(files):  # 排序保持顺序
            if f.endswith(('.html', '.xhtml', '.htm')):
                if any(x in f.lower() for x in ['nav', 'cover', 'copyright']):
                    continue
                filepath = os.path.join(root, f)
                html_files.append(filepath)
    
    print(f"\nProcessing {len(html_files)} HTML files...")
    
    # 按顺序处理文件，保持文章顺序
    all_articles = []
    for filepath in html_files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if 'The Economist' not in content and 'economist.com' not in content:
                continue
            
            articles = parse_html_file(content, filepath, sections_order)
            all_articles.extend(articles)
            
        except Exception as e:
            print(f"Error in {os.path.basename(filepath)}: {e}")
    
    print(f"\nTotal articles extracted: {len(all_articles)}")
    
    if not all_articles:
        print("ERROR: No articles found!")
        sys.exit(1)
    
    # 去重（按 slug），但保持顺序
    seen = set()
    unique_articles = []
    for art in all_articles:
        if art['slug'] not in seen:
            seen.add(art['slug'])
            unique_articles.append(art)
    
    print(f"Unique articles: {len(unique_articles)}")
    
    # 生成网站
    generate_index(unique_articles, sections_order)
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

def extract_toc_structure(epub_root):
    """从目录页提取 section 顺序"""
    sections = {}
    
    # 找目录文件
    toc_files = ['nav.xhtml', 'toc.xhtml', 'book_toc.html']
    toc_content = None
    
    for toc_file in toc_files:
        toc_path = os.path.join(epub_root, 'EPUB', toc_file)
        if os.path.exists(toc_path):
            with open(toc_path, 'r', encoding='utf-8', errors='ignore') as f:
                toc_content = f.read()
            break
    
    if not toc_content:
        return sections
    
    soup = BeautifulSoup(toc_content, 'html.parser')
    
    # 提取所有链接文本作为 section 名称
    order = 0
    for link in soup.find_all('a'):
        text = link.get_text(strip=True)
        # 过滤掉具体文章标题，保留 section 名称
        # Section 名称通常较短，且在大纲中
        if text and len(text) < 100 and not text.startswith('http'):
            # 标准化 section 名称
            section_key = text.strip()
            if section_key not in sections:
                sections[section_key] = {'order': order, 'articles': []}
                order += 1
    
    return sections

def parse_html_file(html_content, source_file, sections_order):
    """解析 HTML 文件"""
    articles = []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 移除 script 和 style
    for tag in soup(['script', 'style']):
        tag.decompose()
    
    # 获取 body
    body = soup.find('body')
    if not body:
        return articles
    
    # 策略：查找所有文章容器
    # Economist 文章通常有特定的 class 或结构
    
    # 方法1：找 h1 标题，然后收集后续内容直到下一个 h1
    headings = body.find_all(['h1', 'h2'])
    
    for i, heading in enumerate(headings):
        # 判断这是否是文章标题（而非 section 标题）
        heading_text = heading.get_text(strip=True)
        
        # 跳过太短的（可能是章节标记）
        if len(heading_text) < 5:
            continue
        
        # 跳过纯日期
        if re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(st|nd|rd|th)?,?\s+202[56]$', heading_text):
            continue
        
        # 找 section（通常在 heading 前面或上面）
        section = find_section_for_heading(heading, sections_order)
        
        # 找日期（通常在 heading 附近）
        date = find_date_near_heading(heading)
        
        # 收集内容（保持 HTML 结构）
        content_html = collect_content_until_next_heading(heading, headings[i+1] if i+1 < len(headings) else None)
        
        if len(content_html) > 200:
            article = create_article(heading_text, date, section, content_html)
            if article:
                articles.append(article)
                print(f"  ✓ [{section or 'Other'}] {heading_text[:50]}...")
    
    return articles

def find_section_for_heading(heading, sections_order):
    """找 heading 所属的 section"""
    # 向上查找 section 标记
    current = heading
    for _ in range(10):  # 向上找10层
        if current.previous_sibling:
            current = current.previous_sibling
            if isinstance(current, NavigableString):
                text = str(current).strip()
                # 检查是否是已知的 section
                for sec in sections_order.keys():
                    if sec.lower() in text.lower():
                        return sec
        else:
            current = current.parent
            if current and current.name in ['body']:
                break
    
    # 从文本内容推断
    full_text = heading.get_text()
    # 检查是否有 "Section | Title" 格式
    if '|' in full_text:
        parts = full_text.split('|')
        if len(parts) >= 2:
            section_candidate = parts[0].strip()
            for sec in sections_order.keys():
                if sec.lower() in section_candidate.lower():
                    return sec
    
    return ""

def find_date_near_heading(heading):
    """在 heading 附近找日期"""
    # 向后查找
    current = heading
    for _ in range(5):
        current = current.next_sibling
        if not current:
            break
        if isinstance(current, NavigableString):
            text = str(current).strip()
            # 匹配日期格式
            date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(st|nd|rd|th)?,?\s+202[56]', text)
            if date_match:
                return date_match.group(0)
        elif hasattr(current, 'get_text'):
            text = current.get_text(strip=True)
            date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(st|nd|rd|th)?,?\s+202[56]', text)
            if date_match:
                return date_match.group(0)
    
    return ""

def collect_content_until_next_heading(start_heading, next_heading):
    """收集从 start_heading 到 next_heading 之间的内容，保持 HTML 结构"""
    content_parts = []
    
    current = start_heading.next_sibling
    
    while current and current != next_heading:
        # 跳过导航元素
        if hasattr(current, 'name') and current.name in ['nav', 'header']:
            current = current.next_sibling
            continue
        
        # 收集内容
        if isinstance(current, NavigableString):
            text = str(current).strip()
            if text:
                content_parts.append(f'<p>{text}</p>')
        else:
            # 保持 HTML 标签，但修复图片路径
            html = str(current)
            # 修复图片路径
            html = re.sub(r'src=["\']static_images/', 'src="/images/', html)
            html = re.sub(r'src=["\']../static_images/', 'src="/images/', html)
            html = re.sub(r'src=["\']../../static_images/', 'src="/images/', html)
            content_parts.append(html)
        
        current = current.next_sibling
    
    return '\n'.join(content_parts)

def create_article(title, date, section, content_html):
    """创建文章"""
    
    # 清理标题
    title = re.sub(r'\s+', ' ', title).strip()
    
    # 移除标题中的 section 部分（如果有 | 分隔）
    if '|' in title:
        parts = title.split('|')
        if len(parts) >= 2:
            title = parts[-1].strip()
    
    # 如果标题是日期，尝试从内容找真正的标题
    if re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}', title):
        # 从内容第一行找
        first_line = re.search(r'<p>([^<]+)</p>', content_html)
        if first_line:
            potential_title = first_line.group(1).strip()
            if len(potential_title) > 10 and not re.match(r'^\d', potential_title):
                title = potential_title
                # 从内容中移除这行
                content_html = re.sub(r'^<p>' + re.escape(potential_title) + r'</p>', '', content_html, count=1)
    
    if len(title) > 150:
        title = title[:147] + "..."
    
    if not title or len(title) < 5:
        return None
    
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
    content_html = clean_content(content_html)
    
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
        figure {{
            margin: 20px 0;
            text-align: center;
        }}
        figcaption {{
            font-size: 14px;
            color: #666;
            font-style: italic;
            margin-top: 8px;
        }}
        a {{
            color: #e3120b;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        h2, h3 {{
            font-size: 24px;
            margin: 30px 0 15px 0;
            font-weight: normal;
        }}
    </style>
</head>
<body>
    {f'<div class="section">{section}</div>' if section else ''}
    <h1>{title}</h1>
    {f'<div class="date">{date}</div>' if date else ''}
    {content_html}
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

def clean_content(content_html):
    """清理内容"""
    # 移除下载信息
    content_html = re.sub(r'<p>This article was downloaded by zlibrary from https?://[^<]+</p>', '', content_html)
    content_html = re.sub(r'This article was downloaded by zlibrary from https?://\S+', '', content_html)
    
    # 移除空段落
    content_html = re.sub(r'<p>\s*</p>', '', content_html)
    
    # 修复连续多个换行
    content_html = re.sub(r'\n{3,}', '\n\n', content_html)
    
    return content_html.strip()

def generate_index(articles, sections_order):
    """生成索引页，保持 section 顺序"""
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    # 按 section 分组，保持顺序
    by_section = {}
    section_positions = {}
    
    for art in articles:
        sec = art.get('section', 'Other')
        if sec not in by_section:
            by_section[sec] = []
            # 记录 section 的原始顺序
            if sec in sections_order:
                section_positions[sec] = sections_order[sec].get('order', 999)
            else:
                section_positions[sec] = 999
        by_section[sec].append(art)
    
    # 按原始顺序排序 sections
    sorted_sections = sorted(by_section.keys(), key=lambda x: section_positions.get(x, 999))
    
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
    
    for sec in sorted_sections:
        html += f'<div class="section-title">{sec}</div>\n'
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
    for art in articles[:30]:
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
