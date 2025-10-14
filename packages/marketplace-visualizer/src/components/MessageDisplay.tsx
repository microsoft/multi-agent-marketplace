import { Clock, MapPin, ShoppingBag } from "lucide-react";
import React from "react";

import {
  MessageContent,
  OrderProposalContent,
  PaymentContent,
  SearchResultContent,
} from "../types";

interface MessageDisplayProps {
  content: MessageContent;
  businesses?: Array<{ id: string; name: string }>;
}

const OrderProposalDisplay: React.FC<{ proposal: OrderProposalContent }> = ({ proposal }) => {
  return (
    <div className="space-y-3">
      {/* Proposal ID */}
      <div className="font-mono text-[10px] uppercase tracking-wider opacity-50">{proposal.id}</div>

      {/* Items */}
      <div className="space-y-2">
        {proposal.items.map((item, index) => (
          <div key={index} className="flex items-start justify-between gap-3">
            <div className="flex flex-1 items-start gap-2">
              <ShoppingBag className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 opacity-50" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium leading-tight">{item.item_name}</div>
                <div className="mt-0.5 text-xs opacity-60">
                  Qty {item.quantity} × ${item.unit_price.toFixed(2)}
                </div>
              </div>
            </div>
            <div className="text-sm font-semibold tabular-nums">
              ${(item.quantity * item.unit_price).toFixed(2)}
            </div>
          </div>
        ))}
      </div>

      {/* Total */}
      <div className="border-t border-white/25 pt-2.5">
        <div className="flex items-center justify-between">
          <span className="text-sm font-bold uppercase tracking-wider opacity-80">Total</span>
          <span className="text-sm font-bold tabular-nums">${proposal.total_price.toFixed(2)}</span>
        </div>
      </div>

      {/* Delivery & Instructions */}
      {(proposal.estimated_delivery || proposal.special_instructions) && (
        <div className="space-y-2.5 border-t border-white/15 pt-2.5">
          {proposal.estimated_delivery && (
            <div className="flex items-start gap-2">
              <Clock className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 opacity-50" />
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">
                  Estimated Delivery
                </div>
                <div className="mt-0.5 text-xs opacity-85">{proposal.estimated_delivery}</div>
              </div>
            </div>
          )}

          {proposal.special_instructions && (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-60">
                Special Instructions
              </div>
              <div className="text-sm leading-relaxed opacity-90">
                {proposal.special_instructions}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const PaymentDisplay: React.FC<{ payment: PaymentContent }> = ({ payment }) => {
  return (
    <div className="space-y-2.5">
      {/* Payment Details */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider opacity-60">Proposal ID</span>
          <span className="font-mono text-sm font-medium opacity-90">
            {payment.proposal_message_id}
          </span>
        </div>

        {payment.payment_method && (
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider opacity-60">Payment Method</span>
            <span className="text-sm font-medium capitalize opacity-90">
              {payment.payment_method.replace("_", " ")}
            </span>
          </div>
        )}
      </div>

      {payment.delivery_address && (
        <div className="bg-white/8 rounded-md p-2.5">
          <div className="flex items-start gap-2">
            <MapPin className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 opacity-50" />
            <div className="min-w-0 flex-1">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-60">
                Delivery Address
              </div>
              <div className="text-sm leading-relaxed opacity-90">{payment.delivery_address}</div>
            </div>
          </div>
        </div>
      )}

      {payment.payment_message && (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-60">
            Note
          </div>
          <div className="text-sm leading-relaxed opacity-90">{payment.payment_message}</div>
        </div>
      )}
    </div>
  );
};

const SearchResultDisplay: React.FC<{
  search: SearchResultContent;
  businesses?: Array<{ id: string; name: string }>;
}> = ({ search, businesses }) => {
  const businessNames = businesses
    ? search.business_ids
        .map((id) => businesses.find((b) => b.id === id)?.name.replace("agent-", ""))
        .filter(Boolean)
    : [];

  return (
    <div className="space-y-2.5">
      <div className="space-y-1.5">
        <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">Query</div>
        <div className="text-sm font-medium italic opacity-90">"{search.query}"</div>
        <div className="text-sm opacity-70">Found {search.total_results} businesses</div>
      </div>

      {businessNames.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">
            Matched Businesses
          </div>
          <div className="flex flex-wrap gap-1.5">
            {businessNames.map((name, index) => (
              <span
                key={index}
                className="rounded-full bg-white/15 px-2.5 py-0.5 text-sm font-medium opacity-90"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const MessageDisplay: React.FC<MessageDisplayProps> = ({ content, businesses }) => {
  if (typeof content === "string") {
    return <span>{content.replace(/"/g, "")}</span>;
  }

  if (content.type === "order_proposal") {
    return <OrderProposalDisplay proposal={content} />;
  }

  if (content.type === "payment") {
    return <PaymentDisplay payment={content} />;
  }

  if (content.type === "search") {
    return <SearchResultDisplay search={content} businesses={businesses} />;
  }

  return <span>{JSON.stringify(content)}</span>;
};

export default MessageDisplay;
