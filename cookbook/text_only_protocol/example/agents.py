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
    """Agent that sends text for proofreading."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        proofreader_id: str,
        text_to_proofread: str,
    ):
        """Initialize writer agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            proofreader_id: ID of the proofreader agent
            text_to_proofread: Text content to send for proofreading

        """
        super().__init__(profile, server_url)
        self.proofreader_id = proofreader_id
        self.text_to_proofread = text_to_proofread
        self.initialized = False
        self.text_sent = False
        self.received_correction = False

    async def step(self) -> None:
        """Send text and wait for corrections."""
        if not self.initialized:
            await asyncio.sleep(1)
            self.initialized = True

            agents_response = await self.client.agents.list(limit=100)
            for agent in agents_response.items:
                if agent.id.startswith(self.proofreader_id) and agent.id != self.id:
                    self.proofreader_id = agent.id
                    break

        if not self.text_sent:
            preview = self.text_to_proofread[:80] + "..." if len(self.text_to_proofread) > 80 else self.text_to_proofread
            print(f"[{self.id}] Sending text for proofreading: {preview}")
            await self._send_message(self.text_to_proofread)
            self.text_sent = True

        result = await self.execute_action(CheckMessages())

        if not result.is_error and not self.received_correction:
            messages = result.content.get("messages", [])
            if messages:
                for msg in messages:
                    content = msg["message"]["content"]
                    preview = content[:80] + "..." if len(content) > 80 else content
                    print(f"[{self.id}] Received correction: {preview}")
                self.received_correction = True

        await asyncio.sleep(1.5)

    async def _send_message(self, content: str) -> None:
        """Send a message to proofreader."""
        message = TextMessage(content=content)
        send_action = SendTextMessage(
            from_agent_id=self.id,
            to_agent_id=self.proofreader_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await self.execute_action(send_action)

        if result.is_error:
            print(f"[{self.id}] Failed to send: {result.content}")


class ProofreaderAgent(BaseAgent[AgentProfile]):
    """Agent that receives text, corrects it, and explains changes."""

    def __init__(self, profile: AgentProfile, server_url: str):
        """Initialize proofreader agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL

        """
        super().__init__(profile, server_url)
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

                    preview = text[:80] + "..." if len(text) > 80 else text
                    print(f"[{self.id}] Received text from {sender_id}: {preview}")
                    print(f"[{self.id}] Proofreading with LLM...")

                    corrected, explanation = await self._proofread(text)
                    response = f"CORRECTED TEXT:\n{corrected}\n\nCHANGES:\n{explanation}"

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
            response, _ = await generate(prompt, max_tokens=2000)

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
