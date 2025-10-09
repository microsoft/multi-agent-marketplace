"""Prompt generation for the business agent."""

from datetime import datetime

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
        self, conversation_history: str, context: str = ""
    ) -> str:
        """Format the prompt for generating responses to customer inquiries.

        Args:
            conversation_history: convo history as string
            context: Additional context for the prompt

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
        menu_block = (
            "\n".join(
                f"  - {item_name}: ${price:.2f}"
                for item_name, price in sorted(self.business.menu_features.items())
            )
            if self.business.menu_features
            else "  - (none listed)"
        )

        # Build business info with comprehensive structure
        business_info_parts = [f"- Name: {self.business.name}"]
        business_info_parts.append(f"- Rating: {self.business.rating:.1f}/1.0")
        business_info_parts.append(f"- Description: {self.business.description}")
        business_info_parts.append(f"- Delivery available: {delivery_available}")

        business_info = "\n".join(business_info_parts)

        # Get current date and time
        now = datetime.now()
        current_date = now.strftime("%B %d, %Y")
        current_time = now.strftime("%I:%M%p").lower()

        prompt = f"""Current Date: {current_date}
Current Time: {current_time}

You are a business owner responding to a customer inquiry. Be helpful, professional, and try to make a sale.

Your business:
{business_info}
- Amenities provided by your business:
{features_block}
- Menu items and prices:
{menu_block}
ONLY tell potential customers what you have on the menu with CORRECT PRICES.

Conversation so far:
{conversation_history}

Context: {context}

Generate a BusinessAction with:
- action_type: "text" for general inquiries/questions, "order_proposal" for creating structured proposals
- content: Either a string (for text responses) or OrderProposal object (for proposals)

CREATING ORDER PROPOSALS:
When customers show interest in purchasing (asking about prices, availability, wanting to order),
PREFER creating order_proposal over text responses:

1. Use action_type="order_proposal" when:
   - Customer expresses interest in purchasing specific items
   - You can create a concrete proposal with items, quantities, and prices
   - Customer is asking "how much for..." or "I want to order..."
   - You want to move the conversation toward a purchase

2. The content should be an OrderProposal with:
   - items: list of OrderItem with correct item names and prices from your menu
   - total_price: sum of all items
   - special_instructions: any relevant notes
   - estimated_delivery: time estimate if applicable

DECISION PRIORITY:
1. If customer wants to purchase specific items: use action_type="order_proposal"
2. For general inquiries: use action_type="text"

REMEMBER: Order proposals let you actively shape the transaction instead of just responding to customer orders!"""

        return prompt
