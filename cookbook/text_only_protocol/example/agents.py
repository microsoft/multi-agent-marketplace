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
            print(f"PHASE 1: REQUEST QUOTES")
            print(f"{'='*70}")
            print(f"[{self.id}] Generated quote request:")
            print(f"  {quote_request[:100].replace(chr(10), ' ')}...")
            print()

            for proofreader_id in self.proofreader_ids:
                print(f"[{self.id}] → Sending quote request to {proofreader_id}")
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
                    print(f"PHASE 2: EVALUATE QUOTES")
                    print(f"{'='*70}")
                    quotes = [(msg["from_agent_id"], msg["message"]["content"]) for msg in messages]

                    for agent_id, quote in quotes:
                        preview = quote[:80].replace('\n', ' ')
                        print(f"[{self.id}] ← Received quote from {agent_id}:")
                        print(f"  {preview}...")

                    print(f"\n[{self.id}] Using LLM to select best quality/price ratio...")
                    self.selected_proofreader = await self._select_best_quote(quotes)
                    print(f"[{self.id}] ✓ Selected: {self.selected_proofreader}\n")

        # Phase 3: Send task to winner
        if self.selected_proofreader and not self.task_sent:
            print(f"{'='*70}")
            print(f"PHASE 3: ASSIGN TASK")
            print(f"{'='*70}")
            print(f"[{self.id}] → Sending {len(self.text_to_proofread)} chars to {self.selected_proofreader}")
            await self._send_message(self.selected_proofreader, self.text_to_proofread)
            self.task_sent = True
            print()

        # Phase 4: Collect result
        if self.task_sent and not self.result_received:
            result = await self.execute_action(CheckMessages())

            if not result.is_error:
                messages = result.content.get("messages", [])
                for msg in messages:
                    if msg["from_agent_id"] == self.selected_proofreader and "CORRECTED TEXT" in msg["message"]["content"]:
                        print(f"{'='*70}")
                        print(f"PHASE 4: RECEIVE RESULT")
                        print(f"{'='*70}")
                        print(f"[{self.id}] ← Received proofreading result from {self.selected_proofreader}")
                        print(f"  Result length: {len(msg['message']['content'])} chars\n")
                        self.result_received = True
                        # Shutdown the agent - work is complete
                        self.shutdown()
                        break

        await asyncio.sleep(1.5)

    async def _generate_quote_request(self) -> str:
        """Use LLM to generate a quote request message."""
        prompt = f"""You are a writer agent requesting proofreading quotes. Generate a brief quote request message that includes:
- The task: proofreading a document
- Text length: {len(self.text_to_proofread)} characters
- What you need back: price quote and quality estimate

Keep the message concise and professional."""

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
                        print(f"[{self.id}] ← Received quote request from {sender_id}")
                        quote = await self._generate_quote(text)
                        print(f"[{self.id}] → Sending quote to {sender_id}:")
                        print(f"  {quote[:80].replace(chr(10), ' ')}...")
                        await self._send_message(sender_id, quote)
                    else:
                        # Actual proofreading task
                        print(f"[{self.id}] ← Received {len(text)} chars task from {sender_id}")
                        print(f"[{self.id}] Proofreading with {self.llm_model}...")

                        corrected, explanation = await self._proofread(text)
                        response = f"[{self.llm_model}]\n\nCORRECTED TEXT:\n{corrected}\n\nCHANGES:\n{explanation}"

                        print(f"[{self.id}] → Sending corrections to {sender_id}")
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
        prompt = f"""You are a proofreading service powered by {self.llm_model}.

Quote Request: {request_text}

Generate a professional quote response that includes:
1. Your price (consider: {self.llm_model} tier - gpt-4o is premium, gpt-4o-mini is budget, gemini is mid-tier)
2. Your quality estimate (1-10 scale, based on your model's capability)
3. Brief explanation of value

Keep it concise (2-3 sentences)."""

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
