"""Readme cleanup.

Dumping the raw text on the page shows literal div tags and badge syntax,
because GitHub renders that and we do not. Rendering it as HTML is worse: a
readme is somebody else's input, so that is stored XSS.

What we do instead: drop the tags, drop the badges, convert the handful of
Markdown constructs that carry meaning, escape the rest. It is a preview, not
a reproduction.
"""
from __future__ import annotations

import html
import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_SCRIPTISH = re.compile(r"<(script|style|iframe|object|embed|svg)\b.*?</\1\s*>", re.S | re.I)
_TAG = re.compile(r"<[^>]{0,400}>")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_BADGE_LINK = re.compile(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_REF_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_REF_DEF = re.compile(r"^\s*\[[^\]]+\]:\s+\S+.*$", re.M)
_ANCHOR = re.compile(r"^#{1,6}\s*")
_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_CODE = re.compile(r"`([^`\n]+)`")
_HR = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_LIST = re.compile(r"^\s*(?:[-*+]|\d{1,2}[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_EMOJI_SHORTCODE = re.compile(r":[a-z0-9_+-]{2,30}:")


_CODE_SPAN = re.compile(r"(`[^`\n]+`)")


def _declaw(line: str) -> str:
    """Strip HTML from a line, except inside backticks.

    A readme that writes `<div>` in a code span means it literally, and
    stripping it leaves a hole in the sentence. _inline() escapes afterwards
    either way, so nothing here can turn into markup.
    """
    out = []
    for part in _CODE_SPAN.split(line):
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(part)
        else:
            out.append(html.unescape(_TAG.sub(" ", part)))
    return "".join(out)


def _inline(text: str) -> str:
    """Escape, then re-introduce only the inline markup we trust."""
    text = _BADGE_LINK.sub("", text)
    text = _MD_IMAGE.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _REF_LINK.sub(r"\1", text)
    text = _EMOJI_SHORTCODE.sub("", text)

    text = plain(text)
    out = html.escape(text, quote=False)
    out = _CODE.sub(lambda m: "<code>%s</code>" % m.group(1), out)
    out = _BOLD.sub(lambda m: "<b>%s</b>" % (m.group(1) or m.group(2)), out)
    out = _ITALIC.sub(lambda m: "<i>%s</i>" % m.group(1), out)
    return out.strip()


def render(raw: str, *, max_blocks: int = 60) -> str:
    """Sanitised HTML fragment. No tag here comes from the input."""
    if not raw:
        return ""

    text = raw.replace("\r\n", "\n")
    text = _COMMENT.sub("", text)
    text = _SCRIPTISH.sub("", text)
    text = _REF_DEF.sub("", text)

    blocks: list[str] = []
    buffer: list[str] = []
    in_code = False
    code: list[str] = []

    def flush_paragraph() -> None:
        if buffer:
            body = _inline(" ".join(buffer))
            if body:
                blocks.append("<p>%s</p>" % body)
            buffer.clear()

    for line in text.split("\n"):
        fence = line.strip().startswith("```") or line.strip().startswith("~~~")
        if fence:
            if in_code:
                if code:
                    blocks.append("<pre>%s</pre>" % html.escape("\n".join(code[:30])))
                code = []
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue

        bare = _declaw(line)

        if not bare.strip():
            flush_paragraph()
            continue
        if _HR.match(bare):
            flush_paragraph()
            blocks.append("<hr>")
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", bare.strip())
        if heading:
            flush_paragraph()
            level = min(len(heading.group(1)) + 2, 6)
            body = _inline(_ANCHOR.sub("", heading.group(2)))
            if body:
                blocks.append("<h%d>%s</h%d>" % (level, body, level))
            continue

        quote = _QUOTE.match(bare)
        if quote:
            flush_paragraph()
            body = _inline(quote.group(1))
            if body:
                blocks.append("<blockquote>%s</blockquote>" % body)
            continue

        item = _LIST.match(bare)
        if item:
            flush_paragraph()
            body = _inline(item.group(1))
            if body:
                blocks.append("<li>%s</li>" % body)
            continue

        if bare.strip().startswith("|"):      # tables rarely survive truncation
            continue

        buffer.append(bare.strip())
        if len(blocks) > max_blocks:
            break

    flush_paragraph()
    if in_code and code:
        blocks.append("<pre>%s</pre>" % html.escape("\n".join(code[:30])))

    # group consecutive <li> into one list
    grouped: list[str] = []
    pending: list[str] = []
    for block in blocks[:max_blocks]:
        if block.startswith("<li>"):
            pending.append(block)
            continue
        if pending:
            grouped.append("<ul>%s</ul>" % "".join(pending))
            pending = []
        grouped.append(block)
    if pending:
        grouped.append("<ul>%s</ul>" % "".join(pending))

    return "".join(grouped)


def summarise(raw: str, limit: int = 240) -> str:
    """First sentence or two as plain text, for tight spaces."""
    if not raw:
        return ""
    text = _COMMENT.sub("", raw.replace("\r\n", "\n"))
    text = _SCRIPTISH.sub("", text)
    text = _BADGE_LINK.sub("", text)
    text = _MD_IMAGE.sub("", text)
    text = _TAG.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _REF_DEF.sub("", text)

    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith(("#", ">", "|", "```", "---", "===")):
            continue
        if _HR.match(line) or _LIST.match(line):
            continue
        line = _EMOJI_SHORTCODE.sub("", _CODE.sub(r"\1", line))
        line = _BOLD.sub(lambda m: m.group(1) or m.group(2), line)
        line = html.unescape(line).strip()
        if len(line) > 40:
            return (line[:limit] + "...") if len(line) > limit else line
    return ""


_DASHES = [
    (re.compile(r"\s*[\u2014\u2013]\s*(?=[a-z0-9])"), ": "),
    (re.compile(r"\s*[\u2014\u2013]\s*(?=[A-Z])"), ". "),
    (re.compile(r"\s*[\u2014\u2013]\s*"), ", "),
]


def plain(text: str) -> str:
    """Tidy punctuation in text we show but did not write.

    Display only. The database, the API and the exports keep the original.
    """
    if not text:
        return ""
    out = text
    for pattern, repl in _DASHES:
        out = pattern.sub(repl, out)
    return out.replace("\u2026", "...").replace("\u00a0", " ").strip()
