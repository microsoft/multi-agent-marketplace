import { ArrowDownAZ, ArrowUpAZ, Store } from "lucide-react";
import React, { useMemo, useState } from "react";

import { Business as BusinessType, BusinessAnalytics } from "../types";
import Business from "./Business";

interface BusinessPanelProps {
  businesses: BusinessType[];
  isLoading: boolean;
  selectedBusiness?: BusinessType | null;
  onBusinessClick?: (business: BusinessType) => void;
  analytics?: Record<string, BusinessAnalytics>;
}

const BusinessPanel: React.FC<BusinessPanelProps> = ({
  businesses,
  isLoading,
  selectedBusiness,
  onBusinessClick,
  analytics,
}) => {
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  // Sort businesses by utility
  const sortedBusinesses = useMemo(() => {
    if (!analytics) return businesses;

    return [...businesses].sort((a, b) => {
      const utilityA = analytics[a.id]?.utility ?? 0;
      const utilityB = analytics[b.id]?.utility ?? 0;
      return sortOrder === "desc" ? utilityB - utilityA : utilityA - utilityB;
    });
  }, [businesses, analytics, sortOrder]);

  const toggleSortOrder = () => {
    setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
  };
  if (isLoading && businesses.length === 0) {
    return (
      <div className="h-full rounded-2xl bg-white p-6 shadow-lg">
        <div className="animate-pulse">
          <div className="mb-6 h-6 rounded bg-gray-200"></div>
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="rounded-xl border border-gray-100 p-4">
                <div className="mb-3 flex items-center space-x-3">
                  <div className="h-12 w-12 rounded-full bg-gray-200"></div>
                  <div className="flex-1">
                    <div className="mb-2 h-4 rounded bg-gray-200"></div>
                    <div className="h-3 rounded bg-gray-100"></div>
                  </div>
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
          <div className="flex items-center space-x-2">
            <Store className="h-5 w-5 text-gray-600" />
            <h2 className="text-xl font-bold text-gray-800">Restaurants</h2>
            <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-sm font-medium text-gray-700">
              {businesses.length}
            </span>
          </div>
          {/* Sort Button */}
          <button
            onClick={toggleSortOrder}
            className="flex items-center space-x-1 rounded-md bg-gray-100 px-2 py-1 text-xs text-gray-700 transition-colors hover:bg-gray-200"
            title={sortOrder === "desc" ? "Highest utility first" : "Lowest utility first"}
          >
            {sortOrder === "desc" ? (
              <>
                <ArrowDownAZ className="h-3.5 w-3.5" />
                <span>Highest</span>
              </>
            ) : (
              <>
                <ArrowUpAZ className="h-3.5 w-3.5" />
                <span>Lowest</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Business List */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-3 p-4">
          {sortedBusinesses.map((business) => (
            <Business
              key={business.id}
              business={business}
              isSelected={selectedBusiness?.id === business.id}
              onClick={() => onBusinessClick?.(business)}
              analytics={analytics?.[business.id]}
            />
          ))}

          {businesses.length === 0 && !isLoading && (
            <div className="py-12 text-center">
              <Store className="mx-auto mb-4 h-16 w-16 text-gray-300" />
              <p className="text-gray-500">No restaurants found</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BusinessPanel;
