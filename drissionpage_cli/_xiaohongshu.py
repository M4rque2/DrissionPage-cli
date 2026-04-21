"""
drissionpage_cli._xiaohongshu
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Xiaohongshu (RedNote) note → Markdown converter.

Extracts content from the rendered DOM of a Xiaohongshu note detail page
(xiaohongshu.com/explore/<note_id>).  The page must already be loaded in the
browser — navigate there by clicking a note card or entering a URL with valid
xsec_token (direct URL navigation is blocked by anti-bot protection).

We read: title, description text, images, video, author, date, location,
engagement stats, and hashtags from the live DOM, then download images/video
locally and produce a clean Markdown file.

Output layout
-------------
{out_dir}/
    {safe_title}/
        {safe_title}.md      ← Markdown; media referenced as images/… or video/…
        images/
            img_001.jpg
            ...
        video/
            video.mp4         ← only for video notes
"""

import re
import time
from pathlib import Path
from urllib.parse import urlparse


_SAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_title(title: str) -> str:
    s = _SAFE_CHARS.sub("_", title).strip().strip(".")
    return s[:120] or "xiaohongshu-note"


def _download_file(url: str, dest: Path, timeout: int = 60) -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": "https://www.xiaohongshu.com/",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"  [warn] download failed: {e}")
        return False


def _guess_ext(url: str) -> str:
    path = urlparse(url).path
    if "." in path.split("/")[-1]:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("jpg", "jpeg", "png", "webp", "gif", "avif", "svg"):
            return ext
    return "jpg"


def _extract_from_dom(page) -> dict:
    """Extract note data from the rendered DOM."""
    data = {}

    # Detect video note
    video_el = page.ele("tag:video", timeout=2)
    data["is_video"] = bool(video_el)

    # Title
    el = page.ele("css:#detail-title", timeout=3)
    if el:
        data["title"] = el.text.strip()

    # Description / body text — get the main note-text span, excluding tag links
    el = page.ele("css:#detail-desc", timeout=2)
    if el:
        note_span = el.ele("css:span.note-text > span", timeout=1)
        if not note_span:
            note_span = el.ele("css:span.note-text", timeout=1)
        raw = note_span.text.strip() if note_span else el.text.strip()
        if raw:
            # XHS uses space-tab-space or newline-tab as paragraph separators
            raw = re.sub(r"\s*\t\s*", "\n\n", raw)
            raw = re.sub(r"\n{3,}", "\n\n", raw)
            # Strip trailing inline hashtags (already extracted separately)
            raw = re.sub(r"(\s*#\S+)+\s*$", "", raw).rstrip()
            data["desc"] = raw

    # Author
    el = page.ele("css:.username", timeout=2)
    if not el:
        el = page.ele("css:.author", timeout=1)
    if el:
        data["author"] = el.text.strip().split("\n")[0].strip()

    # Date
    el = page.ele("css:.date", timeout=2)
    if el:
        data["date"] = el.text.strip()

    # IP location
    el = page.ele("css:.ip-location", timeout=2)
    if not el:
        el = page.ele("css:[class*=location]", timeout=1)
    if el:
        loc = el.text.strip()
        if loc:
            data["location"] = loc

    # Images — note images inside the detail container, excluding avatars
    note_imgs = page.eles("css:.note-image img", timeout=2)
    if not note_imgs:
        container = page.ele("css:#noteContainer", timeout=1)
        if container:
            note_imgs = container.eles("css:.swiper-slide img", timeout=1)
    if not note_imgs:
        note_imgs = page.eles("css:.carousel img", timeout=1)

    seen_srcs = set()
    image_urls = []
    for img in note_imgs:
        src = img.attr("src") or ""
        if not src or "avatar" in src:
            continue
        base = src.split("?")[0]
        if base in seen_srcs:
            continue
        seen_srcs.add(base)
        image_urls.append(src)
    data["image_urls"] = image_urls

    # Tags
    tag_els = page.eles("css:#detail-desc a.tag", timeout=2)
    if not tag_els:
        tag_els = page.eles("css:#detail-desc a[href*=search]", timeout=1)
    tags = []
    for t in tag_els:
        text = t.text.strip().lstrip("#")
        if text and text not in tags:
            tags.append(text)
    data["tags"] = tags

    # Engagement — likes, collects, comments
    like_el = page.ele("css:.like-wrapper .count, .like-wrapper", timeout=2)
    if like_el:
        text = like_el.text.strip()
        nums = re.findall(r"[\d.]+[万]?", text)
        if nums:
            data["likes"] = nums[0]

    collect_el = page.ele("css:.collect-wrapper .count, .collect-wrapper", timeout=1)
    if collect_el:
        text = collect_el.text.strip()
        nums = re.findall(r"[\d.]+[万]?", text)
        if nums:
            data["collects"] = nums[0]

    comment_el = page.ele("css:.chat-wrapper .count, .chat-wrapper", timeout=1)
    if not comment_el:
        comment_el = page.ele("css:[class*=comment-counts]", timeout=1)
    if comment_el:
        text = comment_el.text.strip()
        nums = re.findall(r"[\d.]+[万]?", text)
        if nums:
            data["comments"] = nums[0]

    return data


def _drain_video_url(page) -> str | None:
    """Drain the already-running network listener for a video MP4 URL."""
    for packet in page.listen.steps(timeout=3):
        url = getattr(packet, "url", "") or ""
        if "sns-video" in url and ".mp4" in url:
            return url
    return None


def _capture_video_url(page) -> str | None:
    """Start listener, trigger video replay, capture the MP4 URL."""
    page.listen.start()
    page.run_js(
        'var v=document.querySelector("video");'
        'if(v){v.currentTime=0;v.play();}'
    )
    time.sleep(3)
    return _drain_video_url(page)


