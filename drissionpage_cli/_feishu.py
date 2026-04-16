"""
drissionpage_cli._feishu
~~~~~~~~~~~~~~~~~~~~~~~~
Feishu (Lark) document → Markdown converter.

Network-capture approach (v2)
-----------------------------
Feishu embeds the full document block tree in the SSR HTML response as
  window.DATA.clientVars.data.block_map
— a JSON object with one entry per block (text, headings, bullets, tables,
images, callouts, dividers, …).  No scrolling, no DOM scraping needed.

We capture the full network traffic on page load, find the SSR HTML in the
captured responses, extract block_map, walk the block tree, and write a
Markdown file with images saved locally alongside it.

Output layout
-------------
{out_dir}/
    {title}/
        {title}.md      ← Markdown; images referenced as images/img_NNN.ext
        images/
            img_001.png
            img_002.jpg
            ...
"""

import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote as _url_unquote


# ── constants ──────────────────────────────────────────────────────────────────

_ZERO_WIDTH = (
    "\u200b\u200c\u200d\u200e\u200f\ufeff"   # zero-width / BOM
    "\u2060\u2061\u2062\u2063\u2064"           # word joiner / invisible operators
    "\u2028\u2029"                             # line/paragraph separators
    "\ufff9\ufffa\ufffb"                       # interlinear annotation
)

# Regex covering all invisible/formatting Unicode ranges Feishu embeds in titles
_INVISIBLE_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    r"\u00ad\u200b-\u200f\u202a-\u202f"
    r"\u2060-\u206f\ufeff\ufff9-\ufffb]"
)

_HEADING_TYPES = {
    "heading1": "# ",
    "heading2": "## ",
    "heading3": "### ",
    "heading4": "#### ",
    "heading5": "##### ",
    "heading6": "###### ",
    # Feishu supports up to H9; Markdown caps at H6 — map extras to H6
    "heading7": "###### ",
    "heading8": "###### ",
    "heading9": "###### ",
}

_IMG_CT = frozenset([
    "image/png", "image/jpeg", "image/jpg", "image/webp",
    "image/gif", "image/avif",
])

# All attachment types we save from traffic (images + documents)
_ATTACH_CT = _IMG_CT | frozenset([
    "application/pdf",
    "application/zip", "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",        # xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation", # pptx
    "application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint",
    "text/plain", "text/csv",
])


# ── helpers ────────────────────────────────────────────────────────────────────

def _strip_zero_width(text: str) -> str:
    return _INVISIBLE_RE.sub("", text)


