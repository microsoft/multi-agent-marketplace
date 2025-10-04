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
        priorities: str = "Good balance of price, quality, and reasonable turnaround time",
    ):
        """Initialize writer agent.

        Args:
            profile: Agent profile
            server_url: Marketplace server URL
            proofreader_ids: List of proofreader agent IDs
            text_to_proofread: Text content to send for proofreading
            llm_provider: LLM provider for decision making
            llm_model: LLM model for decision making
            priorities: Buyer's priorities for vendor selection

        """
        super().__init__(profile, server_url)
        self.proofreader_ids = proofreader_ids
        self.text_to_proofread = text_to_proofread
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.priorities = priorities
        self.initialized = False
        self.quotes_requested = False
        self.quotes_received = 0
        self.best_quote = None
        self.negotiation_sent = False
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

            print(f"Writer's priorities: {self.priorities}\n")

            # Show full quote request
            print(f"Writer's message:")
            print(f"{quote_request}\n")

            print(f"Broadcasting via SendTextMessage to {len(self.proofreader_ids)} agents:")
            for proofreader_id in self.proofreader_ids:
                print(f"  → SendTextMessage(to={proofreader_id})")
                await self._send_message(proofreader_id, quote_request)

            self.quotes_requested = True
            print()

        # Phase 2: Collect initial quotes
        if self.quotes_requested and not self.best_quote:
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

                    print(f"Received {len(quotes)} initial quotes via CheckMessages():\n")
                    for i, (agent_id, quote) in enumerate(quotes, 1):
                        print(f"{i}. [{agent_id}]")
                        print(f"{quote}\n")

                    print(f"DECISION: Using LLM to identify best quote based on priorities...")
                    print(f"Priorities: {self.priorities}\n")
                    self.best_quote = await self._select_best_quote(quotes, return_tuple=True)
                    print(f"RESULT: Best initial quote from {self.best_quote[0]}\n")

        # Phase 3: Negotiate with others
        if self.best_quote and not self.negotiation_sent:
            print(f"{'='*70}")
            print(f"PHASE 3: NEGOTIATE (1 → Many)")
            print(f"{'='*70}")
            print("ACTION: Writer shares best offer with other vendors")
            print("WHY: Enable price competition - others may beat the best quote\n")

            best_agent_id, best_quote_text = self.best_quote
            others = [pid for pid in self.proofreader_ids if pid != best_agent_id]

            negotiation_msg = await self._generate_negotiation_message(best_agent_id, best_quote_text)

            print(f"Negotiation message:")
            print(f"{negotiation_msg}\n")

            print(f"Sending negotiation via SendTextMessage to {len(others)} other vendors:")
            for other_id in others:
                print(f"  → SendTextMessage(to={other_id})")
                await self._send_message(other_id, negotiation_msg)

            self.negotiation_sent = True
            print()

        # Phase 4: Collect counter-offers and select final winner
        if self.negotiation_sent and not self.selected_proofreader:
            result = await self.execute_action(CheckMessages())

            if not result.is_error:
                messages = result.content.get("messages", [])
                # Initial quotes + expected counter-offers from non-winners
                best_agent_id = self.best_quote[0]
                others = [pid for pid in self.proofreader_ids if pid != best_agent_id]
                initial_count = len(self.proofreader_ids)
                expected_total = initial_count + len(others)  # 3 initial + 2 counter-offers = 5

                # Only proceed when we have all expected counter-offers
                if len(messages) >= expected_total:
                    print(f"{'='*70}")
                    print(f"PHASE 4: FINAL SELECTION (Many → 1)")
                    print(f"{'='*70}")
                    print("ACTION: Check for counter-offers from negotiation")
                    print("WHY: Vendors may reduce price to win the contract\n")

                    # Get messages after initial quotes
                    counter_offers = [(msg["from_agent_id"], msg["message"]["content"])
                                     for msg in messages[initial_count:]]

                    if counter_offers:
                        print(f"Received {len(counter_offers)} counter-offers:\n")
                        for i, (agent_id, offer) in enumerate(counter_offers, 1):
                            print(f"{i}. [{agent_id}]")
                            print(f"{offer}\n")

                        # Include best initial quote in final comparison
                        all_final_quotes = [self.best_quote] + counter_offers
                        print(f"DECISION: Comparing all offers based on priorities...")
                        print(f"Priorities: {self.priorities}\n")
                        self.selected_proofreader = await self._select_best_quote(all_final_quotes, return_tuple=False)
                        print(f"RESULT: Final winner is {self.selected_proofreader}\n")
                    else:
                        print("No counter-offers received. Selecting initial best bidder.\n")
                        self.selected_proofreader = self.best_quote[0]

        # Phase 5: Send task to winner
        if self.selected_proofreader and not self.task_sent:
            print(f"{'='*70}")
            print(f"PHASE 5: ASSIGN TASK (1 → 1)")
            print(f"{'='*70}")
            print("ACTION: Writer sends full document to winning bidder only")
            print("WHY: Negotiation complete - now execute the work\n")
            print(f"SendTextMessage(to={self.selected_proofreader})")
            print(f"  Payload: {len(self.text_to_proofread)} chars (full document - not shown)\n")
            await self._send_message(self.selected_proofreader, self.text_to_proofread)
            self.task_sent = True

        # Phase 6: Collect result
        if self.task_sent and not self.result_received:
            result = await self.execute_action(CheckMessages())

            if not result.is_error:
                messages = result.content.get("messages", [])
                for msg in messages:
                    if msg["from_agent_id"] == self.selected_proofreader and "CHANGES:" in msg["message"]["content"]:
                        print(f"{'='*70}")
                        print(f"PHASE 6: RECEIVE RESULT (1 → 1)")
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
- Buyer's priorities: {self.priorities}
- Need: Price quote, quality estimate, and turnaround time

