"""
Antigravity CLI Client wrapper.
Executes the `agy` CLI as an asynchronous subprocess and streams structured events.
"""

import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional
from config import settings

logger = logging.getLogger(__name__)


class AgyClient:
    def __init__(self, bin_path: Optional[str] = None):
        self.bin_path = bin_path or settings.AGY_BIN_PATH
        self._active_processes: Dict[int, asyncio.subprocess.Process] = {}

    def cancel_task(self, user_id: int) -> bool:
        """Cancel an ongoing agy process for a specific user."""
        proc = self._active_processes.get(user_id)
        if proc and proc.returncode is None:
            try:
                proc.send_signal(signal.SIGTERM)
                logger.info(f"Sent SIGTERM to agy process {proc.pid} for user {user_id}")
                return True
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error(f"Error terminating process for user {user_id}: {e}")
        return False

    async def run_prompt_stream(
        self,
        user_id: int,
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

        if model:
            cmd.extend(["--model", model])

        if effort:
            cmd.extend(["--effort", effort])

        if workspace_dir:
            cmd.extend(["--add-dir", workspace_dir])

        logger.info(f"Starting agy subprocess for user {user_id}: {' '.join(cmd[:6])}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            self._active_processes[user_id] = process

            accumulated_text = ""
            current_conv_id = conversation_id
            stderr_output = []

            # Background task to read stderr
            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        stderr_output.append(decoded)
                        logger.debug(f"[agy stderr {user_id}] {decoded}")

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
                    
                    if text_delta:
                        accumulated_text += text_delta

                    yield {
                        "type": "step_update",
                        "step_type": step_type,
                        "state": step_update.get("state"),
                        "text_delta": text_delta,
                        "accumulated_text": accumulated_text,
                        "tool_name": step_update.get("tool_name"),
                        "tool_info": step_update.get("tool_info", {}),
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
            await stderr_task

            if process.returncode != 0 and process.returncode != -signal.SIGTERM:
                error_msg = "\n".join(stderr_output) or f"Process exited with code {process.returncode}"
                logger.error(f"agy process failed for user {user_id}: {error_msg}")
                yield {
                    "type": "error",
                    "error": error_msg,
                    "returncode": process.returncode
                }

        except asyncio.CancelledError:
            self.cancel_task(user_id)
            raise
        except Exception as e:
            logger.exception(f"Unexpected exception while running agy for user {user_id}")
            yield {
                "type": "error",
                "error": str(e)
            }
        finally:
            self._active_processes.pop(user_id, None)

    async def get_available_models(self) -> list[str]:
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
                if not line or "Fetching" in line:
                    continue
                # First column is model name
                parts = line.split()
                if parts:
                    models.append(parts[0])
            return models or ["gemini-3.7-flash-high", "gemini-3.1-pro-high", "claude-sonnet-4-6"]
        except Exception as e:
            logger.error(f"Failed to fetch models: {e}")
            return ["gemini-3.7-flash-high", "gemini-3.1-pro-high", "claude-sonnet-4-6"]


agy_client = AgyClient()
