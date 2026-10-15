"""Convert the model's Markdown into Telegram-safe HTML and split it into messages.

Telegram limits a message to 4096 characters and rejects HTML with unbalanced tags,
so every piece is rendered on its own and code blocks are never cut in the middle
of a tag.
"""
import html
import re

LIMIT = 3800  # safe margin below Telegram's 4096
SEP = "\n\n"
RAW_TEXT_CHUNK = 1800
RAW_CODE_LINE = 500


def _segments(md: str) -> list[tuple[str, str, str]]:
    """Split Markdown into ('text'|'code', lang, content) segments."""
    segments: list[tuple[str, str, str]] = []
    text_buf: list[str] = []
    code_buf: list[str] | None = None
    lang = ""

    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if code_buf is None:
                if text_buf:
                    segments.append(("text", "", "\n".join(text_buf)))
                    text_buf = []
                info = stripped[3:].strip().split()
                lang = re.sub(r"[^\w+#.-]", "", info[0]) if info else ""
                code_buf = []
            else:
                segments.append(("code", lang, "\n".join(code_buf)))
                code_buf = None
            continue
        (text_buf if code_buf is None else code_buf).append(line)

    if code_buf is not None:  # unclosed fence (truncated answer)
        segments.append(("code", lang, "\n".join(code_buf)))
    if text_buf:
        segments.append(("text", "", "\n".join(text_buf)))
    return segments


def _inline(text: str) -> str:
    """Render headings, bold, bullets and `inline code` as Telegram HTML."""
    codes: list[str] = []

    def stash(match: re.Match) -> str:
        codes.append(match.group(1))
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", r"<b>\1</b>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?m)^([ \t]*)[-*][ \t]+", r"\1• ", text)
    text = re.sub(
        r"\x00(\d+)\x00",
        lambda m: f"<code>{html.escape(codes[int(m.group(1))], quote=False)}</code>",
        text,
    )
    return text


def _split_raw(raw: str, size: int) -> list[str]:
    """Split raw text on line boundaries, hard-splitting overlong lines."""
    chunks: list[str] = []
    current = ""
    for line in raw.split("\n"):
        while len(line) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:size])
            line = line[size:]
        if current and len(current) + 1 + len(line) > size:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def _text_pieces(text: str) -> list[str]:
    pieces: list[str] = []
    for paragraph in re.split(r"\n{2,}", text.strip("\n")):
        if not paragraph.strip():
            continue
        for raw in _split_raw(paragraph, RAW_TEXT_CHUNK):
            rendered = _inline(raw)
            if len(rendered) > LIMIT:  # extremely escape-heavy text: fall back to plain
                rendered = html.escape(raw, quote=False)[:LIMIT]
            pieces.append(rendered)
    return pieces


def _code_pieces(lang: str, code: str) -> list[str]:
    open_tag = f'<pre><code class="language-{lang}">' if lang else "<pre><code>"
    close_tag = "</code></pre>"
    budget = LIMIT - len(open_tag) - len(close_tag)

    lines: list[str] = []
    for line in code.split("\n"):
        while len(line) > RAW_CODE_LINE:
            lines.append(line[:RAW_CODE_LINE])
            line = line[RAW_CODE_LINE:]
        lines.append(line)

    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        escaped = html.escape(line, quote=False)
        if current and size + len(escaped) + 1 > budget:
            pieces.append(open_tag + "\n".join(current) + close_tag)
            current, size = [], 0
        current.append(escaped)
        size += len(escaped) + 1
    if current:
        pieces.append(open_tag + "\n".join(current) + close_tag)
    return pieces


def render(markdown: str) -> list[str]:
    """Return a list of Telegram-HTML messages, each safely below the size limit."""
    pieces: list[str] = []
    for kind, lang, content in _segments(markdown):
        if kind == "code":
            if content.strip():
                pieces.extend(_code_pieces(lang, content))
        else:
            pieces.extend(_text_pieces(content))

    messages: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(SEP) + len(piece) > LIMIT:
            messages.append(current)
            current = piece
        else:
            current = f"{current}{SEP}{piece}" if current else piece
    if current:
        messages.append(current)
    return messages or ["…"]


def strip_tags(rendered: str) -> str:
    """Plain-text fallback when Telegram rejects the HTML."""
    return html.unescape(re.sub(r"<[^>]+>", "", rendered))
