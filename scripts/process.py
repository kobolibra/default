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
    
    # 清理旧文件
    if os.path.exists('output'):
        shutil.rmtree('output')
        print("Cleaned old output")
    
    if os.path.exists('temp_epub'):
        shutil.rmtree('temp_epub')
    
    os.makedirs('output/articles', exist_ok=True)
    os.makedirs('output/images', exist_ok=True)
    print("Created output directories")
    
    # 检查 EPUB 是否存在
    if not os.path.exists('input/economist.epub'):
        print("Error: input/economist.epub not found!")
        sys.exit(1)
    
    # 解压 EPUB
    print("\nExtracting EPUB...")
    try:
        with zipfile.ZipFile('input/economist.epub', 'r') as z:
            z.extractall('temp_epub')
        print("EPUB extracted successfully")
    except Exception as e:
        print(f"Error extracting EPUB: {e}")
        sys.exit(1)
    
    # 找 content.opf
    opf_path = find_file('temp_epub', '.opf')
    if not opf_path:
        print("Error: content.opf not found!")
        sys.exit(1)
    
    print(f"Found OPF: {opf_path}")
    epub_root = os.path.dirname(opf_path)
    
    # 复制图片
    img_copied = copy_images(epub_root, 'output/images')
    print(f"Copied {img_copied} images")
    
    # 解析文章
    articles = parse_articles(epub_root)
    print(f"\nTotal articles parsed: {len(articles)}")
    
    if not articles:
        print("Warning: No articles found!")
        sys.exit(1)
    
    # 生成文件
    generate_index(articles)
    generate_rss(articles)
    
    # 清理
    shutil.rmtree('temp_epub')
    print("\n" + "=" * 50)
    print("Processing complete!")
    print(f"Site URL: https://{os.environ.get('GITHUB_REPOSITORY', 'user/repo').replace('/', '.github.io/')}")
    print("=" * 50)

def find_file(root, extension):
    for r, d, files in os.walk(root):
        for f in files:
            if f.endswith(extension):
                return os.path.join(r, f)
    return None

def copy_images(epub_root, output_dir):
    img_dirs = ['images', 'Images', 'imgs', 'OEBPS/images', 'OEBPS/Images']
    count = 0
    
    for img_dir in img_dirs:
        img_path = os.path.join(epub_root, img_dir)
        if os.path.exists(img_path):
            for img in os.listdir(img_path):
                if img.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
                    try:
                        shutil.copy(os.path.join(img_path, img), output_dir)
                        count += 1
                    except:
                        pass
            if count > 0:
                break
    
    return count

def parse_articles(epub_root):
    articles = []
    content_files = []
    
    # 找所有 HTML 文件
    for root, dirs, files in os.walk(epub_root):
        # 跳过元数据目录
        if 'META-INF' in root:
            continue
            
        for f in files:
            if f.endswith(('.xhtml', '.html', '.htm')):
                filepath = os.path.join(root, f)
                # 跳过目录页和导航页
                if any(skip in f.lower() for skip in ['nav', 'toc', 'cover', 'copyright', 'index']):
                    continue
                content_files.append(filepath)
    
    # 按文件名排序
    content_files.sort()
    print(f"Found {len(content_files)} content files")
    
    for filepath in content_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 跳过太短的文件（可能是导航页）
            if len(content) < 2000:
                continue
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # 移除 script 和 style
            for tag in soup(['script', 'style']):
                tag.decompose()
            
            # 提取标题
            title = extract_title(soup, filepath)
            
            # 获取正文
            body = soup.find('body')
            if not body:
                continue
            
            # 清理并修复图片路径
            for img in body.find_all('img'):
                src = img.get('src', '')
                # 提取文件名
                img_name = os.path.basename(src.replace('\\', '/'))
                if img_name:
                    img['src'] = f'/images/{img_name}'
                    # 移除可能导致问题的属性
                    img.pop('srcset', None)
                    img.pop('sizes', None)
            
            # 生成唯一 slug
            slug = create_slug(title, articles)
            
            # 保存文章
            art_path = f'articles/{slug}.html'
            
            html_content = f'''<!DOCTYPE html>
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
            background: #fff;
        }}
        h1 {{ 
            font-size: 32px; 
            margin-bottom: 12px;
            line-height: 1.2;
            font-weight: normal;
        }}
        .meta {{
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #ddd;
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        h2, h3 {{
            font-size: 24px;
            margin-top: 30px;
            margin-bottom: 15px;
            font-weight: normal;
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
        a {{ color: #e3120b; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .back-link {{
            display: inline-block;
            margin-top: 40px;
            padding: 10px 0;
            color: #666;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="meta">The Economist • Weekly Edition</div>
    {str(body)}
    <a href="/" class="back-link">← Back to all articles</a>
</body>
</html>'''
            
            with open(f'output/{art_path}', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            articles.append({
                'title': title,
                'slug': slug,
                'path': art_path,
                'date': datetime.now().isoformat()
            })
            print(f"  ✓ {title[:60]}...")
            
        except Exception as e:
            print(f"  ✗ Error in {filepath}: {e}")
            continue
    
    return articles

def extract_title(soup, filepath):
    # 尝试多种方式找标题
    title = None
    
    # 1. HTML title 标签
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
    
    # 2. h1 标签
    if not title or len(title) < 3:
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
    
    # 3. h2 标签
    if not title or len(title) < 3:
        h2 = soup.find('h2')
        if h2:
            title = h2.get_text(strip=True)
    
    # 4. 从文件名推断
    if not title or len(title) < 3:
        filename = os.path.basename(filepath)
        title = filename.replace('.xhtml', '').replace('.html', '').replace('-', ' ').title()
    
    # 清理
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'^\d+\s*', '', title)  # 移除开头的数字
    
    if len(title) > 100:
        title = title[:97] + '...'
    
    if not title:
        title = "Untitled Article"
    
    return title

