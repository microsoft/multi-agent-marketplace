"""Example agents that use the text-only protocol."""

import asyncio
from datetime import UTC, datetime

from magentic_marketplace.platform.agent.base import BaseAgent
from magentic_marketplace.platform.shared.models import AgentProfile

from cookbook.text_only_protocol.actions import CheckMessages, SendTextMessage
from cookbook.text_only_protocol.messaging import TextMessage


class ChatAgent(BaseAgent[AgentProfile]):
    """Simple agent that sends and receives messages."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        peer_id: str,
        messages_to_send: int = 2,
        send_first: bool = False,
    ):
        """Initialize chat agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            peer_id: ID of the peer agent to chat with
            messages_to_send: Number of messages to send
            send_first: Whether to send first message immediately

        """
        super().__init__(profile, server_url)
        self.peer_id = peer_id
        self.messages_to_send = messages_to_send
        self.send_first = send_first
        self.sent_count = 0
        self.last_message_count = 0
        self.initialized = False

    async def step(self) -> None:
        """Send messages and check for new ones."""
        if not self.initialized:
            await asyncio.sleep(1)
            self.initialized = True

            # Resolve peer ID from registered agents
            agents_response = await self.client.agents.list(limit=100)
            for agent in agents_response.items:
                if agent.id.startswith(self.peer_id) and agent.id != self.id:
                    self.peer_id = agent.id
                    break

            if self.send_first and self.sent_count < self.messages_to_send:
                await self._send_message(
                    f"Hi {self.peer_id}, this is {self.id}! (message {self.sent_count + 1})"
                )
                self.sent_count += 1

        result = await self.execute_action(CheckMessages())

        if not result.is_error:
            messages = result.content.get("messages", [])
            if len(messages) > self.last_message_count:
                new_messages = messages[self.last_message_count :]
                for msg in new_messages:
                    sender_id = msg["from_agent_id"]
                    content = msg["message"]["content"]
                    print(f"[{self.id}] Received from {sender_id}: {content}")

                    if self.sent_count < self.messages_to_send:
                        response = f"Thanks! Here's my message {self.sent_count + 1}"
                        await self._send_message(response)
                        self.sent_count += 1

                self.last_message_count = len(messages)

        await asyncio.sleep(1.5)

    async def _send_message(self, content: str) -> None:
        """Send a message to peer agent."""
        message = TextMessage(content=content)
        send_action = SendTextMessage(
            from_agent_id=self.id,
            to_agent_id=self.peer_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await self.execute_action(send_action)

        if result.is_error:
            print(f"[{self.id}] Failed to send: {result.content}")
        else:
            print(f"[{self.id}] Sent: {content}")
