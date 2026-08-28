import pytest
from formatter import (
    escape_html,
    markdown_to_telegram_html,
    split_text_chunks,
    format_tool_status,
    format_stats_footer
)


def test_escape_html():
    assert escape_html("Hello <world> & friends") == "Hello &lt;world&gt; &amp; friends"


def test_markdown_to_telegram_html_basic():
    md = "# Hello Title\nThis is **bold** and *italic* and `inline_code`."
    res = markdown_to_telegram_html(md)
    assert "<b>Hello Title</b>" in res
    assert "<b>bold</b>" in res
    assert "<i>italic</i>" in res
    assert "<code>inline_code</code>" in res


def test_markdown_to_telegram_html_code_block():
    md = "Code:\n```python\ndef foo():\n    return 42\n```"
    res = markdown_to_telegram_html(md)
    assert '<pre><code class="language-python">def foo():\n    return 42</code></pre>' in res


def test_markdown_to_telegram_html_nested_tags():
    md = 'Test `<div class="box">` inside code block:\n```html\n<div>Test & Demo</div>\n```'
    res = markdown_to_telegram_html(md)
    assert '<code>&lt;div class="box"&gt;</code>' in res
    assert "&lt;div&gt;Test &amp; Demo&lt;/div&gt;" in res


def test_split_text_chunks_small():
    text = "Short text"
    chunks = split_text_chunks(text, max_chars=100)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_chunks_long():
    text = "\n".join([f"Line {i}: Some detailed content for testing paragraph splitting" for i in range(100)])
    chunks = split_text_chunks(text, max_chars=300)
    assert len(chunks) > 1
    for ch in chunks:
        assert len(ch) <= 350


def test_split_text_chunks_preserves_pre_tags():
    code_lines = "\n".join([f"x_{i} = {i} * 2" for i in range(50)])
    text = f"<pre><code class=\"language-python\">\n{code_lines}\n</code></pre>"
    chunks = split_text_chunks(text, max_chars=200)
    assert len(chunks) > 1
    # Check that chunks close opened pre tags
    for ch in chunks:
        if "<pre" in ch:
            assert "</pre>" in ch


def test_format_tool_status():
    status = format_tool_status("run_command", {"CommandLine": "ls -la /root"}, state="running")
    assert "⚡" in status
    assert "run_command" in status
    assert "ls -la /root" in status


def test_format_stats_footer():
    footer = format_stats_footer(1.45, {"total_tokens": 1250, "thinking_tokens": 320})
    assert "1.4s" in footer or "1.5s" in footer
    assert "1,250 tokens" in footer
    assert "320 reasoning" in footer


def test_format_tool_diff_telegram():
    from formatter import format_tool_diff_telegram, format_execution_stages_telegram

    # Test replace_file_content diff
    diff_res = format_tool_diff_telegram("replace_file_content", {
        "TargetFile": "/root/app.py",
        "Instruction": "Update port",
        "TargetContent": "port = 8080",
        "ReplacementContent": "port = 38291",
        "StartLine": 10,
        "EndLine": 12
    })
    assert "✏️ <b>Fark (Diff):</b>" in diff_res
    assert "/root/app.py" in diff_res
    assert "Update port" in diff_res
    assert "- port = 8080" in diff_res
    assert "+ port = 38291" in diff_res
    assert 'language-diff' in diff_res

    # Test stages summary
    tools = [
        {"tool_name": "replace_file_content", "tool_info": {"TargetFile": "test.py", "TargetContent": "a", "ReplacementContent": "b"}},
        {"tool_name": "run_command", "tool_info": {"CommandLine": "pytest"}}
    ]
    stages_res = format_execution_stages_telegram(tools)
    assert "<b>🛠️ İşlem Aşamaları & Kod Farkları:</b>" in stages_res
    assert "test.py" in stages_res
    assert "pytest" in stages_res
