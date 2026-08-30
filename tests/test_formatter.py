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
    format_stats_footer,
    format_active_subagents_indicator,
    render_progress_bar,
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
    long_text = "\n".join([f"Line number {i} is here to fill space." for i in range(150)])
    chunks = split_text_chunks(long_text, max_chars=1000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1000


def test_split_text_chunks_preserves_pre_tags():
    code_text = "Before\n<pre><code>\n" + "\n".join([f"def func_{i}(): pass" for i in range(100)]) + "\n</code></pre>\nAfter"
    chunks = split_text_chunks(code_text, max_chars=500)
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert "</pre>" in chunk


def test_format_tool_status_running():
    res = format_tool_status("run_command", {"CommandLine": "ls -la"}, state="running")
    assert "⚡" in res
    assert "<code>run_command</code>" in res
    assert "<code>ls -la</code>" in res
    assert "yürütülüyor" in res or "çalışıyor" in res


def test_format_tool_status_completed():
    res = format_tool_status("view_file", {"TargetFile": "app.py"}, state="completed", duration=1.23)
    assert "✅" in res
    assert "📄" in res
    assert "<code>view_file</code>" in res
    assert "<code>app.py</code>" in res
    assert "1.2s" in res


def test_extract_tool_details():
    # 1. view_file
    assert extract_tool_details("view_file", {"TargetFile": "main.py", "StartLine": 1, "EndLine": 20}) == "main.py (L1-20)"
    assert extract_tool_details("view_file", {"TargetFile": "main.py"}) == "main.py"

    # 2. write_to_file
    assert extract_tool_details("write_to_file", {"TargetFile": "test.txt"}) == "test.txt"

    # 3. replace_file_content
    assert extract_tool_details("replace_file_content", {"TargetFile": "config.py", "StartLine": 10, "EndLine": 15}) == "config.py (L10-15)"

    # 4. run_command
    assert extract_tool_details("run_command", {"CommandLine": "git status"}) == "git status"

    # 5. grep_search
    assert extract_tool_details("grep_search", {"Query": "def test", "SearchPath": "src/"}) == "'def test' in src/"
    assert extract_tool_details("grep_search", {"Query": "def test"}) == "'def test'"

    # 6. find_by_name
    assert extract_tool_details("find_by_name", {"Pattern": "*.py", "SearchDirectory": "app/"}) == "*.py in app/"

    # 7. list_dir
    assert extract_tool_details("list_dir", {"DirectoryPath": "/tmp"}) == "/tmp"

    # 8. invoke_subagent
    assert extract_tool_details("invoke_subagent", {"Role": "Codebase Researcher", "TypeName": "research"}) == "Codebase Researcher (research)"
    assert extract_tool_details("invoke_subagent", {"Prompt": "Search docs for API"}) == "Search docs for API"

    # 9. send_message
    assert extract_tool_details("send_message", {"RecipientName": "parent", "Recipient": "123"}) == "parent (123)"

    # 10. manage_subagents / manage_task
    assert extract_tool_details("manage_subagents", {"Action": "list"}) == "list"
    assert extract_tool_details("manage_task", {"Action": "kill", "TaskId": "task_1"}) == "kill (task_1)"

    # 11. search_web
    assert extract_tool_details("search_web", {"query": "python asyncio"}) == "python asyncio"

    # 12. read_url_content
    assert extract_tool_details("read_url_content", {"Url": "https://example.com"}) == "https://example.com"

    # 13. schedule
    assert extract_tool_details("schedule", {"Prompt": "Remind me", "DurationSeconds": 60}) == "Remind me (60s)"
    assert extract_tool_details("schedule", {"CronExpression": "*/5 * * * *"}) == "*/5 * * * *"

    # 14. generate_image
    assert extract_tool_details("generate_image", {"ImageName": "cat_photo"}) == "cat_photo"

    # 15. notebook_edit
    assert extract_tool_details("notebook_edit", {"NotebookPath": "analysis.ipynb", "Action": "add"}) == "analysis.ipynb (add)"

    # 16. fallback to toolAction/toolSummary
    assert extract_tool_details("custom_tool", {"toolAction": "Doing something"}) == "Doing something"
    assert extract_tool_details("custom_tool", {"toolSummary": "Summary info"}) == "Summary info"


def test_format_tool_diff_telegram():
    info = {
        "TargetFile": "server.py",
        "Instruction": "Update port",
        "TargetContent": "port = 8080",
        "ReplacementContent": "port = 38291",
        "StartLine": 10,
        "EndLine": 11
    }
    diff_res = format_tool_diff_telegram("replace_file_content", info)
    assert "✏️ <b>Fark (Diff):</b>" in diff_res
    assert "server.py (L10-11)" in diff_res
    assert "Update port" in diff_res
    assert "- port = 8080" in diff_res
    assert "+ port = 38291" in diff_res
    assert 'language-diff' in diff_res


def test_format_execution_stages_telegram():
    tools = [
        {"tool_name": "replace_file_content", "tool_info": {"TargetFile": "test.py", "TargetContent": "a", "ReplacementContent": "b"}},
        {"tool_name": "run_command", "tool_info": {"CommandLine": "pytest"}}
    ]
    stages_res = format_execution_stages_telegram(tools)
    assert "<b>🛠️ İşlem Aşamaları & Kod Farkları:</b>" in stages_res
    assert "test.py" in stages_res
    assert "pytest" in stages_res


def test_format_active_subagents_indicator():
    assert format_active_subagents_indicator([]) == ""
    assert format_active_subagents_indicator(["Araştırmacı"]) == "⏳ <i>Aktif Ajanlar: Araştırmacı</i>"
    assert format_active_subagents_indicator(["Araştırmacı", "Kod Geliştirici"]) == "⏳ <i>Aktif Ajanlar: Araştırmacı, Kod Geliştirici</i>"
    # HTML safety
    assert format_active_subagents_indicator(["<Agent 1>", "Tester & Reviewer"]) == "⏳ <i>Aktif Ajanlar: &lt;Agent 1&gt;, Tester &amp; Reviewer</i>"
    # Empty strings and whitespace
    assert format_active_subagents_indicator(["", "  ", "Agent"]) == "⏳ <i>Aktif Ajanlar: Agent</i>"


def test_format_cumulative_status_telegram_empty():
    assert format_cumulative_status_telegram([]) == "🧠 <i>Düşünülüyor ve hazırlanıyor...</i>"


def test_format_cumulative_status_telegram_empty_with_subagents():
    res = format_cumulative_status_telegram([], active_subagents=[{"name": "Araştırmacı"}])
    assert res == "🧠 <i>Düşünülüyor ve hazırlanıyor...</i>\n\n⏳ <i>Aktif Ajanlar: Araştırmacı</i>"


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

    # No static loading indicator and no active agents when none active
    assert "İşlem devam ediyor" not in res
    assert "Aktif Ajanlar" not in res


def test_format_cumulative_status_telegram_with_active_subagents():
    # Via active_subagents parameter
    active_subs = [
        {"name": "Araştırmacı", "type": "research", "status": "running"},
        {"name": "Kod Geliştirici", "type": "coder", "status": "running"}
    ]
    tools = [
        {"tool_name": "grep_search", "tool_info": {"Query": "class AgyClient"}, "state": "running"}
    ]
    res = format_cumulative_status_telegram(tools, active_subagents=active_subs)

    assert "🔄 <b>Aktif İşlem:</b>" in res
    assert "grep_search" in res
    assert res.endswith("⏳ <i>Aktif Ajanlar: Araştırmacı, Kod Geliştirici</i>")
    assert "İşlem devam ediyor" not in res


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

    assert "📋 <b>Tamamlanan Adımlar" in res or "⚙️ <b>İşlem Adımları:</b>" in res
    assert "tests/test_app.py" in res
    assert res.endswith("⏳ <i>Aktif Ajanlar: Test Runner</i>")
    assert "İşlem devam ediyor" not in res


def test_format_cumulative_status_telegram_completed_subagent_not_active():
    # When invoke_subagent completes, it should be in completed steps, not at bottom
    tools = [
        {
            "tool_name": "invoke_subagent",
            "tool_info": {"Role": "Araştırmacı", "TypeName": "research"},
            "state": "completed",
            "duration_seconds": 2.1
        },
        {
            "tool_name": "view_file",
            "tool_info": {"TargetFile": "tests/test_app.py"},
            "state": "running"
        }
    ]
    res = format_cumulative_status_telegram(tools)
    assert "📋 <b>Tamamlanan Adımlar (1):</b>" in res
    assert "invoke_subagent" in res
    assert "🔄 <b>Aktif İşlem:</b>" in res
    assert "view_file" in res
    # Subagent is done, so no active subagents at the bottom
    assert "Aktif Ajanlar" not in res
    assert "İşlem devam ediyor" not in res


def test_format_cumulative_status_telegram_html_safety_and_cutoff():
    # Test HTML escaping
    malicious_tools = [
        {
            "tool_name": "run_command",
            "tool_info": {"CommandLine": "cat <secret.txt> && echo 'test'"},
            "state": "running"
        }
    ]
    res = format_cumulative_status_telegram(malicious_tools, active_subagents=[{"name": "<InjectedAgent>"}])
    assert "<secret.txt>" not in res
    assert "&lt;secret.txt&gt;" in res
    assert "<InjectedAgent>" not in res
    assert "&lt;InjectedAgent&gt;" in res
    assert res.endswith("⏳ <i>Aktif Ajanlar: &lt;InjectedAgent&gt;</i>")

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
    long_res = format_cumulative_status_telegram(long_tools, active_subagents=[{"name": "Araştırmacı"}])
    assert len(long_res) <= 3600
    assert "..." in long_res
    assert long_res.endswith("⏳ <i>Aktif Ajanlar: Araştırmacı</i>")


def test_format_live_progress_panel_telegram_alias():
    tools = [{"tool_name": "list_dir", "tool_info": {"DirectoryPath": "/root"}, "state": "running"}]
    res = format_live_progress_panel_telegram(tools)
    assert "list_dir" in res
    assert "/root" in res
    assert "İşlem devam ediyor" not in res


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
    assert "İşlem devam ediyor" not in res


def test_loading_indicator_absence_in_final_outputs():
    """Verify loading indicator is NOT present in final stages summary, converted markdown, or stats footers."""
    tools = [
        {"tool_name": "view_file", "tool_info": {"TargetFile": "app.py"}, "state": "completed"},
        {"tool_name": "run_command", "tool_info": {"CommandLine": "pytest"}, "state": "completed"}
    ]
    stages_summary = format_execution_stages_telegram(tools)
    assert "İşlem devam ediyor" not in stages_summary
    assert "Aktif Ajanlar" not in stages_summary

    final_md = markdown_to_telegram_html("## Summary\nAll tests passed successfully!")
    assert "İşlem devam ediyor" not in final_md

    footer = format_stats_footer(1.5, {"total_tokens": 500})
    assert "İşlem devam ediyor" not in footer


def test_format_cumulative_status_telegram_with_accumulated_text_only():
    """Test cumulative status with only streaming LLM text and no tools."""
    res = format_cumulative_status_telegram([], current_text="Hello, I am processing your request.")
    assert res == "Hello, I am processing your request."
    assert "Düşünülüyor" not in res
    assert "İşlem devam ediyor" not in res


def test_format_cumulative_status_telegram_with_tools_and_accumulated_text():
    """Test cumulative status with tool progress on top and accumulated LLM text underneath."""
    tools = [
        {"tool_name": "view_file", "tool_info": {"TargetFile": "main.py"}, "state": "completed", "duration_seconds": 0.2},
        {"tool_name": "run_command", "tool_info": {"CommandLine": "pytest"}, "state": "running"}
    ]
    current_text = "Here is what I found in main.py so far:\n- Issue in line 42."
    res = format_cumulative_status_telegram(tools, current_text=current_text)

    # Tool sections should appear before the accumulated text
    tools_index = res.find("Aktif İşlem")
    text_index = res.find("Here is what I found")

    assert tools_index != -1
    assert text_index != -1
    assert tools_index < text_index
    assert "İşlem devam ediyor" not in res


def test_format_cumulative_status_telegram_with_tools_subagents_and_accumulated_text():
    """Test cumulative status with tools, active subagents, and accumulated LLM text."""
    tools = [
        {"tool_name": "view_file", "tool_info": {"TargetFile": "main.py"}, "state": "completed", "duration_seconds": 0.2},
        {"tool_name": "run_command", "tool_info": {"CommandLine": "pytest"}, "state": "running"}
    ]
    current_text = "Here is what I found in main.py so far:\n- Issue in line 42."
    active_subs = [{"name": "Araştırmacı"}]
    res = format_cumulative_status_telegram(tools, active_subagents=active_subs, current_text=current_text)

    tools_index = res.find("Aktif İşlem")
    text_index = res.find("Here is what I found")
    subagent_index = res.find("Aktif Ajanlar: Araştırmacı")

    assert tools_index != -1
    assert text_index != -1
    assert subagent_index != -1
    assert tools_index < text_index < subagent_index
    assert res.endswith("⏳ <i>Aktif Ajanlar: Araştırmacı</i>")


def test_format_cumulative_status_telegram_accumulated_text_markdown_formatting():
    """Test that Markdown formatting in streaming text is safely converted to Telegram HTML."""
    md_text = "Analysis result: **bold text** and `inline_code`"
    res = format_cumulative_status_telegram([], current_text=md_text)
    assert "<b>bold text</b>" in res
    assert "<code>inline_code</code>" in res
    assert "İşlem devam ediyor" not in res


def test_format_cumulative_status_telegram_long_accumulated_text_truncation():
    """Test that very long accumulated text is truncated to keep within safe Telegram message bounds."""
    long_text = "A" * 5000
    res = format_cumulative_status_telegram([], current_text=long_text)
    assert len(res) <= 3600
    assert "..." in res
    assert "İşlem devam ediyor" not in res


def test_format_cumulative_status_telegram_deduplication_and_strings():
    """Test that string subagents and duplicate names from tools/active_subagents are deduplicated."""
    tools = [
        {"tool_name": "invoke_subagent", "tool_info": {"Role": "Araştırmacı"}, "state": "running"}
    ]
    active_subs = [
        "Araştırmacı",
        "Kod Geliştirici",
        {"name": "Araştırmacı"},
        {"role": "Kod Geliştirici"}
    ]
    res = format_cumulative_status_telegram(tools, active_subagents=active_subs)
    assert res.endswith("⏳ <i>Aktif Ajanlar: Araştırmacı, Kod Geliştirici</i>")


def test_format_cumulative_status_telegram_filtered_inactive_subagents():
    """Test that subagents with completed/done states are excluded from active indicator."""
    active_subs = [
        {"name": "Done Agent", "status": "completed"},
        {"name": "Finished Agent", "state": "done"},
        {"name": "Running Agent", "status": "running"}
    ]
    res = format_cumulative_status_telegram([], active_subagents=active_subs)
    assert res.endswith("⏳ <i>Aktif Ajanlar: Running Agent</i>")
    assert "Done Agent" not in res
    assert "Finished Agent" not in res


def test_format_cumulative_status_telegram_various_name_keys():
    """Test that various subagent key names (TypeName, role, type) are extracted correctly."""
    active_subs = [
        {"TypeName": "researcher"},
        {"role": "tester"},
        {"type": "architect"}
    ]
    res = format_cumulative_status_telegram([], active_subagents=active_subs)
    assert res.endswith("⏳ <i>Aktif Ajanlar: researcher, tester, architect</i>")


def test_render_progress_bar_tokens_ratio():
    res = render_progress_bar(6_000_000, 10_000_000, width=10, unit="tokens")
    assert res == "[██████░░░░] %60.0 (6.0M / 10.0M)"


def test_render_progress_bar_mb():
    res1 = render_progress_bar(512, 1024, width=10, unit="MB")
    assert res1 == "[█████░░░░░] %50.0 (512.0 MB / 1024 MB)"

    res2 = render_progress_bar(1.5, 1024, width=10, unit="MB")
    assert res2 == "[░░░░░░░░░░] %0.1 (1.5 MB / 1024 MB)"


def test_render_progress_bar_overflow():
    res = render_progress_bar(12_000_000, 10_000_000, width=10, unit="tokens")
    assert res == "[██████████] %120.0 (12.0M / 10.0M)"


def test_render_progress_bar_zero_and_negative():
    res_zero = render_progress_bar(0, 10_000_000, width=10, unit="tokens")
    assert res_zero == "[░░░░░░░░░░] %0.0 (0.0M / 10.0M)"

    res_total_zero = render_progress_bar(0, 0, width=10, unit="tokens")
    assert res_total_zero == "[░░░░░░░░░░] %0.0 (0.0M / 0.0M)"

    res_neg = render_progress_bar(-50, 100, width=10, unit="")
    assert res_neg == "[░░░░░░░░░░] %0.0 (-50 / 100)"


def test_render_progress_bar_custom_units_and_widths():
    res_gb = render_progress_bar(25, 50, width=4, unit="GB")
    assert res_gb == "[██░░] %50.0 (25.0 GB / 50 GB)"

    res_kb = render_progress_bar(100, 200, width=6, unit="KB")
    assert res_kb == "[███░░░] %50.0 (100.0 KB / 200 KB)"

    res_custom = render_progress_bar(10, 20, width=5, unit="items")
    assert res_custom == "[██░░░] %50.0 (10 items / 20 items)"