Start with "Hello," and sign from {self.id}. Keep it professional and under 120 words."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=200,
        )
        return response.strip()

    async def _select_best_quote(self, quotes: list[tuple[str, str]], return_tuple: bool = False) -> tuple[str, str] | str:
        """Use LLM to parse quotes and select the best quality/price ratio.

        Args:
            quotes: List of (agent_id, quote_text) tuples
            return_tuple: If True, return (agent_id, quote_text). If False, return just agent_id.

        Returns:
            tuple of (agent_id, quote_text) if return_tuple=True, else just agent_id string
        """
        quotes_text = "\n\n".join([f"From {agent_id}:\n{quote}" for agent_id, quote in quotes])

        prompt = f"""You are selecting the best proofreading service for a buyer.

Buyer's priorities: {self.priorities}

Here are the quotes:
{quotes_text}

Analyze each quote for:
1. Price (lower is better)
2. Quality rating (higher is better)
3. Turnaround time (faster may be valuable)
4. Other factors (revisions, service level)

Select the vendor that BEST MATCHES the buyer's stated priorities.
The buyer's priorities should guide your decision - if they value speed, pick faster option even if pricier.

Return ONLY the agent ID of the best choice (e.g., "proofreader-gpt4o-123"). Nothing else."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=100,
        )
        best_agent_id = response.strip()

        if return_tuple:
            # Find and return the quote text too
            for agent_id, quote_text in quotes:
                if agent_id == best_agent_id:
                    return (best_agent_id, quote_text)
            # Fallback if not found
            return (best_agent_id, quotes[0][1])

        return best_agent_id

    async def _generate_negotiation_message(self, best_agent_id: str, best_quote: str) -> str:
        """Generate a negotiation message to send to other vendors."""
        prompt = f"""You are {self.id}. You received a quote from {best_agent_id}.

Their quote:
{best_quote}

Extract their FULL OFFER (price, turnaround time, quality, and extras) and write a negotiation message to OTHER vendors.

Your message MUST:
1. State the complete offer to beat from {best_agent_id} (not just price - include turnaround, quality, extras)
2. Ask if they can provide a better overall value (could be: lower price, faster delivery, higher quality, or add-ons)
3. Mention this is their final chance to compete

