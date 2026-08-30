"""
Telegram message formatting and chunking utilities.
Converts Markdown to clean, safe Telegram HTML and splits long responses.
"""

import re
import html
from typing import List, Optional, Union, Dict, Any


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


TOOL_ICONS = {
    "run_command": "⚡",
    "view_file": "📄",
    "write_to_file": "📝",
    "replace_file_content": "✏️",
    "grep_search": "🔍",
    "find_by_name": "🔎",
    "list_dir": "📁",
    "invoke_subagent": "🤖",
    "send_message": "💬",
    "manage_subagents": "👥",
    "manage_task": "⚙️",
    "search_web": "🌐",
    "read_url_content": "🌍",
    "schedule": "⏰",
    "generate_image": "🎨",
    "notebook_edit": "📓",
    "ask_question": "❓",
}


def extract_tool_details(tool_name: str, tool_info: dict) -> str:
    """
    Extract a concise, human-readable summary/target string from tool arguments.
    Returns plain unescaped text (escaping is handled when inserting into HTML).
    """
    if not isinstance(tool_info, dict):
        return ""

    args = tool_info.get("parameters", tool_info) if isinstance(tool_info.get("parameters"), dict) else tool_info

    if tool_name == "view_file":
        path = args.get("TargetFile") or args.get("AbsolutePath") or args.get("FilePath") or ""
        start = args.get("StartLine")
        end = args.get("EndLine")
        if path and start is not None and end is not None:
            return f"{path} (L{start}-{end})"
        return str(path)

    elif tool_name == "write_to_file":
        return str(args.get("TargetFile") or args.get("AbsolutePath") or "")

    elif tool_name == "replace_file_content":
        path = args.get("TargetFile") or args.get("AbsolutePath") or ""
        start = args.get("StartLine")
        end = args.get("EndLine")
        if path and start is not None and end is not None:
            return f"{path} (L{start}-{end})"
        return str(path)

    elif tool_name == "run_command":
        cmd = args.get("CommandLine") or ""
        return str(cmd)

    elif tool_name == "grep_search":
        q = args.get("Query") or ""
        path = args.get("SearchPath") or ""
        if q and path:
            return f"'{q}' in {path}"
        elif q:
            return f"'{q}'"
        return str(path)

    elif tool_name == "find_by_name":
        pat = args.get("Pattern") or ""
        sdir = args.get("SearchDirectory") or ""
        if pat and sdir:
            return f"{pat} in {sdir}"
        return str(pat or sdir)

    elif tool_name == "list_dir":
        return str(args.get("DirectoryPath") or "")

    elif tool_name == "invoke_subagent":
        role = args.get("Role") or ""
        type_name = args.get("TypeName") or ""
        prompt = args.get("Prompt") or ""
        if role and type_name:
            return f"{role} ({type_name})"
        elif role:
            return str(role)
        elif type_name:
            return str(type_name)
        elif prompt:
            return str(prompt[:80])
        return ""

    elif tool_name == "send_message":
        r_name = args.get("RecipientName") or ""
        r_id = args.get("Recipient") or ""
        msg = args.get("Message") or ""
        if r_name and r_id:
            return f"{r_name} ({r_id})"
        elif r_name:
            return str(r_name)
        elif r_id:
            return str(r_id)
        elif msg:
            return str(msg[:60])
        return ""

    elif tool_name in ("manage_subagents", "manage_task"):
        action = args.get("Action") or ""
        task_id = args.get("TaskId") or ""
        if action and task_id:
            return f"{action} ({task_id})"
        return str(action or task_id)

    elif tool_name == "search_web":
        return str(args.get("query") or "")

    elif tool_name == "read_url_content":
        return str(args.get("Url") or "")

    elif tool_name == "schedule":
        prompt = args.get("Prompt") or ""
        dur = args.get("DurationSeconds")
        cron = args.get("CronExpression")
        if dur is not None:
            return f"{prompt} ({dur}s)" if prompt else f"{dur}s"
        elif cron:
            return f"{prompt} ({cron})" if prompt else f"{cron}"
        return str(prompt)

    elif tool_name == "generate_image":
        return str(args.get("ImageName") or args.get("Prompt") or "")

    elif tool_name == "notebook_edit":
        nb = args.get("NotebookPath") or ""
        action = args.get("Action") or ""
        if nb and action:
            return f"{nb} ({action})"
        return str(nb or action)

    # Generic fallback
    if "toolAction" in args and args["toolAction"]:
        return str(args["toolAction"])
    if "toolSummary" in args and args["toolSummary"]:
        return str(args["toolSummary"])
    if "Description" in args and args["Description"]:
        return str(args["Description"])
    if "Instruction" in args and args["Instruction"]:
        return str(args["Instruction"])

    for k, v in args.items():
        if isinstance(v, (str, int, float)) and v:
            return str(v)

    return ""


def is_running_state(state: Optional[str]) -> bool:
    """Check if state represents an ongoing/active tool execution."""
    if not state:
        return True
    s = str(state).strip().lower()
    return s in ("running", "active", "start", "started", "in_progress")


def is_completed_state(state: Optional[str]) -> bool:
    """Check if state represents a finished tool execution."""
    if not state:
        return False
    s = str(state).strip().lower()
    return s in ("completed", "done", "complete", "finished", "success")