def _safe_title(raw: str) -> str:
    """Turn a document title into a safe filename (max 80 chars)."""
    cleaned = re.sub(
        r"[\x00-\x1f\x7f-\x9f\u00ad\u200b-\u200f\u2028\u2029"
        r"\u202a-\u202f\u2060-\u206f\ufeff\ufff0-\uffff]",
        "",
        raw,
    )
    name = cleaned.strip()
    # Strip Feishu-appended suffixes like " - 飞书云文档" / " - Feishu Docs"
    for suffix in (" - 飞书云文档", " - Feishu Docs", " - Lark Docs", " - 飞书"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    name = re.sub(r'[\\/:*?"<>|]', "-", name)
    name = re.sub(r"\s+", "_", name)[:80]
    return name or "feishu-doc"


# ── SSR HTML → block_map ───────────────────────────────────────────────────────

def _extract_block_map(ssr_html: str) -> tuple:
    """
    Extract window.DATA.clientVars.data.block_map from Feishu SSR HTML.

    Returns (block_map: dict, title: str).
    block_map is empty if not found.
    """
    # Detect old-format "DOC" (wikcn prefix) — uses a completely different structure
    if '"type":"DOC"' in ssr_html or '"type": "DOC"' in ssr_html:
        # Best-effort title extraction from old format
        m = re.search(r'window\.SERVER_DATA\s*=\s*Object\(\{"meta":\{"title":"([^"]+)"', ssr_html)
        title = _strip_zero_width(m.group(1)) if m else ""
        raise RuntimeError(
            "This document uses the old Feishu 'DOC' format (wikcn… URL prefix), "
            "which stores content differently from the modern 'docx' block format. "
            "Old-format DOC conversion is not yet supported. "
            f"Document: {title or '(unknown)'}"
        )

    # There are two clientVars occurrences; we want the one with block_map data.
    idx = ssr_html.find('clientVars: Object({"data":{"block_map":')
    if idx < 0:
        return {}, ""

    obj_start = ssr_html.find("Object(", idx) + len("Object(")
    depth = 0
    obj_end = obj_start
    for i, c in enumerate(ssr_html[obj_start:], obj_start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                obj_end = i + 1
                break

    try:
        cv = json.loads(ssr_html[obj_start:obj_end])
    except json.JSONDecodeError:
        return {}, ""

    block_map = cv.get("data", {}).get("block_map", {})

    # Title: use window.SERVER_DATA meta title (most reliable)
    m = re.search(
        r'window\.SERVER_DATA\s*=\s*Object\(\{"meta":\{"title":"([^"]+)"',
        ssr_html[:idx],
    )
    title = m.group(1) if m else ""

    return block_map, _strip_zero_width(title)


# ── attributed text (Etherpad/Changeset format) ────────────────────────────────

def _parse_attribs(attribs_str: str, num_to_attrib: dict) -> list:
    """
    Parse an Etherpad changeset attrib string into segments.
    Counts are base-36 encoded (e.g. '+h' = 17 chars, '+11' = 37 chars).
    Returns list of (char_count, {attr_key: attr_value}).
    """
    segments = []
    current_attrs = {}
    i = 0
    while i < len(attribs_str):
        c = attribs_str[i]
        if c == "*":
            i += 1
            j = i
            while j < len(attribs_str) and attribs_str[j] not in "+*":
                j += 1
            pair = num_to_attrib.get(attribs_str[i:j])
            if pair and len(pair) == 2 and pair[1] not in ("", "false", None):
                current_attrs[pair[0]] = pair[1]
            i = j
        elif c == "+":
            i += 1
            j = i
            while j < len(attribs_str) and attribs_str[j] not in "+*":
                j += 1
            raw = attribs_str[i:j]
            count = int(raw, 36) if raw else 0
            segments.append((count, dict(current_attrs)))
            current_attrs = {}
            i = j
        else:
            i += 1
    return segments


def _get_rich_text(block_data: dict) -> str:
    """Extract text with inline Markdown formatting from a block's text field."""
    text_data = block_data.get("text")
    if not text_data:
        return ""

    attrs_obj = text_data.get("initialAttributedTexts") or {}
    plain = ((attrs_obj.get("text") or {}).get("0") or "")
    attribs_str = ((attrs_obj.get("attribs") or {}).get("0") or "")
    apool = text_data.get("apool") or {}
    num_to_attrib = apool.get("numToAttrib") or {}

    plain = _strip_zero_width(plain)

    if not attribs_str or not num_to_attrib:
        return plain

    segments = _parse_attribs(attribs_str, num_to_attrib)
    pos = 0
    result = []

    for count, attrs in segments:
        chunk = plain[pos:pos + count]
        pos += count
        if not chunk:
            continue

        attrs.pop("author", None)   # not a display attribute

        link           = attrs.get("link")
        bold           = attrs.get("bold") == "true"
        italic         = attrs.get("italic") == "true"
        inline_code    = attrs.get("code") == "true"
        strike         = attrs.get("strikethrough") == "true"
        inline_eq      = attrs.get("inline_equation") or attrs.get("equation")

        if inline_eq:
            # Strip trailing newline Feishu sometimes appends to LaTeX
            latex = inline_eq.strip()
            chunk = f"${latex}$"
        elif attrs.get("inline-component"):
            # Inline component: mention_doc, mention_user, etc.
            try:
                comp = json.loads(attrs["inline-component"])
                ctype = comp.get("type", "")
                data  = comp.get("data", {})
                if ctype == "mention_doc":
                    title   = data.get("title", "document")
                    raw_url = data.get("raw_url", "")
                    chunk = f"[{title}]({raw_url})" if raw_url else title
                elif ctype == "mention_user":
                    name  = data.get("name") or data.get("en_name") or "user"
                    chunk = f"@{name}"
                else:
                    # Unknown inline component — show title or skip placeholder
                    chunk = data.get("title", "") or chunk
            except Exception:
                pass   # leave chunk as-is
        elif inline_code:
            chunk = f"`{chunk}`"
        elif bold and italic:
            chunk = f"***{chunk}***"
        elif bold:
            chunk = f"**{chunk}**"
        elif italic:
            chunk = f"*{chunk}*"

        if strike:
            chunk = f"~~{chunk}~~"
        if link:
            chunk = f"[{chunk}]({_url_unquote(link)})"

        result.append(chunk)

    if pos < len(plain):
        result.append(plain[pos:])

    return "".join(result)


# ── block tree → Markdown ──────────────────────────────────────────────────────

class _Converter:
    def __init__(self, block_map: dict, token_to_file: dict):
        self.block_map = block_map
        self.token_to_file = token_to_file   # {token: {"rel": ..., "cover": ...}}
        self._out: list = []

    def convert(self, root_id: str) -> str:
        root = self.block_map.get(root_id)
        if not root:
            return ""
        for child_id in root["data"].get("children", []):
            self._render(child_id, depth=0)
        result = "\n".join(self._out)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return _strip_zero_width(result).strip() + "\n"

    def _render(self, block_id: str, depth: int = 0):
        block = self.block_map.get(block_id)
        if not block:
            return
        data = block["data"]
        btype = data["type"]

        # heading
        if btype in _HEADING_TYPES:
            text = _get_rich_text(data)
            if text:
                self._out.extend(["", _HEADING_TYPES[btype] + text, ""])

        # paragraph
        elif btype == "text":
            text = _get_rich_text(data).strip()
            # Promote a sole inline formula to a block equation
            if text.startswith("$") and text.endswith("$") and text.count("$") == 2:
                latex = text[1:-1].strip()
                self._out.extend(["", f"$$\n{latex}\n$$", ""])
            # Standalone link (mention_doc) — needs blank lines to render as
            # a separate paragraph in Markdown
            elif re.match(r"^\[.+\]\(.+\)$", text):
                self._out.extend(["", text, ""])
            else:
                self._out.append(text)

        # bullet list item
        elif btype == "bullet":
            text = _get_rich_text(data)
            self._out.append("  " * depth + f"- {text}")
            for cid in data.get("children", []):
                self._render(cid, depth + 1)
            return  # children already handled above

        # ordered list item
        elif btype == "ordered":
            text = _get_rich_text(data)
            self._out.append("  " * depth + f"1. {text}")
            for cid in data.get("children", []):
                self._render(cid, depth + 1)
            return

        # task / todo
        elif btype == "todo":
            done = (data.get("todo") or {}).get("done", False)
            check = "x" if done else " "
            text = _get_rich_text(data)
            self._out.append(f"- [{check}] {text}")

        # image
        elif btype == "image":
            img_data = data.get("image") or {}
            token = img_data.get("token", "")
            name  = img_data.get("name", "image")
            info  = self.token_to_file.get(token) or {}
            rel   = info.get("rel")
            if rel:
                self._out.extend(["", f"![{name}]({rel})", ""])
            else:
                self._out.append(f"\n<!-- image token: {token} -->\n")

        # horizontal rule
        elif btype == "divider":
            self._out.extend(["", "---", ""])

        # callout
        elif btype == "callout":
            self._out.append("")
            for cid in data.get("children", []):
                child = self.block_map.get(cid)
                if child:
                    text = _get_rich_text(child["data"])
                    if text:
                        self._out.append(f"> {text}")
            self._out.append("")
            return

        # block quote
        elif btype == "quote":
            for cid in data.get("children", []):
                child = self.block_map.get(cid)
                if child:
                    text = _get_rich_text(child["data"])
                    if text:
                        self._out.append(f"> {text}")
            return

        # code block
        elif btype == "code":
            lang = (data.get("code") or {}).get("language", "").lower()
            text = _get_rich_text(data)
            self._out.extend(["", f"```{lang}", text, "```", ""])

        # block equation / formula (公式)
        elif btype == "equation":
            # Feishu stores LaTeX in data.equation.value
            latex = (data.get("equation") or {}).get("value", "").strip()
            if not latex:
                # Fallback: some versions store it in the text field
                latex = _get_rich_text(data).strip()
            if latex:
                self._out.extend(["", f"$$\n{latex}\n$$", ""])
            else:
                self._out.extend(["", "> 🔢 *[Formula — LaTeX not found]*", ""])

        # table
        elif btype == "table":
            self._render_table(data)
            return

        # table_cell / grid layout — just recurse into children
        elif btype in ("table_cell", "grid_column", "grid"):
            for cid in data.get("children", []):
                self._render(cid, depth)
            return

        # sub-page link
        elif btype == "page":
            text = _get_rich_text(data) or data.get("title", "")
            if text:
                self._out.extend(["", f"> 📄 {text}", ""])

        # block quote container (引用块) — render children with > prefix
        elif btype == "quote_container":
            self._out.append("")
            for cid in data.get("children", []):
                child = self.block_map.get(cid)
                if child:
                    text = _get_rich_text(child["data"]).strip()
                    if text:
                        for line in text.splitlines():
                            self._out.append(f"> {line}")
            self._out.append("")
            return

        # synced block (同步块) — content is in children, add a subtle label
        elif btype == "synced_source":
            self._out.append("")

        # diagram / canvas blocks (绘图, 思维导图, 流程图, UML图)
        # block_id is the key — screenshot saved by convert() via data-record-id
        elif btype == "whiteboard":
            info  = self.token_to_file.get(block_id) or {}
            rel   = info.get("rel")
            wb_token = data.get("token", "")
            if rel:
                self._out.extend(["", f"![diagram]({rel})", ""])
            else:
                self._out.extend(["", f"> 🎨 *[Diagram — screenshot not captured]*", ""])

        # file attachment (PDF, docx, xlsx, etc.)
        elif btype == "file":
            f     = data.get("file") or {}
            name  = f.get("name", "attachment")
            size  = f.get("size", 0)
            mime  = f.get("mimeType", "")
            token = f.get("token", "")
            size_str = (f"{size/1024/1024:.1f} MB" if size >= 1048576
                        else f"{size/1024:.1f} KB" if size >= 1024
                        else f"{size} B")
            info  = self.token_to_file.get(token) or {}
            rel   = info.get("rel")
            cover = info.get("cover")
            # Show cover thumbnail if captured
            if cover:
                self._out.extend(["", f"![{name} cover]({cover})", ""])
            # File link or metadata-only fallback
            if rel:
                self._out.extend(["", f"> 📎 [{name}]({rel})  `{mime}`  {size_str}", ""])
            else:
                meta = f"  `{mime}`  {size_str}" if mime else f"  {size_str}"
                self._out.extend(["", f"> 📎 **{name}**{meta}", f"> token: `{token}`", ""])

        # recurse children for any container block not explicitly handled above
        for cid in data.get("children", []):
            self._render(cid, depth)

    def _render_table(self, data: dict):
        rows_id  = data.get("rows_id", [])
        cols_id  = data.get("columns_id", [])
        cell_set = data.get("cell_set", {})

        if not rows_id or not cols_id:
            return

        self._out.append("")
        for row_idx, row_id in enumerate(rows_id):
            cells = []
            for col_id in cols_id:
                key = row_id + col_id
                cell_info  = cell_set.get(key, {})
                cell_block = self.block_map.get(cell_info.get("block_id", ""))
                cells.append(self._cell_text(cell_block))
            self._out.append("| " + " | ".join(cells) + " |")
            if row_idx == 0:
                self._out.append("|" + " --- |" * len(cols_id))
        self._out.append("")

    def _cell_text(self, cell_block) -> str:
        """Render a table_cell block's children as a single inline string."""
        if not cell_block:
            return ""
        parts = []
        for cid in cell_block["data"].get("children", []):
            child = self.block_map.get(cid)
            if not child:
                continue
            ctype = child["data"]["type"]
            if ctype == "image":
                img_data = child["data"].get("image") or {}
                token = img_data.get("token", "")
                name  = img_data.get("name", "image")
                info  = self.token_to_file.get(token) or {}
                rel   = info.get("rel")
                if rel:
                    parts.append(f"![{name}]({rel})")
            else:
                t = _get_rich_text(child["data"])
                if t:
                    parts.append(t)
        return "<br>".join(parts)


# ── image matching & saving ────────────────────────────────────────────────────

_IMG_DL_BASE = "/space/api/box/stream/download/v2/cover/"


def _fetch_missing_images(page, block_map: dict, token_to_rel: dict,
                          records: list, img_dir: Path, tmp_dir: Path) -> int:
    """
    Feishu uses a virtualised renderer that only loads images visible in the
    viewport.  Images outside the viewport never trigger network requests,
    so ``_save_attachments`` cannot match them.

    For each unmatched image token we construct the Drive download URL
    (pattern: /space/api/box/stream/download/v2/cover/{token}/) and trigger
    a fetch via JavaScript inside the authenticated browser session.  The
    network listener captures the response, which we then save normally.

    Returns the number of additionally saved images.
    """
    from drissionpage_cli import _collect_traffic

    # Identify unmatched image tokens
    missing = {}   # token → block_id
    for bid, block in block_map.items():
        bdata = block["data"]
        if bdata["type"] != "image":
            continue
        img = bdata.get("image") or {}
        token = img.get("token")
        if token and token not in token_to_rel:
            missing[token] = bid

    if not missing:
        return 0

    # Discover the image download origin from already-captured traffic
    dl_origin = None
    for rec in records:
        rec_url = rec.get("url", "")
        idx = rec_url.find(_IMG_DL_BASE)
        if idx > 0:
            dl_origin = rec_url[:idx]
            break

    if not dl_origin:
        # Derive from page URL: li.feishu.cn → internal-api-drive-stream.feishu.cn
        from urllib.parse import urlparse as _up
        p = _up(page.url)
        # feishu.cn or larksuite.com
        parts = p.netloc.split(".")
        root = ".".join(parts[-2:]) if len(parts) >= 2 else p.netloc
        dl_origin = f"https://internal-api-drive-stream.{root}"

    print(f"[feishu2md] {len(missing)} image(s) not in traffic, fetching directly…")

    # Build URLs and trigger fetches via JS
    urls_js = []
    for token, bid in missing.items():
        url = (
            f"{dl_origin}{_IMG_DL_BASE}{token}/"
            f"?fallback_source=1&height=1280"
            f"&mount_node_token={bid}&mount_point=docx_image"
            f"&policy=equal&width=1280"
        )
        urls_js.append(url)

    js_array = json.dumps(urls_js)
    page.listen.start()
    page.run_js(
        f"var urls = {js_array};"
        "urls.forEach(function(u) {"
        "  var img = new Image();"
        "  img.src = u;"
        "});"
    )
    time.sleep(2)

    fetch_dir = tmp_dir / "fetch_imgs"
    fetch_dir.mkdir(exist_ok=True)
    fetch_records = _collect_traffic(page, settle=2.0, out_dir=fetch_dir)

    # Match and save
    img_counter = sum(
        1 for v in token_to_rel.values()
        if (v.get("rel") or "").startswith("images/img_")
    )
    saved = 0
    img_dir.mkdir(parents=True, exist_ok=True)

    for rec in fetch_records:
        rec_url = rec.get("url", "")
        f = rec.get("file")
        if not f:
            continue
        ct = rec.get("content_type", "").lower().split(";")[0].strip()
        if ct not in _IMG_CT:
            continue

        for token in list(missing):
            if token not in rec_url:
                continue
            src = fetch_dir / f
            if not src.exists():
                continue
            if token in token_to_rel:
                continue

            if ct == "image/jpeg":       ext = ".jpg"
            elif ct == "image/webp":     ext = ".webp"
            elif ct == "image/gif":      ext = ".gif"
            elif ct == "image/avif":     ext = ".avif"
            else:                        ext = ".png"

            img_counter += 1
            fname = f"img_{img_counter:03d}{ext}"
            shutil.copy2(src, img_dir / fname)
            token_to_rel[token] = {"rel": f"images/{fname}", "cover": None}
            print(f"  [{img_counter:03d}] {fname}  {src.stat().st_size:,}B  ← {rec_url[:70]}")
            saved += 1
            break

    still_missing = [t for t in missing if t not in token_to_rel]
    if still_missing:
        print(f"  {len(still_missing)} image(s) still could not be fetched")

    return saved


def _save_attachments(block_map: dict, records: list, capture_dir: Path,
                      img_dir: Path) -> dict:
    """
    For each image or file block, find its responses in the captured traffic
    (matching by token in the URL) and copy to doc_dir.

    Images       → img_dir/images/img_NNN.ext
    File covers  → img_dir/images/cover_NNN.png  (thumbnail captured as PNG)
    Other files  → img_dir/files/original_name.ext

    Returns {token: info_dict} where info_dict has:
      - "rel"   : relative path from doc_dir (e.g. "images/img_001.png")
      - "cover" : relative path of cover thumbnail, or None (for file blocks)
    """
    # Collect all tokens we need: images + file attachments
    needed = {}   # token → {"name": str, "mime": str, "is_img": bool}
    for bid, block in block_map.items():
        bdata = block["data"]
        btype = bdata["type"]
        if btype == "image":
            img = bdata.get("image") or {}
            token = img.get("token")
            if token:
                needed[token] = {"name": img.get("name", "image"),
                                  "mime": img.get("mimeType", "image/png"),
                                  "is_img": True}
        elif btype == "file":
            f = bdata.get("file") or {}
            token = f.get("token")
            if token:
                needed[token] = {"name": f.get("name", "attachment"),
                                  "mime": f.get("mimeType", ""),
                                  "is_img": False}

    if not needed:
        return {}, 0, 0, 0

    files_dir = img_dir.parent / "files"
    img_dir.mkdir(parents=True, exist_ok=True)

    results      = {}   # token → {"rel": str, "cover": str|None}
    img_counter  = 0
    file_counter = 0

    for rec in records:
        url = rec.get("url", "")
        f   = rec.get("file")
        if not f:
            continue

        ct = rec.get("content_type", "").lower().split(";")[0].strip()
        is_attach = (ct in _ATTACH_CT or
                     bool(re.search(r"\.(png|jpe?g|webp|gif|avif|pdf|zip|docx|xlsx|pptx|txt|csv)",
                                    url, re.I)))
        if not is_attach:
            continue

        for token, info in list(needed.items()):
            if token not in url:
                continue

            src = capture_dir / f
            if not src.exists():
                continue

            if info["is_img"]:
                # ── regular image block ────────────────────────────────────
                if token in results:
                    continue
                if ct not in _IMG_CT:
                    continue
                if ct == "image/jpeg":       ext = ".jpg"
                elif ct == "image/webp":     ext = ".webp"
                elif ct == "image/gif":      ext = ".gif"
                elif ct == "image/avif":     ext = ".avif"
                else:
                    m = re.search(r"\.(png|jpe?g|webp|gif|avif)", url, re.I)
                    ext = "." + (m.group(1).replace("jpeg", "jpg") if m else "png")
                img_counter += 1
                fname = f"img_{img_counter:03d}{ext}"
                shutil.copy2(src, img_dir / fname)
                results[token] = {"rel": f"images/{fname}", "cover": None}
                print(f"  [{img_counter:03d}] {fname}  {src.stat().st_size:,}B  ← {url[:70]}")

            else:
                # ── file block ─────────────────────────────────────────────
                if ct in _IMG_CT:
                    # This is a cover thumbnail — save as preview image
                    if token not in results:
                        results[token] = {"rel": None, "cover": None}
                    if results[token].get("cover") is None:
                        img_counter += 1
                        fname = f"cover_{img_counter:03d}.png"
                        shutil.copy2(src, img_dir / fname)
                        results[token]["cover"] = f"images/{fname}"
                        print(f"  [cover] {fname}  {src.stat().st_size:,}B  ← {url[:70]}")
                else:
                    # Actual file content (PDF, docx, etc.)
                    if results.get(token, {}).get("rel") is not None:
                        continue
                    files_dir.mkdir(parents=True, exist_ok=True)
                    orig = re.sub(r'[\\/:*?"<>|]', "_", info["name"])
                    orig = re.sub(r"\s+", "_", orig)
                    dest = files_dir / orig
                    if dest.exists():
                        file_counter += 1
                        dest = files_dir / f"{dest.stem}_{file_counter}{dest.suffix}"
                    shutil.copy2(src, dest)
                    if token not in results:
                        results[token] = {"rel": None, "cover": None}
                    results[token]["rel"] = f"files/{dest.name}"
                    print(f"  [file] {dest.name}  {src.stat().st_size:,}B  ← {url[:70]}")
            break

    n_img   = sum(1 for v in results.values() if (v.get("rel") or "").startswith("images/"))
    n_cover = sum(1 for v in results.values() if v.get("cover"))
    n_file  = sum(1 for v in results.values() if (v.get("rel") or "").startswith("files/"))
    return results, n_img, n_cover, n_file


def _find_root_id(block_map: dict, doc_token: str) -> str:
    """Return the root 'page' block ID (preferring one matching doc_token)."""
    if doc_token in block_map and block_map[doc_token]["data"]["type"] == "page":
        return doc_token
    for bid, block in block_map.items():
        if block["data"]["type"] == "page":
            return bid
    # Last resort: block with no parent in the map
    child_ids = set()
    for b in block_map.values():
        child_ids.update(b["data"].get("children", []))
    orphans = set(block_map) - child_ids
    return next(iter(orphans), next(iter(block_map)))


_WORKER_INTERCEPT_JS = """
window.__extra_blocks = {};
var _OrigWorker = window.Worker;
window.Worker = function(url, opts) {
    var w = new _OrigWorker(url, opts);
    w.addEventListener('message', function(e) {
        try {
            var d = e.data;
            // Standard clientvar worker message format:
            // { postData: { clientvar: { data: { block_map: {...} } } } }
            var bm = d && d.postData && d.postData.clientvar &&
                     d.postData.clientvar.data &&
                     d.postData.clientvar.data.block_map;
            if (bm) Object.assign(window.__extra_blocks, bm);
        } catch(ex) {}
    });
    return w;
};
window.Worker.prototype = _OrigWorker.prototype;
"""


def _scroll_and_capture_blocks(page, block_map: dict, tmp_dir: Path) -> dict:
    """
    When the SSR block_map is truncated (has_more=True):
      1. Inject a window message listener to intercept web worker postMessage
         calls that deliver additional block data to the main thread
      2. Scroll the page step-by-step to trigger the worker to fetch remaining
         blocks (the worker fetches lazily as blocks are needed for rendering)
      3. Read the intercepted blocks from window.__extra_blocks
      4. Also drain the network listener as a secondary source

    Returns the (possibly augmented) block_map.
    """
    from drissionpage_cli import _collect_traffic

    # ── Step 1: check what the Worker wrapper already captured ────────────────
    # The wrapper was injected before page.get(), so proactive worker fetches
    # that happened during initial load are already in window.__extra_blocks.
    already_json = page.run_js("return JSON.stringify(window.__extra_blocks)")
    already = json.loads(already_json) if already_json else {}
    if already:
        before = len(block_map)
        block_map.update(already)
        print(f"  +{len(block_map)-before} blocks from initial worker fetch")

    # ── Step 2: restart network listener + scroll step-by-step ───────────────
    # Scrolling forces the virtualised renderer to request off-screen blocks,
    # which triggers the worker to fetch more pages via the cursor API.
    page.listen.start()

    _JS = (
        "var c=document.querySelector('.bear-web-x-container');"
        "var h=c?c.scrollHeight:document.body.scrollHeight;"
        "if(c) c.scrollTop={pos}; else window.scrollTo(0,{pos});"
        "return h;"
    )

    height = int(page.run_js(_JS.format(pos=0)) or 10_000)
    pos, step = 0, 500
    while pos <= height + step:
        new_h = int(page.run_js(_JS.format(pos=pos)) or height)
        height = max(height, new_h)
        time.sleep(0.5)
        pos += step

    time.sleep(2)   # let in-flight worker requests finish

    # ── Step 3: read any additional blocks the worker fetched during scroll ───
    after_json = page.run_js("return JSON.stringify(window.__extra_blocks)")
    after = json.loads(after_json) if after_json else {}
    if after:
        before = len(block_map)
        block_map.update(after)
        added = len(block_map) - before
        if added:
            print(f"  +{added} blocks from scroll-triggered worker fetch  "
                  f"(total: {len(block_map)})")
    else:
        print("  no additional blocks captured via Worker interception")

    # ── Step 4: also drain network listener as secondary source ───────────────
    print(f"  scrolled to {height}px, draining listener…")
    extra_dir = tmp_dir / "extra"
    extra_dir.mkdir(exist_ok=True)
    extra_records = _collect_traffic(page, settle=2.0, out_dir=extra_dir)
    print(f"  {len(extra_records)} additional requests captured")

    merged_net = 0
    for rec in extra_records:
        f = rec.get("file")
        if not f:
            continue
        fpath = extra_dir / f
        if not fpath.exists() or fpath.stat().st_size < 50:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
            if "block_map" not in text:
                continue
            payload = json.loads(text)
            bm = (
                (payload.get("data") or {}).get("block_map")
                or ((payload.get("data") or {}).get("clientVars") or {})
                   .get("data", {}).get("block_map")
                or {}
            )
            if bm:
                before = len(block_map)
                block_map.update(bm)
                added = len(block_map) - before
                if added:
                    merged_net += added
                    print(f"  +{added} blocks from {rec.get('url','')[:80]}")
        except Exception:
            pass

    if merged_net:
        print(f"  total after network merge: {len(block_map)} blocks")

    # Scroll back to top
    page.run_js(
        "var c=document.querySelector('.bear-web-x-container');"
        "if(c) c.scrollTop=0; else window.scrollTo(0,0);"
    )
    return block_map


# ── main orchestrator ──────────────────────────────────────────────────────────

def convert(page, url: str, out_dir: Path, save_html: bool = False) -> Path:
    """
    Convert a Feishu document to Markdown.

    1. Start network listener, navigate to URL, wait for load
    2. Drain listener into a temp capture directory
    3. Find the SSR HTML response (the one with clientVars block_map)
    4. Extract block_map and walk it to build Markdown
    5. Match image tokens to captured files; copy them to {out_dir}/images/
    6. Write {out_dir}/{title}.md

    Returns the path of the saved .md file.
    """
    # Deferred import to avoid circular dependency
    from drissionpage_cli import _collect_traffic

    out_dir = Path(out_dir)
    tmp_dir = Path(tempfile.mkdtemp(prefix="feishu_capture_"))
    cdp_script_id = None

    try:
        print(f"[feishu2md] → {url}")
        # Inject Worker wrapper BEFORE page.get() so it runs before Feishu's
        # JS creates the web worker that fetches additional block pages.
        cdp_script = page._run_cdp(
            "Page.addScriptToEvaluateOnNewDocument",
            source=_WORKER_INTERCEPT_JS,
        )
        cdp_script_id = (cdp_script or {}).get("identifier")

        page.listen.start()
        page.get(url)
        time.sleep(3)   # let JS render + async requests fire

        print("[feishu2md] draining network traffic…")
        records = _collect_traffic(page, settle=2.0, out_dir=tmp_dir)
        print(f"  {len(records)} requests captured")

        # ── find the SSR HTML that contains the block_map ──────────────────────
        doc_token = url.rstrip("/").split("/")[-1]
        ssr_html  = None
        ssr_file  = None

        for rec in records:
            rec_url = rec.get("url", "")
            f       = rec.get("file")
            ct      = rec.get("content_type", "")
            if (doc_token in rec_url
                    and "text/html" in ct
                    and f):
                fpath = tmp_dir / f
                if fpath.exists() and fpath.stat().st_size > 50_000:
                    ssr_html  = fpath.read_text(encoding="utf-8", errors="replace")
                    ssr_file  = f
                    print(f"  SSR HTML: {f}  ({len(ssr_html):,} chars)")
                    break

        if not ssr_html:
            raise RuntimeError(
                "Could not find the Feishu SSR HTML in network traffic.\n"
                "Make sure you are logged in and the document is accessible."
            )

        # ── extract block_map ─────────────────────────────────────────────────
        print("[feishu2md] extracting block map…")
        block_map, title = _extract_block_map(ssr_html)

        if not block_map:
            # For some wiki pages (especially external/public tenants) the SSR
            # has clientVars: undefined or empty. The web worker still fetches
            # blocks — check what it intercepted before trying a URL retry.
            extra_raw = page.run_js(
                "return JSON.stringify(window.__extra_blocks || {})"
            )
            extra = json.loads(extra_raw) if extra_raw else {}
            if extra:
                block_map = extra
                print(f"  {len(block_map)} blocks from Worker (SSR was empty)")
                if not title:
                    title = _strip_zero_width(page.title or "").split(" - ")[0].strip()

            if not block_map:
                # Some wiki pages serve clientVars: undefined in the SSR and load
                # the document via a different token embedded in SERVER_DATA.meta.
                # Extract that token and re-navigate to the canonical docx URL.
                real_token = None
                m = re.search(
                    r'window\.SERVER_DATA\s*=\s*Object\(\{"meta":\{[^}]{0,300}"token"\s*:\s*"([A-Za-z0-9]{15,40})"',
                    ssr_html,
                )
                if m:
                    real_token = m.group(1)
                    if len(real_token) > 32 or real_token == doc_token:
                        real_token = None
                if real_token:
                    from urllib.parse import urlparse as _up
                    _p = _up(url)
                    docx_url = f"{_p.scheme}://{_p.netloc}/docx/{real_token}"
                    print(f"  wiki has clientVars:undefined, retrying with docx URL:")
                    print(f"  → {docx_url}")

                    page.listen.start()
                    page.get(docx_url)
                    time.sleep(3)
                    extra_dir2 = tmp_dir / "retry"
                    extra_dir2.mkdir(exist_ok=True)
                    records2 = _collect_traffic(page, settle=2.0, out_dir=extra_dir2)
                    records = records + records2

                    final_url = page.url.rstrip("/")
                    doc_token = final_url.split("/")[-1]
                    print(f"  final URL: {final_url}")

                    html_recs = [
                        (r, extra_dir2 / r["file"])
                        for r in records2
                        if "text/html" in r.get("content_type", "")
                        and r.get("file")
                        and (extra_dir2 / r["file"]).exists()
                    ]
                    html_recs.sort(key=lambda x: x[1].stat().st_size, reverse=True)
                    for rec, fpath in html_recs:
                        if fpath.stat().st_size > 50_000:
                            ssr_html = fpath.read_text(encoding="utf-8", errors="replace")
                            ssr_file = rec["file"]
                            print(f"  SSR HTML (retry): {ssr_file}  ({len(ssr_html):,} chars)")
                            block_map, title = _extract_block_map(ssr_html)
                            if block_map:
                                break

            if not block_map:
                final_url = page.url
                if "/wiki/" in final_url:
                    raise RuntimeError(
                        f"This URL resolves to a wiki space root or navigation container:\n"
                        f"  {final_url}\n"
                        "Wiki space root pages have no document content to convert.\n"
                        "Open the link in a browser, navigate to a specific page inside\n"
                        "the wiki, and use that page's URL with the md command instead."
                    )
                raise RuntimeError(
                    "window.DATA.clientVars.data.block_map not found.\n"
                    "The page may not have loaded fully, or the Feishu format changed."
                )

        # Detect pagination: Feishu caps the initial SSR at ~239 blocks.
        # Remaining blocks are fetched by a web worker into the renderer's
        # internal state — inaccessible to us. Warn in the output.
        has_more_match = re.search(r'"has_more"\s*:\s*(true|false)', ssr_html)
        has_more = bool(has_more_match and has_more_match.group(1) == "true")

        # For wiki pages the URL token is a wiki-node ID that is NOT in the
        # block_map; the actual page block has a different ID.  Fall back to
        # _find_root_id so the children count is always accurate.
        real_root_id  = _find_root_id(block_map, doc_token)
        root_block    = block_map.get(real_root_id, {})
        total_children = len((root_block.get("data") or {}).get("children", []))
        loaded_children = sum(
            1 for cid in (root_block.get("data") or {}).get("children", [])
            if cid in block_map
        )

        if has_more:
            print(f"  {len(block_map)} blocks found  "
                  f"⚠ has_more=true: {loaded_children}/{total_children} root sections loaded")
            print("[feishu2md] scrolling to capture remaining blocks…")
            block_map = _scroll_and_capture_blocks(page, block_map, tmp_dir)
            # Recompute loaded_children after merge
            loaded_children = sum(
                1 for cid in (root_block.get("data") or {}).get("children", [])
                if cid in block_map
            )
            # Re-check: are there still missing children?
            has_more = loaded_children < total_children
            if has_more:
                print(f"  still truncated after scroll: {loaded_children}/{total_children} sections")
        else:
            print(f"  {len(block_map)} blocks found")

        if not title:
            title = _strip_zero_width(page.title or "feishu-doc").split(" - ")[0].strip()
        safe = _safe_title(title)
        print(f"[feishu2md] document: {title}")

        # All output goes into {out_dir}/{safe}/ so each document is self-contained
        doc_dir = out_dir / safe
        doc_dir.mkdir(parents=True, exist_ok=True)

        # ── save images & file attachments ───────────────────────────────────
        img_dir = doc_dir / "images"
        print(f"[feishu2md] saving attachments → {doc_dir}/")
        token_to_rel, n_img, n_cover, n_file = _save_attachments(
            block_map, records, tmp_dir, img_dir
        )
        print(f"  {n_img} image(s), {n_cover} cover(s), {n_file} file(s) saved")

        # ── fetch images not loaded by virtualised renderer ──────────────
        n_fetched = _fetch_missing_images(
            page, block_map, token_to_rel, records, img_dir, tmp_dir
        )
        if n_fetched:
            n_img += n_fetched
            print(f"  {n_img} image(s) total after direct fetch")

        # ── screenshot whiteboard blocks (绘图/思维导图/流程图/UML图) ──────────
        wb_block_ids = [bid for bid, b in block_map.items()
                        if b["data"]["type"] == "whiteboard"]
        if wb_block_ids:
            print(f"[feishu2md] screenshotting {len(wb_block_ids)} whiteboard(s)…")
            img_dir.mkdir(parents=True, exist_ok=True)

            pending  = set(wb_block_ids)   # block IDs not yet captured
            captured = {}                  # bid → fname
            wb_counter = 0

            scroll_js = (
                'var c=document.querySelector(".bear-web-x-container");'
                'var h=c?c.scrollHeight:document.body.scrollHeight;'
                'if(c) c.scrollTop={pos}; else window.scrollTo(0,{pos});'
                'return h;'
            )

            # Scroll step-by-step; after each step check if any pending
            # whiteboard has just appeared in the DOM and screenshot it
            # immediately — before the WASM virtualizer removes it again.
            height = int(page.run_js(scroll_js.format(pos=0)) or 10_000)
            pos, step = 0, 400
            while pos <= height + step:
                new_h = int(page.run_js(scroll_js.format(pos=pos)) or height)
                height = max(height, new_h)
                time.sleep(0.4)

                for bid in list(pending):
                    el = page.ele(f'@data-record-id={bid}', timeout=0)
                    if el:
                        wb_counter += 1
                        fname = f"whiteboard_{wb_counter:03d}.png"
                        try:
                            el.get_screenshot(path=str(img_dir / fname))
                            captured[bid] = fname
                            pending.discard(bid)
                            print(f"  [{wb_counter:03d}] {fname}  ← block {bid[:12]}…")
                        except Exception as e:
                            print(f"  [wb] screenshot failed {bid[:12]}: {e}")

                if not pending:
                    break   # all captured, no need to scroll further
                pos += step

            # Final pass: wait a moment and retry any still-pending whiteboards
            if pending:
                time.sleep(2)
                for bid in list(pending):
                    el = page.ele(f'@data-record-id={bid}', timeout=3)
                    if el:
                        wb_counter += 1
                        fname = f"whiteboard_{wb_counter:03d}.png"
                        try:
                            el.get_screenshot(path=str(img_dir / fname))
                            captured[bid] = fname
                            pending.discard(bid)
                            print(f"  [{wb_counter:03d}] {fname}  ← block {bid[:12]}… (retry)")
                        except Exception as e:
                            print(f"  [wb] retry failed {bid[:12]}: {e}")

            for bid, fname in captured.items():
                token_to_rel[bid] = {"rel": f"images/{fname}", "cover": None}
            if pending:
                print(f"  {len(pending)} whiteboard(s) not rendered by WASM")

            # Scroll back to top
            page.run_js(
                'var c=document.querySelector(".bear-web-x-container");'
                'if(c) c.scrollTop=0; else window.scrollTo(0,0);'
            )

        # ── convert to Markdown ───────────────────────────────────────────────
        print("[feishu2md] converting to Markdown…")
        root_id   = _find_root_id(block_map, doc_token)
        converter = _Converter(block_map, token_to_rel)
        body      = converter.convert(root_id)

        md = f"# {_strip_zero_width(title)}\n\n{body}"
        if has_more:
            missing = total_children - loaded_children
            note = (
                "\n\n---\n\n"
                f"> \u26a0\ufe0f **Document truncated**: Feishu's SSR payload is capped at ~239 blocks. "
                f"This document has {total_children} top-level sections; "
                f"{missing} were not included in the initial load and could not be captured. "
                "Open the document in a browser to read the full content.\n"
            )
            md += note
        md = re.sub(r"\n{3,}", "\n\n", md)
        print(f"  {len(md):,} chars")

        md_path = doc_dir / f"{safe}.md"
        md_path.write_text(md, encoding="utf-8")
        print(f"[feishu2md] done  → {md_path}")

        if save_html:
            html_path = doc_dir / f"{safe}_ssr.html"
            shutil.copy2(tmp_dir / ssr_file, html_path)
            print(f"[feishu2md] html  → {html_path}")

        return md_path

    finally:
        # Remove the CDP script injection so it doesn't affect future page loads
        if cdp_script_id:
            try:
                page._run_cdp(
                    "Page.removeScriptToEvaluateOnNewDocument",
                    identifier=cdp_script_id,
                )
            except Exception:
                pass
        shutil.rmtree(tmp_dir, ignore_errors=True)