Do NOT use placeholder names. Keep under 100 words. Sign from {self.id}."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=150,
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

                    # Use LLM to determine message type
                    message_type = await self._interpret_message(text)

                    if message_type == "quote_request":
                        print(f"\n[{self.id}] Received message via CheckMessages():")
                        print(f"  From: {sender_id}")
                        print(f"  Type: Quote request (LLM interpreted)\n")
                        print(f"Message content:")
                        print(f"{text}\n")

                        print(f"Generating quote using {self.llm_model}...")
                        quote = await self._generate_quote(text)
                        print(f"→ Sending quote via SendTextMessage(to={sender_id})\n")
                        await self._send_message(sender_id, quote)
                    elif message_type == "negotiation":
                        print(f"\n[{self.id}] Received message via CheckMessages():")
                        print(f"  From: {sender_id}")
                        print(f"  Type: Negotiation request (LLM interpreted)\n")
                        print(f"Message content:")
                        print(f"{text}\n")

                        print(f"Considering counter-offer using {self.llm_model}...")
                        counter_offer = await self._generate_counter_offer(text)
                        print(f"→ Sending counter-offer via SendTextMessage(to={sender_id})\n")
                        await self._send_message(sender_id, counter_offer)
                    else:
                        # Actual proofreading task
                        print(f"\n[{self.id}] Received message via CheckMessages():")
                        print(f"  From: {sender_id}")
                        print(f"  Type: Work assignment (LLM interpreted)")
                        print(f"  Size: {len(text)} chars (full document - not shown)\n")

                        print(f"Processing task with {self.llm_model}...")
                        corrected, explanation = await self._proofread(text)
                        response = f"[{self.llm_model}]\n\nCHANGES:\n{explanation}"

                        print(f"→ Sending result via SendTextMessage(to={sender_id})\n")
                        await self._send_message(sender_id, response)

                self.processed_message_count = len(messages)

        await asyncio.sleep(1.5)

    async def _interpret_message(self, text: str) -> str:
        """Use LLM to determine message type."""
        prompt = f"""Analyze this message type:

{text[:200]}...

Is this:
- "quote_request": Initial request for a price quote
- "negotiation": Follow-up asking to beat another offer
- "task": Actual work (full document to proofread)

Respond with ONLY one word: quote_request, negotiation, or task."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=10,
        )
        return response.strip().lower()

    async def _generate_quote(self, request_text: str) -> str:
        """Use LLM to generate a price quote based on model capabilities."""
        # Define service tiers with realistic constraints
        if self.llm_model == "gpt-4o":
            service_params = "Price: $350 | Turnaround: 24 hours | Quality: 9/10 | Includes: 1 revision round"
        elif self.llm_model == "gpt-4o-mini":
            service_params = "Price: $150 | Turnaround: 48 hours | Quality: 10/10 | Includes: Basic proofreading"
        else:  # gemini
            service_params = "Price: $80 | Turnaround: 72 hours | Quality: 10/10 | Includes: Standard service"

        prompt = f"""You are {self.id}, a proofreading service using {self.llm_model}.

Quote request:
{request_text}

Generate a professional quote with these parameters:
{service_params}

Include: price, turnaround time, quality rating, and what's included.
Do NOT use placeholder names. Keep under 90 words. Sign from {self.id}."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=150,
        )
        return response.strip()

    async def _generate_counter_offer(self, negotiation_text: str) -> str:
        """Generate a counter-offer in response to negotiation."""
        if self.llm_model == "gpt-4o":
            counter_params = """Your original: $350, 24hr, quality 9/10, includes 1 revision

Counter-offer options (choose ONE creative trade-off):
1. Same $350 but add 2nd revision + faster 18hr delivery (MORE value at same price)
2. Reduce to $280 by extending to 36hr (trade time for price)
3. Keep $350, 24hr but upgrade quality to 10/10 (premium positioning)

Pick the option that best counters the competing offer. Explain your value proposition."""
        elif self.llm_model == "gpt-4o-mini":
            counter_params = """Your original: $150, 48hr, quality 10/10

Counter-offer options (choose ONE):
1. Reduce to $130 with same 48hr, quality 10/10 (price reduction)
2. Keep $150 but deliver in 36hr instead of 48hr (faster for same price)
3. Keep $150, 48hr but add 1 free revision round (more value)

Pick what best competes with the other offer."""
        else:  # gemini
            counter_params = """Your original: $80, 72hr, quality 10/10

Counter-offer options (choose ONE):
1. Keep $80 but deliver in 60hr instead of 72hr (faster for same price)
2. Keep $80, 72hr but add a formatting check (extra value)
3. Reduce to $75 but note this is absolute minimum

Pick what makes you competitive while staying profitable."""

        prompt = f"""You are {self.id} using {self.llm_model}.

Negotiation message:
{negotiation_text}

{counter_params}

Write a realistic counter-offer. You can compete on price, speed, quality, OR extras.
Clearly state: price, turnaround time, quality, and what's included.
Do NOT use placeholder names. Keep under 100 words. Sign from {self.id}."""

        response, _ = await generate(
            prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            max_tokens=120,
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
