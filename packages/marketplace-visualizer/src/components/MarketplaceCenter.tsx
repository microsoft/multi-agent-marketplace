import { ArrowDownAZ, ArrowUpAZ, Eye, MessageSquare, X } from "lucide-react";
import React, { useEffect, useMemo, useState } from "react";

import { Business, Customer, MessageThread } from "../types";
import Conversation from "./Conversation";

interface MarketplaceCenterProps {
  messageThreads: MessageThread[];
  businesses: Business[];
  isLoading: boolean;
  selectedCustomer: Customer | null;
  selectedBusiness: Business | null;
  onClearCustomer: () => void;
  onClearBusiness: () => void;
}

const MarketplaceCenter: React.FC<MarketplaceCenterProps> = ({
  messageThreads,
  businesses,
  isLoading,
  selectedCustomer,
  selectedBusiness,
  onClearCustomer,
  onClearBusiness,
}) => {
  const [selectedThread, setSelectedThread] = useState<MessageThread | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  // Reset selected thread when filters change
  useEffect(() => {
    setSelectedThread(null);
  }, [selectedCustomer, selectedBusiness]);

  // Sort message threads by lastMessageTime
  const sortedMessageThreads = useMemo(() => {
    return [...messageThreads].sort((a, b) => {
      const timeA = new Date(a.lastMessageTime).getTime();
      const timeB = new Date(b.lastMessageTime).getTime();
      return sortOrder === "desc" ? timeB - timeA : timeA - timeB;
    });
  }, [messageThreads, sortOrder]);

  const toggleSortOrder = () => {
    setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
  };

  if (isLoading && messageThreads.length === 0) {
    return (
      <div className="h-full rounded-2xl bg-white p-6 shadow-lg">
        <div className="animate-pulse">
          <div className="mb-6 h-6 rounded bg-gray-200"></div>
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="rounded-xl border border-gray-100 p-4">
                <div className="mb-3 flex items-center space-x-3">
                  <div className="h-8 w-8 rounded-full bg-gray-200"></div>
                  <div className="h-4 w-4 bg-gray-300"></div>
                  <div className="h-8 w-8 rounded-full bg-gray-200"></div>
                  <div className="h-4 flex-1 rounded bg-gray-200"></div>
                </div>
                <div className="space-y-2">
                  <div className="h-3 rounded bg-gray-100"></div>
                  <div className="h-3 w-3/4 rounded bg-gray-100"></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl bg-white shadow-lg">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-100 p-4">
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex items-center space-x-2">
              <MessageSquare className="h-5 w-5 text-gray-600" />
              <h2 className="text-xl font-bold text-gray-800">Marketplace</h2>
              <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-sm font-medium text-gray-700">
                {messageThreads.length} conversations
              </span>
            </div>
            {/* Active Filters */}
            {(selectedCustomer || selectedBusiness) && (
              <div className="flex items-center gap-2">
                {selectedCustomer && (
                  <div className="flex items-center space-x-1 rounded-full bg-brand-100 px-3 py-1.5 text-xs text-brand-800">
                    <span className="font-medium">
                      Customer: {selectedCustomer.name.replace("agent-", "")}
                    </span>
                    <button
                      onClick={onClearCustomer}
                      className="ml-1 rounded-full p-0.5 transition-colors hover:bg-brand-200"
                      aria-label="Clear customer filter"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )}
                {selectedBusiness && (
                  <div className="flex items-center space-x-1 rounded-full bg-brand-100 px-3 py-1.5 text-xs text-brand-800">
                    <span className="font-medium">
                      Business: {selectedBusiness.name.replace("agent-", "")}
                    </span>
                    <button
                      onClick={onClearBusiness}
                      className="ml-1 rounded-full p-0.5 transition-colors hover:bg-brand-200"
                      aria-label="Clear business filter"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Sort Button */}
            {!selectedThread && (
              <button
                onClick={toggleSortOrder}
                className="flex items-center space-x-1 rounded-md bg-gray-100 px-2 py-1 text-xs text-gray-700 transition-colors hover:bg-gray-200"
                title={sortOrder === "desc" ? "Newest first" : "Oldest first"}
              >
                {sortOrder === "desc" ? (
                  <>
                    <ArrowDownAZ className="h-3.5 w-3.5" />
                    <span>Newest</span>
                  </>
                ) : (
                  <>
                    <ArrowUpAZ className="h-3.5 w-3.5" />
                    <span>Oldest</span>
                  </>
                )}
              </button>
            )}
            {selectedThread && (
              <button
                onClick={() => setSelectedThread(null)}
                className="flex items-center space-x-1 text-sm text-gray-500 hover:text-gray-700"
              >
                <Eye className="h-4 w-4" />
                <span>View All</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="p-4">
          {selectedThread ? (
            // Detailed Thread View
            <Conversation thread={selectedThread} businesses={businesses} isExpanded={true} />
          ) : (
            // Thread List View
            <div className="space-y-3">
              {sortedMessageThreads.map((thread) => (
                <Conversation
                  key={`${thread.participants.customer.id}-${thread.participants.business.id}`}
                  thread={thread}
                  businesses={businesses}
                  onClick={() => setSelectedThread(thread)}
                  isExpanded={false}
                />
              ))}

              {sortedMessageThreads.length === 0 && !isLoading && (
                <div className="py-12 text-center">
                  <MessageSquare className="mx-auto mb-4 h-16 w-16 text-gray-300" />
                  <p className="text-gray-500">No conversations found</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MarketplaceCenter;
