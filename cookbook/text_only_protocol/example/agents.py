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
    """Agent that requests quotes and selects best proofreader using LLM."""

    def __init__(
        self,
        profile: AgentProfile,
        server_url: str,
        proofreader_ids: list[str],
        text_to_proofread: str,
        llm_provider: str,
        llm_model: str,
    ):
        """Initialize writer agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            proofreader_ids: List of proofreader agent IDs
            text_to_proofread: Text content to send for proofreading
            llm_provider: LLM provider for decision making
            llm_model: LLM model for decision making

        """
        super().__init__(profile, server_url)
        self.proofreader_ids = proofreader_ids
        self.text_to_proofread = text_to_proofread
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.initialized = False
        self.quotes_requested = False
        self.quotes_received = 0
        self.selected_proofreader = None
        self.task_sent = False
        self.result_received = False

    async def step(self) -> None:
        """Request quotes, select best, send task to winner."""
        if not self.initialized:
            await asyncio.sleep(1)
            self.initialized = True

            # Resolve proofreader IDs
            agents_response = await self.client.agents.list(limit=100)
            resolved_ids = []
            for proofreader_prefix in self.proofreader_ids:
                for agent in agents_response.items:
                    if agent.id.startswith(proofreader_prefix) and agent.id != self.id:
                        resolved_ids.append(agent.id)
                        break
            self.proofreader_ids = resolved_ids

        # Phase 1: Request quotes
        if not self.quotes_requested:
            quote_request = await self._generate_quote_request()
            print(f"\n{'='*70}")
            print(f"PHASE 1: BROADCAST REQUEST (1 → Many)")
            print(f"{'='*70}")
            print("ACTION: Writer sends the same message to multiple agents")
            print("WHY: Enables competitive marketplace - multiple vendors can bid\n")

            # Show quote request with reasonable truncation
            display_text = quote_request if len(quote_request) <= 300 else quote_request[:300] + "..."
            print(f"Writer's message:")
            print(f"{display_text}\n")

            print(f"Broadcasting via SendTextMessage to {len(self.proofreader_ids)} agents:")
            for proofreader_id in self.proofreader_ids:
                print(f"  → SendTextMessage(to={proofreader_id})")
                await self._send_message(proofreader_id, quote_request)

            self.quotes_requested = True
            print()

        # Phase 2: Collect quotes and select winner
        if self.quotes_requested and not self.selected_proofreader:
            result = await self.execute_action(CheckMessages())

            if not result.is_error:
                messages = result.content.get("messages", [])
                if len(messages) >= len(self.proofreader_ids):
                    print(f"{'='*70}")
                    print(f"PHASE 2: COLLECT BIDS (Many → 1)")
                    print(f"{'='*70}")
                    print("ACTION: Writer retrieves all responses with single CheckMessages call")
                    print("WHY: Protocol auto-stores messages - no need to query each agent\n")

                    quotes = [(msg["from_agent_id"], msg["message"]["content"]) for msg in messages]

                    print(f"Received {len(quotes)} quotes via CheckMessages():\n")
                    for i, (agent_id, quote) in enumerate(quotes, 1):
                        display_quote = quote if len(quote) <= 200 else quote[:200] + "..."
                        print(f"{i}. [{agent_id}]")
                        print(f"   {display_quote}\n")

                    print("DECISION: Using LLM to evaluate quality/price ratio...")
                    self.selected_proofreader = await self._select_best_quote(quotes)
                    print(f"RESULT: Selected {self.selected_proofreader}\n")

        # Phase 3: Send task to winner
        if self.selected_proofreader and not self.task_sent:
            print(f"{'='*70}")
            print(f"PHASE 3: ASSIGN TASK (1 → 1)")
            print(f"{'='*70}")
            print("ACTION: Writer sends full document to winning bidder only")
            print("WHY: Market selected best vendor - now execute the work\n")
            print(f"SendTextMessage(to={self.selected_proofreader})")
            print(f"  Payload: {len(self.text_to_proofread)} character document\n")
            await self._send_message(self.selected_proofreader, self.text_to_proofread)
            self.task_sent = True

        # Phase 4: Collect result
        if self.task_sent and not self.result_received:
            result = await self.execute_action(CheckMessages())

            if not result.is_error:
                messages = result.content.get("messages", [])
                for msg in messages:
                    if msg["from_agent_id"] == self.selected_proofreader and "CHANGES:" in msg["message"]["content"]:
                        print(f"{'='*70}")
                        print(f"PHASE 4: RECEIVE RESULT (1 → 1)")
                        print(f"{'='*70}")
                        print("ACTION: Writer checks for completion message from winner")
                        print("WHY: Winner sends result back via same message protocol\n")

                        result_text = msg['message']['content']

                        # Extract and show the changes (more useful than full corrected text)
                        if "CHANGES:" in result_text:
                            changes = result_text.split("CHANGES:")[1].strip()
                            display_changes = changes if len(changes) <= 300 else changes[:300] + "..."
                            print(f"CheckMessages() returned completion from {self.selected_proofreader}:")
                            print(f"{display_changes}\n")
                            print("MARKETPLACE TRANSACTION COMPLETE")

                        self.result_received = True
                        self.shutdown()
                        break

        await asyncio.sleep(1.5)

    async def _generate_quote_request(self) -> str:
        """Use LLM to generate a quote request message."""
        prompt = f"""Write a quote request from {self.id} for proofreading services.

Do NOT use placeholder names like [Name] or [Recipient's Name].

Include:
- Task: Proofread a document
- Size: {len(self.text_to_proofread)} characters
- Need: Price quote and quality estimate

Start with "Hello," and sign from {self.id}. Keep it professional and under 100 words."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=200,
        )
        return response.strip()

    async def _select_best_quote(self, quotes: list[tuple[str, str]]) -> str:
        """Use LLM to parse quotes and select the best quality/price ratio."""
        quotes_text = "\n\n".join([f"From {agent_id}:\n{quote}" for agent_id, quote in quotes])

        prompt = f"""You are selecting the best proofreading service based on quality/price ratio.

