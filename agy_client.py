"""
Antigravity CLI Client wrapper.
Executes the `agy` CLI as an asynchronous subprocess and streams structured events.
Supports multiple concurrent users/sessions across Telegram and WebUI.
"""

import asyncio
import json
import logging
import os
import signal
import shutil
import psutil
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional, List, Union
from config import settings

logger = logging.getLogger(__name__)

MODEL_EFFORT_SUFFIXES = {"low", "medium", "high"}


def normalize_event_state(state: Optional[str]) -> str:
    """Normalize raw CLI event states (e.g. ACTIVE, DONE) to standard running/completed."""
    if not state:
        return "running"
    s = str(state).strip().lower()
    if s in ("active", "running", "start", "started", "in_progress"):
        return "running"
    if s in ("done", "completed", "complete", "finished", "success"):
        return "completed"
    return s


def normalize_model_name(model: Optional[str]) -> Optional[str]:
    """Remove an agy catalog effort suffix so effort can be selected separately."""
    if not model:
        return model
    name, separator, suffix = model.rpartition("-")
    if separator and suffix.lower() in MODEL_EFFORT_SUFFIXES:
        return name
    return model


class AgyClient:
    def __init__(self, bin_path: Optional[str] = None):
        self.bin_path = bin_path or settings.AGY_BIN_PATH
        self._active_processes: Dict[Union[int, str], asyncio.subprocess.Process] = {}

    def cancel_task(self, user_id: Union[int, str]) -> bool:
        """Cancel an ongoing agy process for a specific user or web session."""
        proc = self._active_processes.get(user_id)
        if proc and proc.returncode is None:
            try:
                try:
                    # Terminate whole process group if process group leader
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except Exception:
                    proc.send_signal(signal.SIGTERM)
                logger.info(f"Sent SIGTERM to agy process {proc.pid} for user/session {user_id}")
                return True
            except ProcessLookupError:
                self._active_processes.pop(user_id, None)
            except Exception as e:
                logger.error(f"Error terminating process for user/session {user_id}: {e}")
        return False

    def cancel_all(self):
        """Cancel all active agy processes."""
        for uid in list(self._active_processes.keys()):
            self.cancel_task(uid)

    def is_running(self, user_id: Union[int, str]) -> bool:
        """Check if a process is actively running for a user/session."""
        proc = self._active_processes.get(user_id)
        if proc is None:
            return False
        if proc.returncode is not None:
            self._active_processes.pop(user_id, None)
            return False
        return True

    def get_active_count(self) -> int:
        """Get the count of currently running agy processes."""
        dead_keys = [uid for uid, proc in self._active_processes.items() if proc.returncode is not None]
        for uid in dead_keys:
            self._active_processes.pop(uid, None)
        return len(self._active_processes)

    async def send_input(self, user_id: Union[int, str], text: str) -> bool:
        """Send standard input to an active agy process."""
        proc = self._active_processes.get(user_id)
        if proc and proc.returncode is None and proc.stdin:
            try:
                proc.stdin.write(f"{text}\n".encode("utf-8"))
                await proc.stdin.drain()
                logger.info(f"Sent stdin input to agy process {proc.pid} for session {user_id}")
                return True
            except Exception as e:
                logger.error(f"Error sending input to process for session {user_id}: {e}")
        return False

    async def run_prompt_stream(
        self,
        user_id: Union[int, str],
        prompt: str,
        conversation_id: Optional[str] = None,
        workspace: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        auto_approve: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute prompt via `agy` CLI in streaming JSON mode.
        Yields structured dictionaries for init, step_updates, tool calls, text deltas, and final result.
        """
        workspace_dir = workspace or settings.DEFAULT_WORKSPACE
        if not os.path.isdir(workspace_dir):
            workspace_dir = "/root"

        cmd = [
            self.bin_path,
            "--output-format", "stream-json",
            "-p", prompt
        ]

        if auto_approve:
            cmd.append("--dangerously-skip-permissions")

        if conversation_id:
            cmd.extend(["--conversation", conversation_id])

        model = normalize_model_name(model)
        if model:
            cmd.extend(["--model", model])

        if effort:
            cmd.extend(["--effort", effort])

        if workspace_dir:
            cmd.extend(["--add-dir", workspace_dir])

        logger.info(f"Starting agy subprocess for session {user_id}: {' '.join(cmd[:6])}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
                start_new_session=True
            )
            self._active_processes[user_id] = process

            accumulated_text = ""
            current_conv_id = conversation_id
            stderr_output = []

            # Background task to read stderr
            async def read_stderr():
                try:
                    while True:
                        line = await process.stderr.readline()
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded:
                            stderr_output.append(decoded)
                            logger.debug(f"[agy stderr {user_id}] {decoded}")
                except Exception as e:
                    logger.debug(f"read_stderr finished with: {e}")

            stderr_task = asyncio.create_task(read_stderr())

            # Read NDJSON events from stdout line by line
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                raw_line = line.decode("utf-8", errors="replace").strip()
                if not raw_line:
                    continue

                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON line from agy: {raw_line[:100]}")
                    continue

                event_type = event.get("event")

                if event_type == "init":
                    current_conv_id = event.get("conversation_id")
                    yield {
                        "type": "init",
                        "conversation_id": current_conv_id,
                        "init": event.get("init", {})
                    }

                elif event_type == "step_update":
                    step_update = event.get("step_update", {})
                    step_type = step_update.get("step_type")
                    text_delta = step_update.get("text_delta", "")
                    raw_state = step_update.get("state")
                    normalized_state = normalize_event_state(raw_state)
                    
                    if text_delta:
                        accumulated_text += text_delta

                    yield {
                        "type": "step_update",
                        "step_type": step_type,
                        "state": normalized_state,
                        "text_delta": text_delta,
                        "accumulated_text": accumulated_text,
                        "tool_name": step_update.get("tool_name"),
                        "tool_info": step_update.get("tool_info", {}),
                        "active_subagents": step_update.get("active_subagents") or event.get("active_subagents"),
                        "duration_seconds": step_update.get("duration_seconds")
                    }

                elif event_type == "result":
                    result = event.get("result", {})
                    final_response = result.get("response", accumulated_text)
                    yield {
                        "type": "result",
                        "conversation_id": result.get("conversation_id", current_conv_id),
                        "status": result.get("status", "SUCCESS"),
                        "response": final_response,
                        "duration_seconds": result.get("duration_seconds", 0.0),
                        "usage": result.get("usage", {}),
                        "num_turns": result.get("num_turns", 1)
                    }

            await process.wait()
            try:
                await asyncio.wait_for(stderr_task, timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                stderr_task.cancel()

            if process.returncode != 0 and process.returncode not in (0, -signal.SIGTERM, 143):
                error_msg = "\n".join(stderr_output) or f"Process exited with code {process.returncode}"
                logger.error(f"agy process failed for session {user_id}: {error_msg}")
                yield {
                    "type": "error",
                    "error": error_msg,
                    "returncode": process.returncode
                }

        except asyncio.CancelledError:
            self.cancel_task(user_id)
            raise
        except Exception as e:
            logger.exception(f"Unexpected exception while running agy for session {user_id}")
            yield {
                "type": "error",
                "error": str(e)
            }
        finally:
            self._active_processes.pop(user_id, None)

    async def get_available_models(self) -> List[str]:
        """Fetch available models from `agy models`."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.bin_path, "models",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")
            models = []
            for line in output.splitlines():
                line = line.strip()
                if not line or "Fetching" in line or line.startswith("#"):
                    continue
                # First column is model name
                parts = line.split()
                if parts:
                    models.append(normalize_model_name(parts[0]))
            return list(dict.fromkeys(models)) or ["gemini-3.7-flash", "gemini-3.1-pro", "claude-sonnet-4-6"]
        except Exception as e:
            logger.error(f"Failed to fetch models: {e}")
            return ["gemini-3.7-flash", "gemini-3.1-pro", "claude-sonnet-4-6"]

    async def get_official_quotas(self) -> Dict[str, Any]:
        """
        Fetch official API quotas (5-hour and weekly limits) via `agy --output-format json -p "/usage"`.
        Returns structured quota data including groups, buckets, and remaining percentages.
        """
        cmd = [
            self.bin_path,
            "--output-format", "json",
            "-p", "/usage"
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            raw_output = stdout.decode("utf-8", errors="replace").strip()
            if not raw_output:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.warning(f"Empty output from agy usage command: {err_msg}")
                return {"success": False, "groups": [], "error": err_msg or "Empty output"}

            data = json.loads(raw_output)
            groups = []

            # 1. Structured format from command.data.groups
            command_data = data.get("command", {}).get("data", {}) if isinstance(data, dict) else {}
            raw_groups = command_data.get("groups") if isinstance(command_data, dict) else None

            if raw_groups and isinstance(raw_groups, list):
                for g in raw_groups:
                    group_name = g.get("name", "")
                    group_desc = g.get("description", "")
                    buckets = []
                    for b in g.get("buckets", []):
                        rem_frac = b.get("remaining_fraction")
                        if rem_frac is not None:
                            rem_pct = round(float(rem_frac) * 100.0, 1)
                        else:
                            rem_pct = 100.0
                        buckets.append({
                            "id": b.get("id", ""),
                            "name": b.get("name", ""),
                            "description": b.get("description", ""),
                            "window": b.get("window", ""),
                            "remaining_fraction": float(rem_frac) if rem_frac is not None else 1.0,
                            "remaining_percent": rem_pct,
                            "reset_time": b.get("reset_time", "")
                        })
                    groups.append({
                        "name": group_name,
                        "description": group_desc,
                        "buckets": buckets
                    })

            # 2. Fallback: Parse TSV formatted response if structured groups missing
            if not groups and isinstance(data, dict):
                raw_response = data.get("response") or data.get("result", {}).get("response", "")
                if raw_response and isinstance(raw_response, str):
                    groups_dict: Dict[str, Dict[str, Any]] = {}
                    for line in raw_response.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 3:
                            g_name = parts[0].strip()
                            b_name = parts[1].strip()
                            pct_str = parts[2].strip().replace("%", "")
                            reset_t = parts[3].strip() if len(parts) >= 4 else ""
                            try:
                                rem_pct = float(pct_str)
                            except ValueError:
                                rem_pct = 100.0
                            rem_frac = rem_pct / 100.0
                            window = "5h" if ("5" in b_name or "five" in b_name.lower()) else "weekly"

                            if g_name not in groups_dict:
                                groups_dict[g_name] = {
                                    "name": g_name,
                                    "description": "",
                                    "buckets": []
                                }
                            groups_dict[g_name]["buckets"].append({
                                "id": f"{g_name.lower()}-{window}",
                                "name": b_name,
                                "description": "",
                                "window": window,
                                "remaining_fraction": rem_frac,
                                "remaining_percent": rem_pct,
                                "reset_time": reset_t
                            })
                    groups = list(groups_dict.values())

            return {
                "success": True,
                "groups": groups,
                "raw_response": data.get("response", "") if isinstance(data, dict) else ""
            }
        except Exception as e:
            logger.error(f"Failed to fetch official quotas from agy: {e}")
            return {
                "success": False,
                "groups": [],
                "error": str(e)
            }


    @staticmethod
    def get_system_stats() -> Dict[str, Any]:
        """Fetch system statistics (CPU, RAM, Disk)."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "cpu_percent": cpu_percent,
                "memory_total_gb": round(mem.total / (1024 ** 3), 2),
                "memory_used_gb": round(mem.used / (1024 ** 3), 2),
                "memory_percent": mem.percent,
                "disk_total_gb": round(disk.total / (1024 ** 3), 2),
                "disk_used_gb": round(disk.used / (1024 ** 3), 2),
                "disk_free_gb": round(disk.free / (1024 ** 3), 2),
                "disk_percent": disk.percent
            }
        except Exception as e:
            logger.warning(f"Failed to get psutil stats: {e}")
            total, used, free = shutil.disk_usage("/")
            return {
                "cpu_percent": 0,
                "memory_total_gb": 0,
                "memory_used_gb": 0,
                "memory_percent": 0,
                "disk_total_gb": round(total / (1024 ** 3), 2),
                "disk_used_gb": round(used / (1024 ** 3), 2),
                "disk_free_gb": round(free / (1024 ** 3), 2),
                "disk_percent": round((used / total) * 100, 1)
            }


agy_client = AgyClient()
