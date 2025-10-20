import { clsx } from "clsx";
import { ChevronDown, ChevronUp } from "lucide-react";
import React, { useState } from "react";

import { Customer as CustomerType, CustomerAnalytics } from "../types";
import { getCustomerAvatar } from "../utils/avatars";

interface CustomerProps {
  customer: CustomerType;
  onClick?: () => void;
  isSelected?: boolean;
  analytics?: CustomerAnalytics;
}

const Customer: React.FC<CustomerProps> = ({
  customer,
  onClick,
  isSelected = false,
  analytics,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const formatList = (items: string[] | undefined) => {
    return items && items.length > 0 ? items.join(", ") : "Not available";
  };

  const cleanName =
    customer.name?.replace("agent-", "").replace(/\s+/g, " ").trim() || "Unknown Customer";

  return (
    <div
      className={clsx(
        "group relative overflow-hidden rounded-xl transition-all duration-300",
        isSelected
          ? "border-2 border-brand-400 shadow-lg"
          : "border border-gray-200 hover:border-brand-200",
      )}
    >
      {/* Avatar and Name - Clickable Header */}
      <div
        className={clsx(
          "flex transform cursor-pointer items-start space-x-3 bg-gradient-to-r p-4 transition-all duration-300 hover:-translate-y-0.5",
          isSelected ? "from-brand-50 to-brand-100" : "from-gray-50 to-gray-100",
        )}
        onClick={onClick}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-500 text-xl shadow-sm">
          {getCustomerAvatar(cleanName)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <h3 className="text-sm font-semibold leading-tight text-gray-800">{cleanName}</h3>
              <div className="mt-1 space-y-1">
                {customer.id && <div className="text-xs text-gray-500">{customer.id}</div>}
                {/* Analytics - always visible */}
                {analytics && (
                  <div className="flex items-center gap-2 text-xs font-semibold text-gray-700">
                    <span>Utility: ${analytics.utility.toFixed(2)}</span>
                    <span>|</span>
                    <span>Payments: {analytics.payments_made}</span>
                  </div>
                )}
              </div>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-2 rounded-lg p-1 transition-colors hover:bg-brand-100"
              aria-label={isExpanded ? "Collapse details" : "Expand details"}
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4 text-brand-600" />
              ) : (
                <ChevronDown className="h-4 w-4 text-brand-600" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Customer Details - Collapsible */}
      {isExpanded && (
        <div className="space-y-2 bg-white p-4">
          {customer.user_request && (
            <div>
              <span className="text-xs font-medium text-brand-700">Request:</span>
              <p className="mt-1 line-clamp-3 text-xs text-gray-600">{customer.user_request}</p>
            </div>
          )}
          <div>
            <span className="text-xs font-medium text-brand-700">Menu Items:</span>
            <p className="mt-1 text-xs text-gray-600">
              {formatList(customer.menu_features ? Object.keys(customer.menu_features) : [])}
            </p>
          </div>
          {customer.menu_features && (
            <div>
              <span className="text-xs font-medium text-brand-700">Budget:</span>
              <p className="mt-1 text-xs text-gray-600">
                {Object.entries(customer.menu_features).map(([item, price]) => (
                  <span key={item} className="block">
                    {item}: ${price}
                  </span>
                ))}
              </p>
            </div>
          )}
          {customer.amenity_features && customer.amenity_features.length > 0 && (
            <div>
              <span className="text-xs font-medium text-brand-700">Amenity Preferences:</span>
              <p className="mt-1 text-xs text-gray-600">{formatList(customer.amenity_features)}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Customer;
