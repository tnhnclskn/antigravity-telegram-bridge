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


def format_tool_status(tool_name: str, tool_args: dict, state: str = "running", duration: Optional[float] = None) -> str:
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
        "invoke_subagent": "🤖",
    }
    icon = icons.get(tool_name, "⚙️")

    # Handle parameters if nested or flat
    args = tool_args.get("parameters", tool_args) if isinstance(tool_args, dict) else {}

    arg_summary = ""
    if tool_name == "run_command" and "CommandLine" in args:
        arg_summary = f": <code>{escape_html(str(args['CommandLine'])[:80])}</code>"
    elif tool_name in ("view_file", "write_to_file", "replace_file_content") and "TargetFile" in args:
        arg_summary = f": <code>{escape_html(str(args['TargetFile'])[:60])}</code>"
    elif tool_name in ("view_file", "write_to_file") and "AbsolutePath" in args:
        arg_summary = f": <code>{escape_html(str(args['AbsolutePath'])[:60])}</code>"
    elif tool_name == "search_web" and "query" in args:
        arg_summary = f": <i>{escape_html(str(args['query'])[:60])}</i>"

    if state == "running":
        return f"{icon} <b>Çalıştırılıyor:</b> <code>{escape_html(tool_name)}</code>{arg_summary}..."
    else:
        dur_str = f" ({duration:.1f}s)" if duration else ""
        return f"✅ <b>Tamamlandı:</b> <code>{escape_html(tool_name)}</code>{arg_summary}{dur_str}"


def format_tool_diff_telegram(tool_name: str, tool_info: dict) -> str:
    """Format file diff or tool execution stage for Telegram HTML."""
    info = tool_info.get("parameters", tool_info) if isinstance(tool_info, dict) else {}

    if tool_name == "replace_file_content":
        file = info.get("TargetFile", "Dosya")
        instruction = info.get("Instruction") or info.get("Description") or ""
        target = str(info.get("TargetContent", "")).strip()
        replacement = str(info.get("ReplacementContent", "")).strip()
        start = info.get("StartLine", "")
        end = info.get("EndLine", "")
        lines_str = f" (L{start}-{end})" if start and end else ""

        diff_lines = []
        if target:
            for l in target.splitlines():
                diff_lines.append(f"- {l}")
        if replacement:
            for l in replacement.splitlines():
                diff_lines.append(f"+ {l}")
        diff_block = "\n".join(diff_lines)
        if len(diff_block) > 600:
            diff_block = diff_block[:600] + "\n..."

        header = f"✏️ <b>Fark (Diff):</b> <code>{escape_html(file)}{lines_str}</code>"
        inst_html = f"\n<i>💡 {escape_html(instruction)}</i>" if instruction else ""
        code_html = f'\n<pre><code class="language-diff">{escape_html(diff_block)}</code></pre>' if diff_block else ""
        return f"{header}{inst_html}{code_html}"

    elif tool_name == "write_to_file":
        file = info.get("TargetFile", "Dosya")
        desc = info.get("Description", "")
        code = str(info.get("CodeContent", "")).strip()
        if len(code) > 300:
            code = code[:300] + "\n..."
        header = f"📝 <b>Yeni Dosya:</b> <code>{escape_html(file)}</code>"
        desc_html = f"\n<i>{escape_html(desc)}</i>" if desc else ""
        code_html = f"\n<pre>{escape_html(code)}</pre>" if code else ""
        return f"{header}{desc_html}{code_html}"

    elif tool_name == "run_command":
        cmd = info.get("CommandLine", "")
        cwd = info.get("Cwd", "")
        header = f"⚡ <b>Komut:</b> <code>{escape_html(cmd)}</code>"
        cwd_html = f" <i>(dizin: {escape_html(cwd)})</i>" if cwd else ""
        return f"{header}{cwd_html}"

    elif tool_name in ("view_file", "grep_search", "find_by_name", "list_dir"):
        target = info.get("TargetFile") or info.get("AbsolutePath") or info.get("Query") or info.get("SearchPath") or ""
        return f"🔍 <b>İnceleme ({escape_html(tool_name)}):</b> <code>{escape_html(str(target))}</code>"

    return f"⚙️ <b>İşlem:</b> <code>{escape_html(tool_name)}</code>"


def format_execution_stages_telegram(tools: List[dict]) -> str:
    """Format a list of executed tool stages into a Telegram HTML section."""
    if not tools:
        return ""
    lines = ["<b>🛠️ İşlem Aşamaları & Kod Farkları:</b>"]
    for t in tools:
        t_name = t.get("tool_name", "")
        t_info = t.get("tool_info", {})
        formatted_stage = format_tool_diff_telegram(t_name, t_info)
        lines.append(formatted_stage)
    return "\n\n".join(lines)


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