Here are the quotes:
{quotes_text}

Analyze each quote for:
1. Price (lower is better)
2. Quality estimate (higher is better)
3. Calculate quality/price ratio

Return ONLY the agent ID of the best choice (e.g., "proofreader-gpt4o-123"). Nothing else."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=100,
        )
        return response.strip()

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
        """Check for messages and respond appropriately."""
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

                    # Use LLM to determine if this is a quote request or actual task
                    message_type = await self._interpret_message(text)

                    if message_type == "quote_request":
                        display_request = text if len(text) <= 200 else text[:200] + "..."
                        print(f"\n[{self.id}] Received message via CheckMessages():")
                        print(f"  From: {sender_id}")
                        print(f"  Type: Quote request (LLM interpreted)\n")
                        print(f"Message content:")
                        print(f"{display_request}\n")

                        print(f"Generating quote using {self.llm_model}...")
                        quote = await self._generate_quote(text)
                        print(f"→ Sending quote via SendTextMessage(to={sender_id})\n")
                        await self._send_message(sender_id, quote)
                    else:
                        # Actual proofreading task
                        print(f"\n[{self.id}] Received message via CheckMessages():")
                        print(f"  From: {sender_id}")
                        print(f"  Type: Work assignment (LLM interpreted)")
                        print(f"  Size: {len(text)} chars\n")

                        print(f"Processing task with {self.llm_model}...")
                        corrected, explanation = await self._proofread(text)
                        response = f"[{self.llm_model}]\n\nCHANGES:\n{explanation}"

                        print(f"→ Sending result via SendTextMessage(to={sender_id})\n")
                        await self._send_message(sender_id, response)

                self.processed_message_count = len(messages)

        await asyncio.sleep(1.5)

    async def _interpret_message(self, text: str) -> str:
        """Use LLM to determine if message is a quote request or actual task."""
        prompt = f"""You are analyzing a message to determine its type.

Message: {text[:200]}...

Is this a QUOTE REQUEST (asking for a price quote) or an ACTUAL TASK (the full text to proofread)?

Respond with ONLY one word: "quote_request" or "task"."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=10,
        )
        return response.strip().lower()

    async def _generate_quote(self, request_text: str) -> str:
        """Use LLM to generate a price quote based on model capabilities."""
        prompt = f"""You are {self.id}, a proofreading service using {self.llm_model}.

Quote request:
{request_text}

Write a quote response. Do NOT use placeholder names like [Your Name] or [Recipient's Name].

Include:
1. Price (gpt-4o=$300-400, gpt-4o-mini=$100-200, gemini=$50-100)
2. Quality rating 1-10 (gpt-4o=9-10, gpt-4o-mini=7-8, gemini=8-9)
3. Brief value statement

Sign from {self.id}. Keep under 80 words."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=150,
        )
        return response.strip()

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
3. Return the corrected text followed by a brief list of suggested changes

Format your response as:

CHANGES:
- [suggested change 1]
- [suggested change 2]
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
