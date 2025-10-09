"""Prompt generation for the business agent."""

from magentic_marketplace.platform.logger import MarketplaceLogger

from ...shared.models import Business


class PromptsHandler:
    """Handles prompt generation for the business agent."""

    def __init__(
        self,
        business: Business,
        logger: MarketplaceLogger,
    ):
        """Initialize the prompts handler.

        Args:
            business: Business data
            logger: Logger instance

        """
        self.business = business
        self.logger = logger

    def format_response_prompt(
        self,
        conversation_history: list[str],
        customer_id: str,
        context: str | None = None,
    ) -> str:
        """Format the prompt for generating responses to customer inquiries.

        Args:
            conversation_history: convo history as string
            customer_id: the customer id
            context: extra context with error or instructions

        Returns:
            Formatted prompt for LLM

        """
        # Derive delivery availability from amenity features
        delivery_available = (
            "Yes" if self.business.amenity_features.get("delivery", False) else "No"
        )

        # Format amenity features for the prompt
        features_block = (
            "\n".join(
                f"  - {k}: {'Yes' if v else 'No'}"
                for k, v in sorted(self.business.amenity_features.items())
            )
            if self.business.amenity_features
            else "  - (none)"
        )

        # Format menu items for the prompt
        menu_lines: list[str] = []
        for item_name, price in self.business.menu_features.items():
            item_id = len(menu_lines) + 1
            menu_lines.append(f"  - Item-{item_id}: {item_name} - ${price:.2f}")

        if not menu_lines:
            menu_lines.append("  - (none listed)")

        # Sorted to match (incorrect, i.e. [1, 10, 11, 2]) sorting from v1
        menu_block = "\n".join(sorted(menu_lines))

        # Build business info with comprehensive structure
        business_info_parts = [f"- Name: {self.business.name}"]
        business_info_parts.append(f"- Rating: {self.business.rating:.1f}/1.0")
        business_info_parts.append(f"- Description: {self.business.description}")
        business_info_parts.append("- Hours: Unknown")
        business_info_parts.append(f"- Delivery available: {delivery_available}")

        business_info = "\n".join(business_info_parts)

        last_message = conversation_history[-1] if conversation_history else ""
        earlier_conversation_history = (
            "\n".join(conversation_history[:-1])
            if len(conversation_history) > 1
            else ""
        )
        if context is None:
            context = "Customer is making an inquiry. Use text action to respond, or create an order_proposal if they want to purchase something specific."

        # Get current date and time
        prompt = f"""You are a business owner responding to a customer inquiry. Be helpful, professional, and try to make a sale.

Your business:
{business_info}
- Amenities provided by your business:
{features_block}
- Menu items and prices:
{menu_block}
ONLY tell potential customers what you have on the menu with CORRECT PRICES.

Conversation so far:
{earlier_conversation_history}

Customer just said: "{last_message}"

Context: {context}

Generate a BusinessAction with:
- action_type: "text" for general inquiries/questions, "order_proposal" for creating structured proposals
- text_message: ServiceTextMessageRequest (if action_type is "text")
- order_proposal_message: ServiceOrderProposalMessageRequest (if action_type is "order_proposal")

For all message types, use:
- to_customer_id: {customer_id}
- type: Must match the action_type
- content: Appropriate response content (string for text, OrderProposal for order_proposal)


CREATING ORDER PROPOSALS:
When customers show interest in purchasing (asking about prices, availability, wanting to order),
PREFER creating order_proposal over text responses:

1. Use action_type="order_proposal" when:
   - Customer expresses interest in purchasing specific items
   - You can create a concrete proposal with items, quantities, and prices
   - Customer is asking "how much for..." or "I want to order..."
   - You want to move the conversation toward a purchase

2. The order_proposal_message should contain OrderProposal with:
   - items: list of OrderItem with id (use the menu item ID like "Item-1"), item_name, quantity, unit_price from your menu
   - total_price: sum of all items
   - special_instructions: any relevant notes
   - estimated_delivery: time estimate if applicable

DECISION PRIORITY:
1. If customer wants to purchase specific items: use action_type="order_proposal"
2. For general inquiries: use action_type="text"

REMEMBER: Order proposals let you actively shape the transaction instead of just responding to customer orders!"""

        return prompt
