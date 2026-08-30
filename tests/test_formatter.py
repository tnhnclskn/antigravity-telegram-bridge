import pytest
from formatter import (
    escape_html,
    markdown_to_telegram_html,
    split_text_chunks,
    format_tool_status,
    extract_tool_details,
    format_cumulative_status_telegram,
    format_live_progress_panel_telegram,
    format_tool_diff_telegram,
    format_execution_stages_telegram,
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


def test_extract_tool_details_all_tools():
    # 1. view_file
    assert extract_tool_details("view_file", {"TargetFile": "/root/app.py", "StartLine": 1, "EndLine": 50}) == "/root/app.py (L1-50)"
    assert extract_tool_details("view_file", {"AbsolutePath": "/root/main.py"}) == "/root/main.py"

    # 2. write_to_file
    assert extract_tool_details("write_to_file", {"TargetFile": "/root/new.py"}) == "/root/new.py"

    # 3. replace_file_content
    assert extract_tool_details("replace_file_content", {"TargetFile": "src/utils.py", "StartLine": 10, "EndLine": 20}) == "src/utils.py (L10-20)"

    # 4. run_command
    assert extract_tool_details("run_command", {"CommandLine": "pytest -v", "Cwd": "/root/app"}) == "pytest -v"

    # 5. grep_search
    assert extract_tool_details("grep_search", {"Query": "def handle", "SearchPath": "/root/src"}) == "'def handle' in /root/src"
    assert extract_tool_details("grep_search", {"Query": "TODO"}) == "'TODO'"

    # 6. find_by_name
    assert extract_tool_details("find_by_name", {"Pattern": "*.py", "SearchDirectory": "/root"}) == "*.py in /root"

    # 7. list_dir
    assert extract_tool_details("list_dir", {"DirectoryPath": "/root/Projects"}) == "/root/Projects"

    # 8. invoke_subagent
    assert extract_tool_details("invoke_subagent", {"Role": "Codebase Researcher", "TypeName": "research"}) == "Codebase Researcher (research)"
    assert extract_tool_details("invoke_subagent", {"Prompt": "Search docs for API"}) == "Search docs for API"

    # 9. send_message
    assert extract_tool_details("send_message", {"RecipientName": "parent", "Recipient": "agent-123"}) == "parent (agent-123)"

    # 10. manage_subagents / manage_task
    assert extract_tool_details("manage_task", {"Action": "kill", "TaskId": "task-99"}) == "kill (task-99)"
    assert extract_tool_details("manage_subagents", {"Action": "list"}) == "list"

    # 11. search_web
    assert extract_tool_details("search_web", {"query": "python asyncio tutorial"}) == "python asyncio tutorial"

    # 12. read_url_content
    assert extract_tool_details("read_url_content", {"Url": "https://docs.python.org/3/"}) == "https://docs.python.org/3/"

    # 13. schedule
    assert extract_tool_details("schedule", {"Prompt": "Health check", "DurationSeconds": 300}) == "Health check (300s)"
    assert extract_tool_details("schedule", {"Prompt": "Cron job", "CronExpression": "*/5 * * * *"}) == "Cron job (*/5 * * * *)"

    # 14. generate_image
    assert extract_tool_details("generate_image", {"ImageName": "dashboard_ui"}) == "dashboard_ui"

    # 15. notebook_edit
    assert extract_tool_details("notebook_edit", {"NotebookPath": "explore.ipynb", "Action": "list"}) == "explore.ipynb (list)"

    # 16. Fallback parameters / toolAction
    assert extract_tool_details("custom_tool", {"toolAction": "Analyzing database structure"}) == "Analyzing database structure"
    assert extract_tool_details("custom_tool", {"toolSummary": "Database analysis"}) == "Database analysis"


def test_format_tool_status():
    # Running state
    status_running = format_tool_status("run_command", {"CommandLine": "ls -la /root"}, state="running")
    assert "⚡" in status_running
    assert "run_command" in status_running
    assert "ls -la /root" in status_running
    assert "yürütülüyor" in status_running or "çalışıyor" in status_running

    # Completed state
    status_comp = format_tool_status("view_file", {"TargetFile": "app.py"}, state="completed", duration=0.42)
    assert "✅" in status_comp
    assert "📄" in status_comp
    assert "view_file" in status_comp
    assert "app.py" in status_comp
    assert "0.4s" in status_comp


def test_format_stats_footer():
    footer = format_stats_footer(1.45, {"total_tokens": 1250, "thinking_tokens": 320})
    assert "1.4s" in footer or "1.5s" in footer
    assert "1,250 tokens" in footer
    assert "320 reasoning" in footer


def test_format_tool_diff_telegram():
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

    tools = [
        {"tool_name": "replace_file_content", "tool_info": {"TargetFile": "test.py", "TargetContent": "a", "ReplacementContent": "b"}},
        {"tool_name": "run_command", "tool_info": {"CommandLine": "pytest"}}
    ]
    stages_res = format_execution_stages_telegram(tools)
    assert "<b>🛠️ İşlem Aşamaları & Kod Farkları:</b>" in stages_res
    assert "test.py" in stages_res
    assert "pytest" in stages_res


def test_format_cumulative_status_telegram_empty():
    assert format_cumulative_status_telegram([]) == "🧠 <i>Düşünülüyor ve hazırlanıyor...</i>"


def test_format_cumulative_status_telegram_active_and_completed():
    tools = [
        {"tool_name": "view_file", "tool_info": {"TargetFile": "app.py"}, "state": "completed", "duration_seconds": 0.3},
        {"tool_name": "run_command", "tool_info": {"CommandLine": "pytest"}, "state": "running", "duration_seconds": None}
    ]
    res = format_cumulative_status_telegram(tools)

    # Active tool section check
    assert "🔄 <b>Aktif İşlem:</b>" in res
    assert "run_command" in res
    assert "pytest" in res
    assert "yürütülüyor" in res or "çalışıyor" in res

    # Completed tool section check
    assert "📋 <b>Tamamlanan Adımlar (1):</b>" in res or "⚙️ <b>İşlem Adımları:</b>" in res
    assert "view_file" in res
    assert "app.py" in res
    assert "0.3s" in res


def test_format_cumulative_status_telegram_with_active_subagents():
    # Via active_subagents parameter
    active_subs = [
        {"name": "Codebase Researcher", "type": "research", "status": "running"}
    ]
    tools = [
        {"tool_name": "grep_search", "tool_info": {"Query": "class AgyClient"}, "state": "running"}
    ]
    res = format_cumulative_status_telegram(tools, active_subagents=active_subs)

    assert "🤖 <b>Aktif Ajanlar:</b>" in res
    assert "Codebase Researcher" in res
    assert "research" in res
    assert "🔄 <b>Aktif İşlem:</b>" in res
    assert "grep_search" in res


def test_format_cumulative_status_telegram_with_subagent_tool():
    # Via invoke_subagent tool
    tools = [
        {
            "tool_name": "invoke_subagent",
            "tool_info": {"Role": "Test Runner", "TypeName": "testing", "Prompt": "Run all tests"},
            "state": "running"
        },
        {
            "tool_name": "view_file",
            "tool_info": {"TargetFile": "tests/test_app.py"},
            "state": "completed",
            "duration_seconds": 0.5
        }
    ]
    res = format_cumulative_status_telegram(tools)

    assert "🤖 <b>Aktif Ajanlar:</b>" in res
    assert "Test Runner" in res
    assert "testing" in res
    assert "📋 <b>Tamamlanan Adımlar" in res or "⚙️ <b>İşlem Adımları:</b>" in res
    assert "tests/test_app.py" in res


def test_format_cumulative_status_telegram_html_safety_and_cutoff():
    # Test HTML escaping
    malicious_tools = [
        {
            "tool_name": "run_command",
            "tool_info": {"CommandLine": "cat <secret.txt> && echo 'test'"},
            "state": "running"
        }
    ]
    res = format_cumulative_status_telegram(malicious_tools)
    assert "<secret.txt>" not in res
    assert "&lt;secret.txt&gt;" in res

    # Test 3500 char cutoff
    long_tools = [
        {
            "tool_name": "run_command",
            "tool_info": {"CommandLine": f"echo 'Very long step number {i} with lots of filler text to check length limitation'"},
            "state": "completed",
            "duration_seconds": 0.1
        }
        for i in range(50)
    ]
    long_res = format_cumulative_status_telegram(long_tools)
    assert len(long_res) <= 3500
    assert "..." in long_res


def test_format_live_progress_panel_telegram_alias():
    tools = [{"tool_name": "list_dir", "tool_info": {"DirectoryPath": "/root"}, "state": "running"}]
    res = format_live_progress_panel_telegram(tools)
    assert "list_dir" in res
    assert "/root" in res


def test_is_running_and_completed_state_helpers():
    from formatter import is_running_state, is_completed_state
    assert is_running_state("running") is True
    assert is_running_state("ACTIVE") is True
    assert is_running_state("active") is True
    assert is_running_state("start") is True
    assert is_running_state("started") is True
    assert is_running_state(None) is True
    assert is_running_state("done") is False
    assert is_running_state("completed") is False

    assert is_completed_state("completed") is True
    assert is_completed_state("DONE") is True
    assert is_completed_state("done") is True
    assert is_completed_state("finished") is True
    assert is_completed_state("success") is True
    assert is_completed_state("running") is False
    assert is_completed_state("ACTIVE") is False
    assert is_completed_state(None) is False


def test_format_cumulative_status_telegram_with_active_and_done_states():
    # Tools with raw ACTIVE and DONE states as emitted by agy CLI
    tools = [
        {"tool_name": "find_by_name", "tool_info": {"Pattern": "*.py", "SearchDirectory": "/root"}, "state": "DONE", "duration_seconds": 0.05},
        {"tool_name": "grep_search", "tool_info": {"Query": "class AgyClient", "SearchPath": "/root"}, "state": "ACTIVE"}
    ]
    res = format_cumulative_status_telegram(tools)
    assert "🔄 <b>Aktif İşlem:</b>" in res
    assert "grep_search" in res
    assert "class AgyClient" in res
    assert "📋 <b>Tamamlanan Adımlar (1):</b>" in res
    assert "find_by_name" in res
    assert "*.py in /root" in res
    assert "0.1s" in res or "0.0s" in res