def format_tool_status(tool_name: str, tool_args: dict, state: str = "running", duration: Optional[float] = None) -> str:
    """Format an informative status message when a tool is executed."""
    icon = TOOL_ICONS.get(tool_name, "⚙️")
    details = extract_tool_details(tool_name, tool_args)

    details_html = ""
    if details:
        d_str = details[:80] + ("..." if len(details) > 80 else "")
        details_html = f": <code>{escape_html(d_str)}</code>"

    if is_running_state(state):
        return f"{icon} <code>{escape_html(tool_name)}</code>{details_html} ⏳ <i>(yürütülüyor...)</i>"
    else:
        dur_str = f" [{duration:.1f}s]" if duration is not None else ""
        return f"✅ {icon} <code>{escape_html(tool_name)}</code>{details_html}{dur_str}"


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


def format_active_subagents_indicator(active_subagents: List[str]) -> str:
    """
    Format active subagents list into dynamic bottom indicator:
    ⏳ <i>Aktif Ajanlar: Araştırmacı, Kod Geliştirici...</i>
    Returns empty string if list is empty.
    """
    if not active_subagents:
        return ""
    valid_names = [escape_html(name.strip()) for name in active_subagents if isinstance(name, str) and name.strip()]
    if not valid_names:
        return ""
    return f"⏳ <i>Aktif Ajanlar: {', '.join(valid_names)}</i>"


def format_cumulative_status_telegram(
    tools: List[dict],
    active_subagents: Optional[List[Union[dict, str]]] = None,
    elapsed_seconds: Optional[float] = None,
    current_text: Optional[str] = None
) -> str:
    """
    Format all executed and currently running tool stages along with live streaming LLM text into a cumulative progress message.
    Displays:
    - 🔄 Aktif İşlem (Currently running tool, if any)
    - 📋 Tamamlanan Adımlar (Completed steps, if any)
    - Live streamed LLM response accumulated so far (if any)
    - ⏳ <i>Aktif Ajanlar: Araştırmacı, Kod Geliştirici...</i> (Dynamic active subagent list at bottom, if any active subagents)
    """
    subagent_names: List[str] = []

    def _add_name(name: Optional[str]):
        if name:
            s = str(name).strip()
            if s and s not in subagent_names:
                subagent_names.append(s)

    if active_subagents:
        for sa in active_subagents:
            if isinstance(sa, str):
                _add_name(sa)
            elif isinstance(sa, dict):
                st = sa.get("status") or sa.get("state")
                if st is None or is_running_state(st):
                    name = (
                        sa.get("name")
                        or sa.get("role")
                        or sa.get("Role")
                        or sa.get("TypeName")
                        or sa.get("type")
                        or "Subagent"
                    )
                    _add_name(name)

    running_subagent_tools = []
    normal_tools = []
    for t in (tools or []):
        t_name = t.get("tool_name", "")
        t_state = t.get("state", "running")
        if t_name in ("invoke_subagent",) and is_running_state(t_state):
            running_subagent_tools.append(t)
            t_info = t.get("tool_info", {})
            args = t_info.get("parameters", t_info) if isinstance(t_info, dict) else {}
            role = (
                args.get("Role")
                or args.get("role")
                or args.get("name")
                or args.get("Name")
                or args.get("TypeName")
                or args.get("type")
                or "Subagent"
            )
            _add_name(role)
        else:
            normal_tools.append(t)

    sections = []

    # Section 1: Active Tools (Running)
    running_tools = [t for t in normal_tools if is_running_state(t.get("state"))]
    if running_tools:
        run_lines = []
        for t in running_tools:
            t_name = t.get("tool_name", "")
            t_info = t.get("tool_info", {})
            status_line = format_tool_status(t_name, t_info, state="running")
            run_lines.append(f"• {status_line}")
        sections.append("🔄 <b>Aktif İşlem:</b>\n" + "\n".join(run_lines))

    # Section 2: Completed Tools
    completed_tools = [t for t in (tools or []) if is_completed_state(t.get("state"))]
    if completed_tools:
        comp_lines = []
        for t in completed_tools:
            t_name = t.get("tool_name", "")
            t_info = t.get("tool_info", {})
            duration = t.get("duration_seconds")
            status_line = format_tool_status(t_name, t_info, state="completed", duration=duration)
            comp_lines.append(f"• {status_line}")

        header = f"📋 <b>Tamamlanan Adımlar ({len(completed_tools)}):</b>"
        if len(comp_lines) > 10:
            truncated_comp = comp_lines[:3] + [f"• ... <i>({len(comp_lines) - 8} adım daha)</i>"] + comp_lines[-5:]
            sections.append(f"{header}\n" + "\n".join(truncated_comp))
        else:
            sections.append(f"{header}\n" + "\n".join(comp_lines))

    has_tools_or_subs = bool(sections)
    tools_part = "\n\n".join(sections) if sections else ""

    text_part = ""
    if current_text and current_text.strip():
        text_part = markdown_to_telegram_html(current_text.strip())
        if len(text_part) > 2500:
            text_part = text_part[:2450] + "\n..."

    active_subagents_indicator = format_active_subagents_indicator(subagent_names)

    if not has_tools_or_subs and not text_part:
        base_text = "🧠 <i>Düşünülüyor ve hazırlanıyor...</i>"
        if active_subagents_indicator:
            return f"{base_text}\n\n{active_subagents_indicator}"
        return base_text

    if has_tools_or_subs and text_part:
        full_text = f"{tools_part}\n\n{text_part}"
    elif has_tools_or_subs:
        full_text = tools_part
    else:
        full_text = text_part

    # Enforce safe cutoff (< 3500 chars)
    if len(full_text) > 3500:
        lines = full_text.splitlines()
        truncated = lines[:5] + ["• ..."] + lines[-10:]
        full_text = "\n".join(truncated)
        if len(full_text) > 3500:
            full_text = full_text[:3450] + "\n..."

    if active_subagents_indicator:
        full_text += f"\n\n{active_subagents_indicator}"

    return full_text


format_live_progress_panel_telegram = format_cumulative_status_telegram


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
