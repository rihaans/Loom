"""ChatSession — the chat REPL loop driver.

This is the top-level controller for interactive Loom sessions. It:
  1. Compiles the graph in interactive mode
  2. Reads user input
  3. Pushes input into graph state via `update_state`
  4. Resumes the graph until it interrupts or completes
  5. Renders agent output between turns
  6. Dispatches slash commands
  7. Persists transcripts

The ChatSession does NOT know anything about prompt_toolkit or rich
internals — it composes ChatInputReader and ChatRenderer.

Set LOOM_CHAT_DEBUG=1 to dump snapshot state at each loop iteration.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from loom.cli.chat.commands import (
    HELP_ENTRIES,
    SlashCommand,
    SlashCommandParser,
    SlashCommandResult,
)
from loom.cli.chat.input import ChatInputReader
from loom.cli.chat.renderer import ChatRenderer
from loom.cli.chat.transcript import append_event, get_chat_path
from loom.config import LoomConfig
from loom.graph.builder import compile_graph
from loom.graph.routing import is_paused_for_input
from loom.state.enums import AgentRole

# Short affirmative replies that should trigger drafting when the agent has
# asked something like "want me to draft?" — treats plain "yes" as /done so
# users don't have to remember the slash-command form.
_AFFIRMATIVE_INPUTS = {
    "y",
    "yes",
    "yeah",
    "yep",
    "yup",
    "yea",
    "ya",
    "ok",
    "okay",
    "k",
    "sure",
    "fine",
    "go",
    "go ahead",
    "do it",
    "ship it",
    "draft",
    "draft it",
    "draft the prd",
    "draft now",
    "done",
    "looks good",
    "lgtm",
    "perfect",
    "great",
    "please",
    "please do",
}

# Words that indicate affirmative intent at the start of a longer reply.
_AFFIRMATIVE_PREFIXES = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "ok",
    "okay",
    "sure",
    "go",
    "draft",
    "do",
    "done",
    "perfect",
    "great",
}


def looks_affirmative(text: str) -> bool:
    """Return True if `text` is a short affirmative reply.

    Catches plain "yes" and short variants like "yes go ahead",
    "ok do it", "sure make it now". For longer prose we assume the
    user wants to keep talking.
    """
    cleaned = text.strip().lower().rstrip("!.?,")
    if not cleaned:
        return False
    if cleaned in _AFFIRMATIVE_INPUTS:
        return True
    # Short replies (< 30 chars) that begin with an affirmative word
    if len(cleaned) < 30:
        words = cleaned.split()
        if words and words[0] in _AFFIRMATIVE_PREFIXES:
            return True
    return False


logger = logging.getLogger(__name__)


class ChatSession:
    """Drives the chat REPL loop.

    Args:
        config: Loaded Loom configuration
        renderer: Output renderer (defaults to a new ChatRenderer)
        input_reader: Input reader (defaults to a new ChatInputReader)
        checkpointer: LangGraph checkpointer (defaults to MemorySaver)
        thread_id: Optional thread ID for resume; if None, a fresh one is generated
    """

    def __init__(
        self,
        config: LoomConfig | None = None,
        renderer: ChatRenderer | None = None,
        input_reader: ChatInputReader | None = None,
        checkpointer: Any | None = None,
        thread_id: str | None = None,
    ) -> None:
        self.config = config or LoomConfig()
        self.renderer = renderer or ChatRenderer()
        self.input_reader = input_reader or ChatInputReader()
        self.checkpointer = checkpointer or MemorySaver()
        self.thread_id = thread_id or f"chat-{uuid.uuid4().hex[:8]}"
        self.parser = SlashCommandParser()
        self._graph: Any = None  # compiled graph (lazy)
        self._current_role: str = AgentRole.PRODUCT_MANAGER.value
        # Per-role render cursor: how many messages we've already rendered
        # for each agent. Tracking this per role (not as a single counter)
        # is essential — when the conversation transitions PM → Architect,
        # the architect's history starts at 0 and would otherwise be skipped
        # because PM's count was higher.
        self._rendered_count: dict[str, int] = {}
        self._rendered_artifacts: set[str] = set()
        self._transcript_path = get_chat_path(self.thread_id)

    # ---- Public API -----------------------------------------------------

    @property
    def thread_config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self.thread_id}}

    async def run(self, initial_input: str | None = None) -> dict[str, Any]:
        """Run the chat REPL.

        Args:
            initial_input: Optional first user message (otherwise prompted).

        Returns:
            The final graph state values.
        """
        self._render_startup_banner()
        self._graph = compile_graph(self.config, checkpointer=self.checkpointer, interactive=True)

        # Step 1: Get the user's first message — this becomes state.description
        first_input = initial_input or await self._read_input()
        if first_input is None:
            return {}
        append_event(
            self._transcript_path,
            {"role": "user", "content": first_input},
        )

        # Bootstrap state and run first PM turn
        initial_state = {
            "description": first_input,
            "interactive": True,
            "agent_messages": {},
            "events": [],
            "costs": [],
            "code_files": {},
            "max_retries": self.config.max_retries,
        }

        # Initial graph invocation — show a thinking spinner
        with self.renderer.thinking(self._thinking_label_for_phase(None)):
            await self._graph.ainvoke(initial_state, config=self.thread_config)

        # Main loop: render, read, dispatch
        while True:
            snapshot = await self._graph.aget_state(self.thread_config)
            values: dict[str, Any] = snapshot.values

            if os.environ.get("LOOM_CHAT_DEBUG"):
                self.renderer.console.print(
                    f"[dim][debug] next={snapshot.next} "
                    f"agent_status={values.get('agent_status')!r} "
                    f"interactive={values.get('interactive')!r} "
                    f"prd={'set' if values.get('prd') else 'None'} "
                    f"error={values.get('error')!r}[/dim]"
                )

            # Render any new agent output since last turn (animated)
            await self._render_new_agent_messages(values)

            # Surface any error from the agent (e.g. LLM hiccup) so the user
            # can see it before being prompted again.
            err = values.get("error")
            if err:
                self.renderer.render_error(
                    f"{err}",
                    hint="You can retry by typing again, or /quit to exit.",
                )
                # Clear the error so we don't keep showing it.
                await self._graph.aupdate_state(self.thread_config, {"error": None})

            # If the graph is no longer paused for input, it's either done or running
            if not is_paused_for_input(values):
                # Check if graph reached END
                if not snapshot.next:
                    # If we got here without a PRD or any real output, the graph
                    # routed to END unexpectedly (probably an error path). Don't
                    # render a misleading "Build complete" — show a diagnostic.
                    has_real_output = (
                        values.get("prd") is not None
                        or values.get("output_dir") is not None
                        or values.get("code_files")
                    )
                    if not has_real_output:
                        self.renderer.render_error(
                            "The build pipeline ended without producing output.",
                            hint=(
                                "This usually means the LLM produced an unexpected "
                                "response on a clarifying turn. Try a fresh `loom` "
                                "session and use shorter inputs, or switch to a "
                                "non-coder model: `loom --model ollama:llama3.1:8b`"
                            ),
                        )
                        return values
                    # Real build completed
                    self._render_completion(values)
                    return values
                # Graph wants to advance — resume it with a thinking spinner
                try:
                    with self.renderer.thinking(self._thinking_label_for_phase(values)):
                        await self._graph.ainvoke(None, config=self.thread_config)
                    continue
                except Exception as e:
                    logger.error(f"Graph resume failed: {e}")
                    self.renderer.render_error(f"Build failed: {e}")
                    return values

            # Paused for input — solicit user reply
            try:
                user_text = await self._read_input()
            except (KeyboardInterrupt, EOFError):
                self.renderer.render_status("Exiting…")
                return values

            if user_text is None or not user_text.strip():
                continue

            # Convenience: short affirmative responses ("yes", "ok do it",
            # "draft", "done") auto-trigger drafting. The agent is in
            # `wait_for_input` or `ready_to_draft` and the user has
            # expressed assent — there's no useful conversational content
            # to send the LLM.
            if looks_affirmative(user_text):
                user_text = "__DRAFT__"

            # Slash commands
            if self.parser.is_slash_command(user_text):
                cmd = self.parser.parse(user_text)
                append_event(
                    self._transcript_path,
                    {
                        "role": "system",
                        "command": cmd.command.value,
                        "args": cmd.args,
                    },
                )
                action = await self._handle_slash(cmd, values)
                if action == "exit":
                    return values
                if action == "draft":
                    user_text = "__DRAFT__"
                else:
                    # Command consumed; loop back to prompt again
                    continue

            # Persist the user input for transcript replay
            append_event(
                self._transcript_path,
                {"role": "user", "content": user_text},
            )

            # Push the user input into the graph state and resume.
            # Re-assert interactive=True so the chat-mode routing always
            # fires (defensive against any state-merging surprises).
            await self._graph.aupdate_state(
                self.thread_config,
                {
                    "pending_user_input": user_text,
                    "interactive": True,
                },
            )
            try:
                # Wrap the LLM-bound work in the thinking spinner
                label = (
                    "drafting"
                    if user_text == "__DRAFT__"
                    else self._thinking_label_for_phase(values)
                )
                with self.renderer.thinking(label):
                    await self._graph.ainvoke(None, config=self.thread_config)
            except Exception as e:
                logger.error(f"Graph step failed: {e}")
                self.renderer.render_error(f"Build step failed: {e}")
                return values

    # ---- Slash command dispatch ----------------------------------------

    async def _handle_slash(self, cmd: SlashCommandResult, values: dict[str, Any]) -> str | None:
        """Handle a slash command.

        Returns:
            "exit" if the session should terminate
            "draft" if the user wants to draft (the loop converts this to __DRAFT__)
            None for commands that were handled internally
        """
        if cmd.command == SlashCommand.HELP:
            self.renderer.render_help(HELP_ENTRIES)
            return None

        if cmd.command == SlashCommand.STATUS:
            self._render_status(values)
            return None

        if cmd.command == SlashCommand.CLEAR:
            self.renderer.clear()
            return None

        if cmd.command == SlashCommand.QUIT:
            self.renderer.render_status("Saving and exiting…")
            return "exit"

        if cmd.command in (SlashCommand.DONE, SlashCommand.SKIP):
            return "draft"

        if cmd.command == SlashCommand.RESTART:
            self.renderer.render_status("Restart not yet wired — exit and re-run for now")
            return None

        if cmd.command == SlashCommand.BACK:
            self.renderer.render_status("Back not yet wired — see /restart")
            return None

        if cmd.command == SlashCommand.SHOW:
            self._handle_show(cmd, values)
            return None

        if cmd.command == SlashCommand.SAVE:
            self.renderer.render_status("Save not yet wired (Phase 9.5)")
            return None

        if cmd.command == SlashCommand.MODEL:
            self._handle_model(cmd)
            return None

        if cmd.command == SlashCommand.COST:
            self._render_cost(values)
            return None

        # UNKNOWN
        self.renderer.render_error(
            f"Unknown command: {cmd.raw}",
            hint="Type /help for the list of commands.",
        )
        return None

    def _handle_show(self, cmd: SlashCommandResult, values: dict[str, Any]) -> None:
        if not cmd.args:
            self.renderer.render_error("Usage: /show <prd|architecture|code|tests>")
            return
        what = cmd.args[0].lower()
        if what == "prd":
            self.renderer.render_prd_panel(values.get("prd"))
        elif what in ("architecture", "arch"):
            self.renderer.render_architecture_panel(values.get("architecture"))
        elif what == "code":
            files = values.get("code_files", {})
            count = sum(len(b.files) for b in files.values() if hasattr(b, "files"))
            self.renderer.render_status(f"{count} files generated across {len(files)} bundles")
        elif what == "tests":
            self.renderer.render_test_report(values.get("test_report"))
        else:
            self.renderer.render_error(f"Unknown artifact type: {what}")

    def _handle_model(self, cmd: SlashCommandResult) -> None:
        if not cmd.args:
            llm = self.config.llm_default
            self.renderer.render_status(f"Current model: {llm.provider}:{llm.model}")
            return
        # We don't actually swap the model live yet — Phase 9.7 polish
        self.renderer.render_status(
            f"Live model swap not yet wired. Restart with --model {cmd.args[0]}"
        )

    def _render_cost(self, values: dict[str, Any]) -> None:
        """Render the `/cost` command — per-role breakdown table."""
        costs = values.get("costs", [])

        # Group token / dollar totals by agent role. CostEntry uses `agent`;
        # tolerate `agent_role` / `role` for tests and forward-compat.
        per_role: dict[str, list[int]] = {}  # role -> [input_tok, output_tok, micro_cost]
        for c in costs:
            role = (
                getattr(c, "agent", None)
                or getattr(c, "agent_role", None)
                or getattr(c, "role", None)
                or "unknown"
            )
            role_key = str(role).lower() if role else "unknown"
            entry = per_role.setdefault(role_key, [0, 0, 0])
            entry[0] += int(getattr(c, "input_tokens", 0) or 0)
            entry[1] += int(getattr(c, "output_tokens", 0) or 0)
            # Store cost in micro-dollars to avoid float drift in summation.
            entry[2] += round(float(getattr(c, "cost_usd", 0.0) or 0.0) * 1_000_000)

        # Convert micro-cost back to dollars and tuple-ify for the renderer.
        per_role_out: dict[str, tuple[int, int, float]] = {
            role: (vals[0], vals[1], vals[2] / 1_000_000) for role, vals in per_role.items()
        }
        total_tokens = sum(v[0] + v[1] for v in per_role_out.values())
        total_cost = sum(v[2] for v in per_role_out.values())

        self.renderer.render_cost_table(per_role_out, total_tokens, total_cost)

    def _render_status(self, values: dict[str, Any]) -> None:
        """Render the `/status` command — current build state at-a-glance."""
        costs = values.get("costs", [])
        total_cost = sum(float(getattr(c, "cost_usd", 0.0) or 0.0) for c in costs)
        total_tokens = sum(
            int(getattr(c, "input_tokens", 0) or 0) + int(getattr(c, "output_tokens", 0) or 0)
            for c in costs
        )

        phase_val = values.get("phase")
        phase_str = str(phase_val) if phase_val else None

        llm = self.config.llm_default
        model_label = f"{llm.provider}:{llm.model}"

        artifacts = {
            "PRD": values.get("prd") is not None,
            "Architecture": values.get("architecture") is not None,
            "Code": bool(values.get("code_files")),
            "Tests": values.get("test_report") is not None,
            "DevOps": values.get("devops_files") is not None,
        }

        self.renderer.render_status_panel(
            phase=phase_str,
            active_role=self._current_role,
            tokens=total_tokens,
            cost_usd=total_cost,
            retries=int(values.get("retry_count", 0) or 0),
            max_retries=int(values.get("max_retries", self.config.max_retries) or 0),
            artifacts=artifacts,
            model_label=model_label,
        )

    # ---- Internal helpers ----------------------------------------------

    def _thinking_label_for_phase(self, values: dict[str, Any] | None) -> str:
        """Return a short, contextual label for the thinking spinner."""
        if values is None:
            return "thinking"
        # If the user just hit /done or "yes" we're drafting
        if values.get("pending_user_input") == "__DRAFT__":
            return "drafting"
        # If we're between agents, name the next agent
        next_phase = self._current_role
        labels = {
            "product_manager": "PM is thinking",
            "architect": "architect is designing",
            "frontend_dev": "frontend dev is coding",
            "backend_dev": "backend dev is coding",
            "code_reviewer": "reviewer is critiquing the code",
            "qa_engineer": "QA is running tests",
            "devops_engineer": "DevOps is packaging",
        }
        return labels.get(next_phase, "thinking")

    def _render_startup_banner(self) -> None:
        from loom import __version__ as loom_version

        llm = self.config.llm_default
        model_label = f"{llm.provider}:{llm.model}"
        self.renderer.render_banner(loom_version, model_label)

    def _render_completion(self, values: dict[str, Any]) -> None:
        output_dir = values.get("output_dir", "(not set)")
        costs = values.get("costs", [])
        total_cost = sum(getattr(c, "cost_usd", 0.0) for c in costs)
        total_tokens = sum(
            getattr(c, "input_tokens", 0) + getattr(c, "output_tokens", 0) for c in costs
        )

        # Surface the Code Reviewer's verdict before the final summary so the
        # generator-critic loop is visible in the autonomous build phase.
        review_report = values.get("review_report")
        if review_report is not None:
            self.renderer.render_review_panel(review_report)

        code_files = values.get("code_files", {}) or {}
        file_count = sum(len(b.files) for b in code_files.values() if hasattr(b, "files"))
        self.renderer.render_completion(
            str(output_dir),
            total_cost,
            total_tokens,
            test_report=values.get("test_report"),
            review_report=review_report,
            files=file_count or None,
        )

    async def _render_new_agent_messages(self, values: dict[str, Any]) -> None:
        """Render any agent messages we haven't shown yet — animated.

        Walks agent_messages and renders new AIMessages with a typewriter
        effect. Tracks per-role message counts so PM → Architect transitions
        don't skip Architect's first messages.
        """
        agent_messages: dict[str, list[Any]] = values.get("agent_messages", {}) or {}
        for role_key, history in agent_messages.items():
            already_rendered = self._rendered_count.get(role_key, 0)
            new_count = len(history)
            if new_count <= already_rendered:
                continue
            new_msgs = history[already_rendered:]
            # If the work just moved to a new agent, drop a one-line phase
            # breadcrumb so the user has a "you are here" indicator without
            # having to type /status.
            if role_key != self._current_role:
                self.renderer.render_phase_breadcrumb(role_key)
            for msg in new_msgs:
                if isinstance(msg, AIMessage):
                    self.renderer.render_agent_speaker(role_key)
                    await self.renderer.render_agent_message_animated(role_key, str(msg.content))
                    append_event(
                        self._transcript_path,
                        {
                            "role": "assistant",
                            "agent": role_key,
                            "content": msg.content,
                        },
                    )
                # HumanMessages we already showed at the input prompt
            self._rendered_count[role_key] = new_count
            self._current_role = role_key

        # Render artifacts when an agent transitions to "done" — only once
        status = values.get("agent_status")
        if status == "done":
            if values.get("prd") is not None and "prd" not in self._rendered_artifacts:
                self.renderer.render_prd_panel(values["prd"])
                self._rendered_artifacts.add("prd")
            if (
                values.get("architecture") is not None
                and "architecture" not in self._rendered_artifacts
            ):
                self.renderer.render_architecture_panel(values["architecture"])
                self._rendered_artifacts.add("architecture")

    async def _read_input(self) -> str | None:
        """Read one line of user input. Returns None on EOF."""
        try:
            return await self.input_reader.read()
        except EOFError:
            return None
        except KeyboardInterrupt:
            self.renderer.render_status("Cancelled")
            return None
