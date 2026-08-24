"""
Telegram message formatting and chunking utilities.
Converts Markdown to clean, safe Telegram HTML and splits long responses.
"""

import re
import html
from typing import List, Optional


def escape_html(text: str) -> str:
    """Escape &, <, > for Telegram HTML."""
    return html.escape(text, quote=False)


def markdown_to_telegram_html(md_text: str) -> str:
    """
    Convert standard Markdown text to Telegram-compatible HTML.
    Safely escapes special characters and preserves code formatting.
    """
    if not md_text:
        return ""

    # Placeholder storage for code blocks and inline code to prevent regex collision
    code_blocks = []
    inline_codes = []

    # 1. Extract fenced code blocks (```lang ... ```)
    def save_code_block(match):
        lang = match.group(1) or ""
        code_content = match.group(2)
        escaped_code = escape_html(code_content.strip("\n"))
        index = len(code_blocks)
        if lang:
            tag = f'<pre><code class="language-{escape_html(lang)}">{escaped_code}</code></pre>'
        else:
            tag = f'<pre>{escaped_code}</pre>'
        code_blocks.append(tag)
        return f"\x02CB{index}\x03"

    text = re.sub(r"```([a-zA-Z0-9_\-\+\.#]*)\n?(.*?)```", save_code_block, md_text, flags=re.DOTALL)

    # 2. Extract inline code (`code`)
    def save_inline_code(match):
        code_content = match.group(1)
        escaped_code = escape_html(code_content)
        index = len(inline_codes)
        inline_codes.append(f"<code>{escaped_code}</code>")
        return f"\x02IC{index}\x03"

    text = re.sub(r"`([^`\n]+)`", save_inline_code, text)

    # 3. Escape all remaining HTML entities in regular text
    text = escape_html(text)

    # 4. Headers: # Header -> <b>Header</b>
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 5. Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 6. Italic: *text* or _text_ (be careful with isolated underscores)
    text = re.sub(r"(?<!\w)\*([^\*\n]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)

    # 7. Strikethrough: ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 8. Links: [label](url) -> <a href="url">label</a>
    def replace_link(match):
        label = match.group(1)
        url = match.group(2)
        return f'<a href="{url}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", replace_link, text)

    # 9. Blockquotes: > quote -> <blockquote>quote</blockquote>
    def replace_blockquotes(match):
        quote_body = match.group(0)
        lines = [re.sub(r"^&gt;\s?", "", line) for line in quote_body.splitlines()]
        clean_quote = "\n".join(lines).strip()
        return f"<blockquote>{clean_quote}</blockquote>"

    text = re.sub(r"(?:^&gt;.*(?:\n|$))+", replace_blockquotes, text, flags=re.MULTILINE)

    # 10. Restore inline codes
    for idx, inline_html in enumerate(inline_codes):
        text = text.replace(f"\x02IC{idx}\x03", inline_html)

    # 11. Restore code blocks
    for idx, block_html in enumerate(code_blocks):
        text = text.replace(f"\x02CB{idx}\x03", block_html)

    return text


def split_text_chunks(text: str, max_chars: int = 3800) -> List[str]:
    """
    Split long text into chunks smaller than max_chars.
    Attempts to split by paragraphs, then newlines, then spaces.
    Handles HTML pre/code tags so blocks aren't left unclosed.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = ""
    lines = text.split("\n")

    in_pre = False
    pre_tag = "<pre>"

    for line in lines:
        # Track opening/closing pre tags in this line
        line_opens_pre = "<pre" in line
        line_closes_pre = "</pre>" in line

        # If adding this line exceeds max_chars
        if len(current) + len(line) + 1 > max_chars:
            if current:
                # If currently inside a <pre> block, close it for this chunk
                if in_pre:
                    current += "\n</code></pre>" if "</code" in current and "<code" in current else "\n</pre>"
                chunks.append(current)
                
                # Start new chunk
                if in_pre:
                    current = f"{pre_tag}\n{line}"
                else:
                    current = line
            else:
                # Single line is larger than max_chars
                chunks.append(line[:max_chars])
                current = line[max_chars:]
        else:
            if current:
                current += "\n" + line
            else:
                current = line

        # Update in_pre state
        if line_opens_pre:
            in_pre = True
            # Capture the exact pre tag (e.g., <pre><code class="...">)
            m = re.search(r"<pre[^>]*>(?:<code[^>]*>)?", line)
            if m:
                pre_tag = m.group(0)
        if line_closes_pre:
            in_pre = False
            pre_tag = "<pre>"

    if current.strip():
        if in_pre and not current.endswith("</pre>"):
            current += "\n</pre>"
        chunks.append(current)

    return chunks


def format_tool_status(tool_name: str, tool_args: dict, state: str = "running") -> str:
    """Format an informative status message when a tool is executed."""
    icons = {
        "run_command": "⚡",
        "view_file": "📄",
        "write_to_file": "📝",
        "replace_file_content": "✏️",
        "grep_search": "🔍",
        "find_by_name": "🔎",
        "list_dir": "📁",
        "search_web": "🌐",
        "read_url_content": "🌍",
        "generate_image": "🎨",
        "ask_question": "❓",
    }
    icon = icons.get(tool_name, "⚙️")
    
    arg_summary = ""
    if tool_name == "run_command" and "CommandLine" in tool_args:
        arg_summary = f": <code>{escape_html(str(tool_args['CommandLine'])[:80])}</code>"
    elif tool_name in ("view_file", "write_to_file", "replace_file_content") and "TargetFile" in tool_args:
        arg_summary = f": <code>{escape_html(str(tool_args['TargetFile'])[:60])}</code>"
    elif tool_name in ("view_file", "write_to_file") and "AbsolutePath" in tool_args:
        arg_summary = f": <code>{escape_html(str(tool_args['AbsolutePath'])[:60])}</code>"
    elif tool_name == "search_web" and "query" in tool_args:
        arg_summary = f": <i>{escape_html(str(tool_args['query'])[:60])}</i>"
    
    if state == "running":
        return f"{icon} <b>Çalıştırılıyor:</b> <code>{escape_html(tool_name)}</code>{arg_summary}..."
    else:
        return f"✅ <b>Tamamlandı:</b> <code>{escape_html(tool_name)}</code>{arg_summary}"


def format_stats_footer(duration: float, usage: Optional[dict] = None) -> str:
    """Format footer with latency and token usage statistics."""
    parts = [f"⏱ {duration:.1f}s"]
    if usage:
        total = usage.get("total_tokens", 0)
        thinking = usage.get("thinking_tokens", 0)
        if total:
            parts.append(f"📊 {total:,} tokens")
        if thinking:
            parts.append(f"🧠 {thinking:,} reasoning")
    return " | ".join(parts)