def convert(page, url: str, out_dir: Path, save_html: bool = False,
            _pre_listened: bool = False) -> Path:
    """
    Convert a Xiaohongshu note page to Markdown.

    The page should already be loaded in the browser (via click or URL with
    valid xsec_token).  If the current URL doesn't match, we attempt navigation
    but it may be blocked by anti-bot protection.

    Set ``_pre_listened=True`` when ``page.listen.start()`` was called before
    navigating to this page (e.g. before clicking a note card in batch mode).
    This lets video capture drain the already-running listener instead of
    forcing a replay.

    Returns the path of the saved .md file.
    """
    out_dir = Path(out_dir)

    print(f"[xhs2md] → {url}")

    current = page.url.split("?")[0].rstrip("/")
    target = url.split("?")[0].rstrip("/")
    if current != target:
        page.get(url)
        time.sleep(4)

    if "/404" in page.url.split("?")[0]:
        raise RuntimeError(
            "Navigation was blocked by Xiaohongshu anti-bot protection.\n"
            "Instead of navigating directly, open the search page first,\n"
            "then click on a note card to open it with valid auth tokens."
        )

    print("[xhs2md] extracting note data from DOM…")
    data = _extract_from_dom(page)

    title = data.get("title", "")
    desc = data.get("desc", "")
    is_video = data.get("is_video", False)
    tags = data.get("tags", [])
    author = data.get("author", "")

    if not title and not desc and not tags and not is_video:
        raise RuntimeError(
            "Could not extract note content from the page.\n"
            "Make sure a Xiaohongshu note detail page is fully loaded."
        )

    if not title and desc:
        title = desc.split("\n")[0].strip()[:80]
    if not title and tags:
        title = " ".join(f"#{t}" for t in tags[:5])[:80]
    if not title and author:
        title = f"{author} - note"
    if not title:
        path_parts = urlparse(url).path.rstrip("/").split("/")
        title = f"xhs-{path_parts[-1]}" if path_parts else "xhs-note"

    safe = _safe_title(title)
    image_urls = data.get("image_urls", [])
    note_type = "video" if is_video else "image"
    print(f"[xhs2md] note: {title}")
    if author:
        print(f"  author: {author}")
    print(f"  type: {note_type}, images: {len(image_urls)}")

    doc_dir = out_dir / safe
    doc_dir.mkdir(parents=True, exist_ok=True)
    img_dir = doc_dir / "images"

    # Download images
    img_refs = []
    if image_urls:
        img_dir.mkdir(parents=True, exist_ok=True)
        print(f"[xhs2md] downloading {len(image_urls)} image(s)…")
        for i, img_url in enumerate(image_urls):
            ext = _guess_ext(img_url)
            fname = f"img_{i + 1:03d}.{ext}"
            dest = img_dir / fname
            if _download_file(img_url, dest):
                img_refs.append(f"images/{fname}")
                print(f"  [{i + 1:03d}] {fname}")
            else:
                img_refs.append(img_url)

    # Download video for video notes
    video_ref = None
    if is_video:
        video_url = None
        if _pre_listened:
            video_url = _drain_video_url(page)
        if not video_url:
            video_url = _capture_video_url(page)
        if not video_url:
            # Last resort: reload with listener to capture the stream
            print("  [retry] reloading page to capture video…")
            page.listen.start()
            page.get(page.url)
            time.sleep(5)
            video_url = _drain_video_url(page)
        if video_url:
            vid_dir = doc_dir / "video"
            vid_dir.mkdir(parents=True, exist_ok=True)
            vid_dest = vid_dir / "video.mp4"
            print(f"[xhs2md] downloading video…")
            if _download_file(video_url, vid_dest, timeout=120):
                size_mb = vid_dest.stat().st_size / (1024 * 1024)
                print(f"  video.mp4  ({size_mb:.1f} MB)")
                video_ref = "video/video.mp4"
            else:
                print("  [warn] video download failed, keeping URL reference")
                video_ref = video_url
        else:
            print("  [warn] video URL not found in network traffic")

    # Build Markdown
    md_parts = []
    md_parts.append(f"# {title}\n")

    meta_parts = []
    if author:
        meta_parts.append(f"Author: {author}")
    if data.get("location"):
        meta_parts.append(f"Location: {data['location']}")
    if data.get("date"):
        meta_parts.append(f"Date: {data['date']}")
    engagement = []
    if data.get("likes"):
        engagement.append(f"Likes: {data['likes']}")
    if data.get("collects"):
        engagement.append(f"Collects: {data['collects']}")
    if data.get("comments"):
        engagement.append(f"Comments: {data['comments']}")
    if engagement:
        meta_parts.append(" | ".join(engagement))
    if meta_parts:
        md_parts.append("> " + " | ".join(meta_parts) + "\n")

    if video_ref:
        md_parts.append(f'<video src="{video_ref}" controls width="100%"></video>\n')

    if desc:
        clean = desc.strip()
        if clean:
            md_parts.append(clean + "\n")

    if img_refs:
        for ref in img_refs:
            md_parts.append(f"![image]({ref})\n")

    tags = data.get("tags", [])
    if tags:
        md_parts.append("---\n")
        md_parts.append("Tags: " + " ".join(f"#{t}" for t in tags) + "\n")

    md = "\n".join(md_parts)
    md = re.sub(r"\n{3,}", "\n\n", md)

    md_path = doc_dir / f"{safe}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"[xhs2md] done  → {md_path}  ({len(md):,} chars)")

    if save_html:
        html_path = doc_dir / f"{safe}_ssr.html"
        html_path.write_text(page.html, encoding="utf-8")
        print(f"[xhs2md] html  → {html_path}")

    return md_path
