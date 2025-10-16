export interface Customer {
  id: string;
  name: string;
  user_request: string;
  menu_features: Record<string, number>;
  amenity_features: string[];
}

export interface Business {
  id: string;
  name: string;
  rating: number;
  price_min: number;
  price_max: number;
  description: string;
  menu_features: Record<string, number>;
  amenity_features: Record<string, boolean>;
}

export interface OrderItem {
  id: string;
  item_name: string;
  quantity: number;
  unit_price: number;
}

export interface OrderProposalContent {
  type: "order_proposal";
  id: string;
  items: OrderItem[];
  total_price: number;
  special_instructions?: string;
  estimated_delivery?: string;
  expiry_time?: string;
}

export interface PaymentContent {
  type: "payment";
  proposal_message_id: string;
  payment_method?: string;
  delivery_address?: string;
  payment_message?: string;
}

export interface SearchResultContent {
  type: "search";
  query: string;
  business_ids: string[];
  total_results: number;
}

export type MessageContent = string | OrderProposalContent | PaymentContent | SearchResultContent;

export interface Message {
  id: string;
  to_agent: string;
  from_agent: string;
  type: string;
  content: MessageContent;
  created_at: string;
}

export interface MessageThread {
  participants: {
    customer: Customer;
    business: Business;
  };
  messages: Message[];
  lastMessageTime: string;
  utility: number;
}

export interface CustomerAnalytics {
  utility: number;
  payments_made: number;
  proposals_received: number;
}

export interface BusinessAnalytics {
  utility: number;
  proposals_sent: number;
  payments_received: number;
}

export interface MarketplaceSummary {
  total_utility: number;
  total_payments: number;
  total_proposals: number;
}

export interface AnalyticsData {
  customer_analytics: Record<string, CustomerAnalytics>;
  business_analytics: Record<string, BusinessAnalytics>;
  marketplace_summary: MarketplaceSummary;
}

export interface MarketplaceData {
  customers: Customer[];
  businesses: Business[];
  messages: Message[];
  messageThreads: MessageThread[];
  analytics?: AnalyticsData;
}
