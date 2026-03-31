import os
import re
import sys
import mimetypes
import hashlib
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ASSET_PATTERNS = [
    re.compile(r'''(?:src|href)=["']([^"'#]+)''', re.IGNORECASE),
    re.compile(r'''url\(["']?([^"')]+)''', re.IGNORECASE),
]


def normalize_url(base, candidate):
    if not candidate:
        return None
    candidate = candidate.strip()
    if candidate.startswith(("data:", "javascript:", "mailto:", "tel:")):
        return None
    if any(ch in candidate for ch in ("<", ">", "{", "}", " ")):
        return None
    full = urljoin(base, candidate)
    full, _ = urldefrag(full)
    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return None
    return full


def iter_asset_urls(text, base_url):
    for pattern in ASSET_PATTERNS:
        for m in pattern.findall(text):
            u = normalize_url(base_url, m)
            if u:
                yield u


def local_path_for_url(url, out_dir):
    p = urlparse(url)
    host = p.netloc.replace(":", "_")
    path = p.path or "/"
    if path.endswith("/"):
        path = path + "index.html"
    rel = os.path.join(host, path.lstrip("/"))
    full = os.path.join(out_dir, rel)
    if len(full) > 220:
        stem, ext = os.path.splitext(os.path.basename(path))
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        safe_name = f"{(stem or 'asset')[:40]}-{digest}{ext[:10]}"
        full = os.path.join(out_dir, host, "__long__", safe_name)
    folder = os.path.dirname(full)
    os.makedirs(folder, exist_ok=True)
    return full


def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
        return data, ctype


def ensure_ext(path, ctype):
    if os.path.splitext(path)[1]:
        return path
    ext = mimetypes.guess_extension(ctype or "")
    if ext:
        return path + ext
    return path


def fallback_path_for_url(url, out_dir, ctype):
    p = urlparse(url)
    host = p.netloc.replace(":", "_")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    ext = mimetypes.guess_extension(ctype or "") or os.path.splitext(p.path)[1] or ".bin"
    full = os.path.join(out_dir, host, "__fallback__", f"{digest[:24]}{ext[:10]}")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    return full


def rewrite_links(text, base_url, url_to_local_rel):
    def repl_attr(match):
        orig = match.group(1)
        full = normalize_url(base_url, orig)
        if full in url_to_local_rel:
            return match.group(0).replace(orig, url_to_local_rel[full].replace('\\\\', '/'))
        return match.group(0)

    def repl_css(match):
        orig = match.group(1)
        full = normalize_url(base_url, orig)
        if full in url_to_local_rel:
            newv = url_to_local_rel[full].replace('\\\\', '/')
            return f"url('{newv}')"
        return match.group(0)

    text = re.sub(r'''(?:src|href)=["']([^"'#]+)''', repl_attr, text, flags=re.IGNORECASE)
    text = re.sub(r'''url\(["']?([^"')]+)''', repl_css, text, flags=re.IGNORECASE)
    return text


def main():
    if len(sys.argv) < 3:
        print("Usage: mirror_site.py <url> <out_dir>")
        raise SystemExit(1)

    start_url = sys.argv[1]
    out_dir = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    start_host = urlparse(start_url).netloc.lower()
    allowed_hosts = {start_host, start_host.replace("www.", ""), "www." + start_host.replace("www.", "")}
    max_files = 600

    to_visit = [start_url]
    visited = set()
    assets_text = {}
    url_to_file = {}

    while to_visit:
        if len(url_to_file) >= max_files:
            print(f"Reached max_files={max_files}, stopping crawl.")
            break
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        host = urlparse(url).netloc.lower()
        if host not in allowed_hosts:
            continue

        try:
            data, ctype = fetch(url)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as e:
            print(f"skip {url} ({e})")
            continue

        path = local_path_for_url(url, out_dir)
        path = ensure_ext(path, ctype)
        url_to_file[url] = path

        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError:
            path = fallback_path_for_url(url, out_dir, ctype)
            with open(path, "wb") as f:
                f.write(data)
            url_to_file[url] = path

        is_text = ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "application/xml", "")
        if is_text:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = data.decode("latin-1")
                except UnicodeDecodeError:
                    text = None

            if text:
                assets_text[url] = text
                for found in iter_asset_urls(text, url):
                    found_host = urlparse(found).netloc.lower()
                    if found_host not in allowed_hosts:
                        continue
                    if found not in visited and found not in to_visit:
                        to_visit.append(found)

    for base, txt in assets_text.items():
        base_file = url_to_file.get(base)
        if not base_file:
            continue

        base_dir = os.path.dirname(base_file)
        rel_map = {}
        for u, fpath in url_to_file.items():
            rel_map[u] = os.path.relpath(fpath, base_dir)

        rewritten = rewrite_links(txt, base, rel_map)
        try:
            with open(base_file, "w", encoding="utf-8", newline="") as f:
                f.write(rewritten)
        except OSError:
            pass

    root_host = urlparse(start_url).netloc.replace(":", "_")
    root_index = os.path.join(out_dir, root_host, "index.html")
    top_index = os.path.join(out_dir, "index.html")
    if os.path.exists(root_index):
        with open(root_index, "rb") as src, open(top_index, "wb") as dst:
            dst.write(src.read())

    print(f"Done. Downloaded {len(url_to_file)} files to {out_dir}")


if __name__ == "__main__":
    main()
