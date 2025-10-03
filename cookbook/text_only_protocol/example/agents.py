"""Example agents that use the text-only protocol."""

import asyncio
from datetime import UTC, datetime

from magentic_marketplace.platform.agent.base import BaseAgent
from magentic_marketplace.platform.shared.models import AgentProfile

from cookbook.text_only_protocol.actions import CheckMessages, SendTextMessage
from cookbook.text_only_protocol.messaging import TextMessage


class GreeterAgent(BaseAgent[AgentProfile]):
    """Agent that sends greeting messages to other agents."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        target_agent_id: str,
        message_count: int = 3,
    ):
        """Initialize greeter agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            target_agent_id: ID prefix of agent to send messages to (will be resolved to actual ID)
            message_count: Number of messages to send

        """
        super().__init__(profile, server_url)
        self.target_agent_id_prefix = target_agent_id
        self.target_agent_id = None  # Will be resolved on first send
        self.message_count = message_count
        self.messages_sent = 0

    async def step(self) -> None:
        """Send a greeting message if quota not reached."""
        # Resolve target agent ID on first step
        if self.messages_sent == 0 and self.target_agent_id is None:
            await asyncio.sleep(1.5)  # Give other agents time to register

            # Look up the actual registered agent ID
            agents_response = await self.client.agents.list(limit=100)
            for agent in agents_response.items:
                if agent.id.startswith(self.target_agent_id_prefix):
                    self.target_agent_id = agent.id
                    break

            if not self.target_agent_id:
                print(
                    f"[{self.id}] Could not find target agent with prefix '{self.target_agent_id_prefix}'"
                )
                return

        if self.messages_sent >= self.message_count:
            return

        message = TextMessage(
            content=f"Hello from {self.id}! (message {self.messages_sent + 1})"
        )

        send_action = SendTextMessage(
            from_agent_id=self.id,
            to_agent_id=self.target_agent_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await self.execute_action(send_action)

        if result.is_error:
            print(f"[{self.id}] Failed to send message: {result.content}")
        else:
            self.messages_sent += 1
            print(f"[{self.id}] Sent: {message.content}")

        await asyncio.sleep(1)


class ReaderAgent(BaseAgent[AgentProfile]):
    """Agent that periodically checks and prints received messages."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        check_interval: float = 2.0,
    ):
        """Initialize reader agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            check_interval: Seconds between message checks

        """
        super().__init__(profile, server_url)
        self.check_interval = check_interval
        self.last_message_count = 0

    async def step(self) -> None:
        """Check for new messages and print them."""
        check_action = CheckMessages()

        result = await self.execute_action(check_action)

        if result.is_error:
            print(f"[{self.id}] Failed to check messages: {result.content}")
            return

        messages = result.content.get("messages", [])

        if len(messages) > self.last_message_count:
            new_messages = messages[self.last_message_count :]
            for msg in new_messages:
                print(
                    f"[{self.id}] Received from {msg['from_agent_id']}: {msg['message']['content']}"
                )
            self.last_message_count = len(messages)

        await asyncio.sleep(self.check_interval)


class ConversationAgent(BaseAgent[AgentProfile]):
    """Agent that both sends and receives messages."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        peer_agent_id: str,
        initial_message: str | None = None,
    ):
        """Initialize conversation agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            peer_agent_id: ID prefix of agent to converse with (will be resolved to actual ID)
            initial_message: Optional message to send at start

        """
        super().__init__(profile, server_url)
        self.peer_agent_id_prefix = peer_agent_id
        self.peer_agent_id = None  # Will be resolved when needed
        self.initial_message = initial_message
        self.sent_initial = False
        self.last_message_count = 0
        self.response_count = 0
        self.max_responses = 3

    async def _resolve_peer_id(self) -> bool:
        """Resolve the peer agent's actual registered ID.

        Returns:
            True if peer was found, False otherwise

        """
        if self.peer_agent_id:
            return True

        agents_response = await self.client.agents.list(limit=100)
        for agent in agents_response.items:
            if agent.id.startswith(self.peer_agent_id_prefix) and agent.id != self.id:
                self.peer_agent_id = agent.id
                return True

        print(
            f"[{self.id}] Could not find peer agent with prefix '{self.peer_agent_id_prefix}'"
        )
        return False

    async def step(self) -> None:
        """Check for messages and respond to them."""
        if not self.sent_initial and self.initial_message:
            # Give other agents time to register
            await asyncio.sleep(1.5)

            # Resolve peer agent ID
            if not await self._resolve_peer_id():
                return

            await self._send_message(self.initial_message)
            self.sent_initial = True
            await asyncio.sleep(1)
            return

        check_action = CheckMessages()
        result = await self.execute_action(check_action)

        if result.is_error:
            print(f"[{self.id}] Error checking messages: {result.content}")
            return

        messages = result.content.get("messages", [])

        if (
            len(messages) > self.last_message_count
            and self.response_count < self.max_responses
        ):
            # Resolve peer ID if we haven't yet
            if not await self._resolve_peer_id():
                return

            new_messages = messages[self.last_message_count :]
            for msg in new_messages:
                content = msg["message"]["content"]
                print(f"[{self.id}] Received: {content}")

                response = f"Thanks for your message! (reply {self.response_count + 1})"
                await self._send_message(response)
                self.response_count += 1

            self.last_message_count = len(messages)

        await asyncio.sleep(2)

    async def _send_message(self, content: str) -> None:
        """Send a message to peer agent.

        Args:
            content: Message content

        """
        message = TextMessage(content=content)
        send_action = SendTextMessage(
            from_agent_id=self.id,
            to_agent_id=self.peer_agent_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await self.execute_action(send_action)

        if result.is_error:
            print(f"[{self.id}] Failed to send: {result.content}")
        else:
            print(f"[{self.id}] Sent: {content}")
