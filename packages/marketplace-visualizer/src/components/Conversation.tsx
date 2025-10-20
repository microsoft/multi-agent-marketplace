import { clsx } from "clsx";
import { ArrowRight, Clock, CreditCard, MessageSquare, Search, Send } from "lucide-react";
import React, { useMemo } from "react";

import { MessageThread } from "../types";
import { getBusinessAvatar, getCustomerAvatar } from "../utils/avatars";
import MessageDisplay from "./MessageDisplay";

interface ConversationProps {
  thread: MessageThread;
  businesses?: Array<{ id: string; name: string }>;
  onClick?: () => void;
  isExpanded?: boolean;
}

const Conversation: React.FC<ConversationProps> = ({
  thread,
  businesses,
  onClick,
  isExpanded = false,
}) => {
  // Calculate conversation analytics
  const conversationStats = useMemo(() => {
    const payments = thread.messages.filter(
      (m) => m.type === "payment" && m.from_agent === thread.participants.customer.id,
    ).length;

    const proposals = thread.messages.filter(
      (m) => m.type === "order_proposal" && m.from_agent === thread.participants.business.id,
    ).length;

    // Use utility from backend (already calculated per conversation)
    const utility = thread.utility;

    return { payments, proposals, utility };
  }, [
    thread.messages,
    thread.participants.customer.id,
    thread.participants.business.id,
    thread.utility,
  ]);

  const getMessageIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case "pay":
      case "payment":
        return <CreditCard className="h-4 w-4" />;
      case "order_proposal":
      case "proposal":
        return <MessageSquare className="h-4 w-4" />;
      case "search":
        return <Search className="h-4 w-4" />;
      case "send":
      case "message":
      case "text":
        return <Send className="h-4 w-4" />;
      default:
        return <MessageSquare className="h-4 w-4" />;
    }
  };

  const customerName = thread.participants.customer.name?.replace("agent-", "") || "Customer";
  const businessName = thread.participants.business.name?.replace("agent-", "") || "Restaurant";
  const lastMessage = thread.messages[thread.messages.length - 1];

  if (isExpanded) {
    // Detailed view when expanded
    return (
      <div className="flex h-full min-h-0 flex-col space-y-4">
        {/* Thread Header */}
        <div className="flex-shrink-0 rounded-xl border border-brand-100 bg-gradient-to-r from-brand-50 to-brand-100 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-500 text-lg shadow-sm">
                  {getCustomerAvatar(customerName)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-800">{customerName}</p>
                  <p className="text-xs text-gray-500">Customer</p>
                </div>
              </div>
              <ArrowRight className="h-5 w-5 text-brand-400" />
              <div className="flex items-center space-x-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-gray-300 to-gray-400 font-bold text-white shadow-sm">
                  {getBusinessAvatar(businessName)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-800">{businessName}</p>
                  <p className="text-xs text-gray-500">Restaurant</p>
                </div>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm font-medium text-brand-600">
                {thread.messages.length} messages
              </p>
              <p className="text-xs text-gray-500">
                {new Date(thread.lastMessageTime).toLocaleTimeString()}
              </p>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          {thread.messages.map((message) => {
            const isFromCustomer = thread.participants.customer.id === message.from_agent;
            const senderName = isFromCustomer
              ? thread.participants.customer.name?.replace("agent-", "") || "Customer"
              : thread.participants.business.name?.replace("agent-", "") || "Restaurant";

            return (
              <div key={message.id} className="space-y-1">
                {/* Sender Name */}
                <div className={clsx("flex", isFromCustomer ? "justify-start" : "justify-end")}>
                  <div
                    className={clsx(
                      "flex items-center space-x-2 px-3",
                      isFromCustomer ? "text-brand-600" : "text-gray-600",
                    )}
                  >
                    <div
                      className={clsx(
                        "flex h-6 w-6 items-center justify-center rounded-full text-xs",
                        isFromCustomer
                          ? "bg-brand-100 text-brand-700"
                          : "bg-gray-100 text-gray-700",
                      )}
                    >
                      {isFromCustomer
                        ? getCustomerAvatar(senderName)
                        : getBusinessAvatar(businessName)}
                    </div>
                    <span className="text-sm font-medium">{senderName}</span>
                    <span className="text-xs text-gray-500">
                      {new Date(message.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                </div>

                {/* Message Bubble */}
                <div className={clsx("flex", isFromCustomer ? "justify-start" : "justify-end")}>
                  <div
                    className={clsx(
                      "max-w-xs rounded-2xl px-4 py-3 shadow-sm lg:max-w-md",
                      isFromCustomer
                        ? "ml-9 rounded-bl-md bg-gradient-to-br from-brand-500 to-brand-600 text-white"
                        : "mr-9 rounded-br-md bg-gradient-to-br from-gray-400 to-gray-500 text-white",
                    )}
                  >
                    <div className="mb-2 flex items-center space-x-2">
                      {getMessageIcon(message.type)}
                      <span className="text-sm font-medium capitalize opacity-90">
                        {message.type.replace(/_/g, " ")}
                      </span>
                    </div>
                    <div className="text-sm leading-relaxed">
                      <MessageDisplay content={message.content} businesses={businesses} />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // List view (default)
  return (
    <div
      onClick={onClick}
      className={clsx(
        "group relative rounded-xl bg-gradient-to-r from-brand-50 to-brand-50 p-4",
        "border border-brand-100 transition-all duration-300 hover:border-brand-200",
        "transform cursor-pointer hover:-translate-y-1 hover:shadow-md",
      )}
    >
      {/* Connection Visualization */}
      <div className="mb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* Customer */}
            <div className="flex items-center gap-1.5">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-500 text-xs shadow-sm">
                {getCustomerAvatar(customerName)}
              </div>
              <span className="text-sm font-medium text-gray-800">{customerName}</span>
            </div>

            {/* Arrow */}
            <ArrowRight className="h-4 w-4 text-brand-400" />

            {/* Business */}
            <div className="flex items-center gap-1.5">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-gray-300 to-gray-400 text-xs font-bold text-white shadow-sm">
                {getBusinessAvatar(businessName)}
              </div>
              <span className="text-sm font-medium text-gray-800">{businessName}</span>
            </div>
          </div>

          <div className="flex items-center space-x-1 text-right">
            <Clock className="h-3 w-3 flex-shrink-0 text-gray-400" />
            <span className="text-xs tabular-nums text-gray-500">
              {new Date(thread.lastMessageTime).toLocaleTimeString()}
            </span>
          </div>
        </div>

        {/* Stats - New line below names */}
        <div className="mt-2 flex items-center gap-2 text-xs font-semibold text-gray-600">
          <span>{thread.messages.length} messages</span>
          <span>|</span>
          <span>Customer Utility: ${conversationStats.utility.toFixed(2)}</span>
          <span>|</span>
          <span>Proposals: {conversationStats.proposals}</span>
          <span>|</span>
          <span>Payments: {conversationStats.payments}</span>
        </div>
      </div>

      {/* Last Message Preview */}
      <div className="rounded-lg border border-brand-100 bg-white p-3">
        <p className="mb-1 text-xs font-medium text-brand-700">Last message:</p>
        <div className="line-clamp-2 text-sm leading-relaxed text-gray-700">
          {typeof lastMessage.content === "string"
            ? lastMessage.content.replace(/"/g, "").substring(0, 100) +
              (lastMessage.content.length > 100 ? "..." : "")
            : lastMessage.content.type === "payment"
              ? "💳 Payment sent"
              : lastMessage.content.type === "order_proposal"
                ? `📋 Order Proposal - $${lastMessage.content.total_price.toFixed(2)}`
                : lastMessage.content.type === "search"
                  ? `🔍 Search: "${lastMessage.content.query}"`
                  : "Message"}
        </div>
      </div>

      {/* Hover Effect */}
      <div className="pointer-events-none absolute inset-0 rounded-xl bg-gradient-to-r from-brand-400/10 to-brand-300/10 opacity-0 transition-opacity duration-300 group-hover:opacity-100"></div>
    </div>
  );
};

export default Conversation;