def create_slug(title, existing_articles):
    # 生成 URL slug
    slug = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()[:50]
    slug = re.sub(r'-+', '-', slug)  # 合并多个连字符
    
    # 确保唯一
    counter = 1
    original_slug = slug
    existing_slugs = {a['slug'] for a in existing_articles}
    
    while slug in existing_slugs:
        slug = f"{original_slug}-{counter}"
        counter += 1
    
    return slug

def generate_index(articles):
    # 获取仓库信息用于 URL
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>The Economist Weekly</title>
    <style>
        body {{ 
            max-width: 720px; 
            margin: 0 auto; 
            padding: 40px 20px; 
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
            font-size: 36px; 
            margin-bottom: 8px;
            font-weight: 600;
            color: #e3120b;
        }}
        .subtitle {{ 
            color: #666; 
            margin-bottom: 30px;
            font-size: 16px;
        }}
        .article-list {{ 
            list-style: none; 
            padding: 0; 
            margin: 0;
        }}
        .article-list li {{ 
            border-bottom: 1px solid #eee;
            padding: 16px 0;
            transition: background 0.2s;
        }}
        .article-list li:hover {{
            background: #fafafa;
            margin: 0 -40px;
            padding-left: 40px;
            padding-right: 40px;
        }}
        .article-list a {{ 
            color: #222; 
            text-decoration: none;
            font-size: 18px;
            font-weight: 500;
            display: block;
        }}
        .article-list a:hover {{ 
            color: #e3120b; 
        }}
        .article-date {{
            font-size: 13px;
            color: #999;
            margin-top: 4px;
        }}
        .rss-link {{
            display: inline-block;
            margin-top: 30px;
            padding: 12px 24px;
            background: #e3120b;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            transition: background 0.2s;
        }}
        .rss-link:hover {{
            background: #c40f0a;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>The Economist</h1>
        <div class="subtitle">Weekly Edition • {len(articles)} articles • Updated {datetime.now().strftime("%Y-%m-%d")}</div>
        
        <ul class="article-list">
'''
    
    for art in articles:
        date_str = art['date'][:10]
        html += f'''            <li>
                <a href="{art["path"]}">{art["title"]}</a>
                <div class="article-date">{date_str}</div>
            </li>
'''
    
    html += f'''        </ul>
        
        <a href="feed.xml" class="rss-link">📡 Subscribe via RSS</a>
        
        <div class="footer">
            Auto-generated from EPUB • Not affiliated with The Economist
        </div>
    </div>
</body>
</html>'''
    
    with open('output/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Generated index with {len(articles)} articles")

def generate_rss(articles):
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    # RSS 只包含最新 20 篇
    recent_articles = articles[:20]
    
    items = []
    for art in recent_articles:
        try:
            with open(f'output/{art["path"]}', 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取 body 内容
            match = re.search(r'<body>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
            if match:
                body_content = match.group(1)
                # 移除 back-link
                body_content = re.sub(r'<a[^>]*class="back-link"[^>]*>.*?</a>', '', body_content)
            else:
                body_content = content
            
            # 转义 CDATA 结束标记
            body_content = body_content.replace(']]>', ']]]]><![CDATA[>')
            
            # 格式化日期为 RSS 格式
            pub_date = datetime.fromisoformat(art['date']).strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            items.append(f'''
    <item>
      <title><![CDATA[{art["title"]}]]></title>
      <link>{base_url}/{art["path"]}</link>
      <guid isPermaLink="true">{base_url}/{art["path"]}</guid>
      <pubDate>{pub_date}</pubDate>
      <description><![CDATA[{art["title"]} - The Economist Weekly Edition]]></description>
      <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/"><![CDATA[{body_content}]]></content:encoded>
    </item>''')
            
        except Exception as e:
            print(f"  Warning: RSS item error for {art['title']}: {e}")
            continue
    
    build_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>The Economist Weekly</title>
    <link>{base_url}/</link>
    <description>Full-text articles from The Economist weekly edition</description>
    <language>en</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml" />
    {''.join(items)}
  </channel>
</rss>'''
    
    with open('output/feed.xml', 'w', encoding='utf-8') as f:
        f.write(rss)
    
    print(f"Generated RSS with {len(items)} items")
    print(f"Feed URL: {base_url}/feed.xml")

if __name__ == '__main__':
    main()
