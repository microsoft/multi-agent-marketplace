"""Example agents that use the text-only protocol.

This example shows a Writer sending text to a Proofreader for correction.
The Proofreader uses an LLM to fix errors and explain changes.
"""

import asyncio
from datetime import UTC, datetime

from magentic_marketplace.marketplace.llm.functional import generate
from magentic_marketplace.platform.agent.base import BaseAgent
from magentic_marketplace.platform.shared.models import AgentProfile

from cookbook.text_only_protocol.actions import CheckMessages, SendTextMessage
from cookbook.text_only_protocol.messaging import TextMessage


class WriterAgent(BaseAgent[AgentProfile]):
    """Agent that sends text for proofreading to multiple proofreaders."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        proofreader_ids: list[str],
        text_to_proofread: str,
    ):
        """Initialize writer agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            proofreader_ids: List of proofreader agent IDs
            text_to_proofread: Text content to send for proofreading

        """
        super().__init__(profile, server_url)
        self.proofreader_ids = proofreader_ids
        self.text_to_proofread = text_to_proofread
        self.initialized = False
        self.text_sent = False
        self.expected_responses = len(proofreader_ids)
        self.received_count = 0

    async def step(self) -> None:
        """Send text to all proofreaders and collect corrections."""
        if not self.initialized:
            await asyncio.sleep(1)
            self.initialized = True

            # Resolve proofreader IDs from registered agents
            agents_response = await self.client.agents.list(limit=100)
            resolved_ids = []
            for proofreader_prefix in self.proofreader_ids:
                for agent in agents_response.items:
                    if agent.id.startswith(proofreader_prefix) and agent.id != self.id:
                        resolved_ids.append(agent.id)
                        break
            self.proofreader_ids = resolved_ids

        if not self.text_sent:
            preview = self.text_to_proofread[:60].replace("\n", " ") + "..." if len(self.text_to_proofread) > 60 else self.text_to_proofread
            print(f"\n[{self.id}] Sending {len(self.text_to_proofread)} chars to {len(self.proofreader_ids)} proofreaders")
            print(f"[{self.id}] First 60 chars: {preview}\n")

            for proofreader_id in self.proofreader_ids:
                await self._send_message(proofreader_id, self.text_to_proofread)

            self.text_sent = True

        result = await self.execute_action(CheckMessages())

        if not result.is_error and self.received_count < self.expected_responses:
            messages = result.content.get("messages", [])
            new_count = len(messages)

            if new_count > self.received_count:
                new_messages = messages[self.received_count:]
                for msg in new_messages:
                    sender_id = msg["from_agent_id"]
                    content = msg["message"]["content"]

                    # Extract model name from response
                    model_name = "Unknown"
                    if content.startswith("["):
                        end_bracket = content.find("]")
                        if end_bracket > 0:
                            model_name = content[1:end_bracket]

                    print(f"[{self.id}] ✓ Received correction from {sender_id} using {model_name}\n")

                self.received_count = new_count

        await asyncio.sleep(1.5)

    async def _send_message(self, to_agent_id: str, content: str) -> None:
        """Send a message to a specific proofreader."""
        message = TextMessage(content=content)
        send_action = SendTextMessage(
            from_agent_id=self.id,
            to_agent_id=to_agent_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await self.execute_action(send_action)

        if result.is_error:
            print(f"[{self.id}] Failed to send to {to_agent_id}: {result.content}")


class ProofreaderAgent(BaseAgent[AgentProfile]):
    """Agent that receives text, corrects it, and explains changes using an LLM."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        llm_provider: str,
        llm_model: str,
    ):
        """Initialize proofreader agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            llm_provider: LLM provider (openai, anthropic, gemini)
            llm_model: Model name for the LLM

        """
        super().__init__(profile, server_url)
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.initialized = False
        self.processed_message_count = 0

    async def step(self) -> None:
        """Check for text to proofread and send corrections."""
        if not self.initialized:
            await asyncio.sleep(1)
            self.initialized = True

        result = await self.execute_action(CheckMessages())

        if not result.is_error:
            messages = result.content.get("messages", [])
            if len(messages) > self.processed_message_count:
                new_messages = messages[self.processed_message_count :]
                for msg in new_messages:
                    sender_id = msg["from_agent_id"]
                    text = msg["message"]["content"]

                    char_count = len(text)
                    print(f"[{self.id}] Received {char_count} chars from {sender_id}")
                    print(f"[{self.id}] Proofreading with {self.llm_model}...")

                    corrected, explanation = await self._proofread(text)
                    response = f"[{self.llm_model}]\n\nCORRECTED TEXT:\n{corrected}\n\nCHANGES:\n{explanation}"

                    await self._send_message(sender_id, response)
                    print(f"[{self.id}] Sent corrections back to {sender_id}")

                self.processed_message_count = len(messages)

        await asyncio.sleep(1.5)

    async def _proofread(self, text: str) -> tuple[str, str]:
        """Proofread text using LLM and return corrected version with explanation.

        Args:
            text: Original text to proofread

        Returns:
            Tuple of (corrected_text, explanation_of_changes)

        """
        prompt = f"""You are a professional proofreader. Please proofread the following text and:
1. Correct any spelling, grammar, or punctuation errors
2. Improve clarity where needed
3. Return the corrected text followed by a brief list of changes made

Format your response as:
CORRECTED TEXT:
[corrected text here]

CHANGES:
- [change 1]
- [change 2]
etc.

TEXT TO PROOFREAD:
{text}"""

        try:
            response, _ = await generate(
                prompt,
                provider=self.llm_provider,
                model=self.llm_model,
                max_tokens=2000,
            )

            if "CORRECTED TEXT:" in response and "CHANGES:" in response:
                parts = response.split("CHANGES:")
                corrected = parts[0].replace("CORRECTED TEXT:", "").strip()
                explanation = parts[1].strip()
            else:
                corrected = text
                explanation = "- Unable to parse LLM response"

            return corrected, explanation
        except Exception as e:
            return text, f"- Error during proofreading: {str(e)}"

    async def _send_message(self, to_agent_id: str, content: str) -> None:
        """Send a message to another agent."""
        message = TextMessage(content=content)
        send_action = SendTextMessage(
            from_agent_id=self.id,
            to_agent_id=to_agent_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await self.execute_action(send_action)

        if result.is_error:
            print(f"[{self.id}] Failed to send: {result.content}")
