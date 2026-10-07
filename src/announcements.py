"""Read announcement posts without traversing reply/edit/subscribe actions."""
import hashlib
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from src.course_library import atomic_write, now


def parse_posts(soup, url):
    posts = soup.select('[data-region="post"]') or soup.select('.forumpost')
    result = []
    for post in posts:
        body = post.select_one('[data-region="post-content"]') or post.select_one('.posting') or post.select_one('.post-content-container')
        if body is None:
            continue
        title = post.select_one('[data-region="post-title"], .subject, h3, h4')
        author = post.select_one('[data-region="post-author"], .author')
        stamp = post.select_one('time')
        identity = post.get('data-post-id') or post.get('id', '')
        # Stable Moodle post IDs are required, never hash text as event identity.
        match = re.search(r'(\d+)$', identity)
        if not match:
            continue
        links = []
        for a in post.select('a[href]'):
            target = urljoin(url, a['href'])
            path = urlsplit(target).path
            if '/pluginfile.php/' in path and '/attachment/' in path:
                links.append((target, a.get_text(' ', strip=True) or 'Announcement attachment'))
        result.append({'id': match[1], 'title': title.get_text(' ', strip=True) if title else 'Announcement',
                       'author': author.get_text(' ', strip=True) if author else '',
                       'posted_at': stamp.get('datetime', '') if stamp else '',
                       'text': body.get_text('\n', strip=True), 'attachments': links,
                       'url': url.split('#')[0]+'#p'+match[1]})
    return result


def save_posts(library, soup, url):
    posts = parse_posts(soup, url)
    if not posts:
        raise ValueError('Announcement page has no readable posts; coverage incomplete.')
    for post in posts:
        path = Path('pages') / ('announcement-'+post['id']+'.md')
        content = ('# '+post['title']+'\n\n'+post['text']+'\n').encode()
        atomic_write(library.root/path, content)
        library.manifest['pages'][post['url']] = {
            'title': post['title'], 'path': str(path), 'sha256': hashlib.sha256(content).hexdigest(),
            'verified_at': now(), 'source_type': 'announcement',
            'posted_at': post['posted_at'], 'author': post['author'], 'post_id': post['id']}
        library.seen_pages.add(post['url'])
        for target, title in post['attachments']:
            try:
                response = library.fetch(target, library.file_headers(target))
                if response.status_code == 304:
                    response.close()
                    library.manifest['files'][target]['verified_at'] = now()
                    library.seen_files.add(target)
                    library.counts['unchanged'] += 1
                else:
                    library.store_file(target, title, response)
            except Exception:
                library.errors.append({'url': target, 'reason': 'Announcement attachment could not be downloaded.'})
