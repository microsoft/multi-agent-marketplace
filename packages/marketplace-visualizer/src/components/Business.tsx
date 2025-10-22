import { clsx } from "clsx";
import { ChevronDown, ChevronUp, Star } from "lucide-react";
import React, { useState } from "react";

import { Business as BusinessType, BusinessAnalytics } from "../types";
import { getBusinessAvatar } from "../utils/avatars";

interface BusinessProps {
  business: BusinessType;
  onClick?: () => void;
  isSelected?: boolean;
  analytics?: BusinessAnalytics;
}

const Business: React.FC<BusinessProps> = ({
  business,
  onClick,
  isSelected = false,
  analytics,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const getRatingColor = (rating: number) => {
    if (rating >= 0.8) return "text-brand-800";
    if (rating >= 0.6) return "text-brand-400";
    return "text-brand-200";
  };

  const cleanName = business.name?.replace("agent-", "") || "Unknown Restaurant";

  return (
    <div
      className={clsx(
        "group relative overflow-hidden rounded-xl transition-all duration-300",
        isSelected
          ? "border-2 border-brand-400 shadow-lg"
          : "border border-gray-200 hover:border-brand-200",
      )}
    >
      {/* Header with Avatar and Name - Clickable */}
      <div
        className={clsx(
          "flex transform cursor-pointer items-start space-x-3 bg-gradient-to-r p-4 transition-all duration-300 hover:-translate-y-0.5",
          isSelected ? "from-brand-50 to-brand-100" : "from-gray-50 to-gray-100",
        )}
        onClick={onClick}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-gray-300 to-gray-400 font-bold text-white shadow-sm">
          {getBusinessAvatar(business.name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <h3 className="text-sm font-semibold leading-tight text-gray-800">{cleanName}</h3>
              <div className="mt-1 space-y-1">
                {business.id && <div className="text-xs text-gray-500">{business.id}</div>}
                {/* Analytics - always visible */}
                {analytics && (
                  <div className="flex items-center gap-2 text-xs font-semibold text-gray-700">
                    <span>Utility: ${analytics.utility.toFixed(2)}</span>
                    <span>|</span>
                    <span>Proposals: {analytics.proposals_sent}</span>
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

      {/* Rating and Details - Collapsible */}
      {isExpanded && (
        <div className="space-y-3 bg-white p-4">
          <div className="flex items-center space-x-1">
            <Star className={`h-4 w-4 ${getRatingColor(business.rating)} fill-current`} />
            <span className={`text-sm font-medium ${getRatingColor(business.rating)}`}>
              {business.rating.toFixed(2)}
            </span>
          </div>

          {/* Business Details */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-brand-700">Price Range:</span>
              <span className="text-sm font-semibold text-gray-800">
                ${business.price_min} - ${business.price_max}
              </span>
            </div>
            {business.description && (
              <div>
                <span className="text-xs font-medium text-brand-700">About:</span>
                <p className="mt-1 line-clamp-2 text-xs text-gray-600">{business.description}</p>
              </div>
            )}
            {business.menu_features && Object.keys(business.menu_features).length > 0 && (
              <div>
                <span className="text-xs font-medium text-brand-700">
                  Menu Items ({Object.keys(business.menu_features).length}):
                </span>
                <div className="mt-1 max-h-24 space-y-0.5 overflow-y-auto text-xs text-gray-600">
                  {Object.entries(business.menu_features)
                    .slice(0, 5)
                    .map(([item, price]) => (
                      <div key={item} className="flex justify-between">
                        <span className="truncate">{item}</span>
                        <span className="ml-2 font-medium">${Number(price).toFixed(2)}</span>
                      </div>
                    ))}
                  {Object.keys(business.menu_features).length > 5 && (
                    <div className="italic text-gray-400">
                      + {Object.keys(business.menu_features).length - 5} more
                    </div>
                  )}
                </div>
              </div>
            )}
            {business.amenity_features && (
              <div>
                <span className="text-xs font-medium text-brand-700">Amenities:</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {Object.entries(business.amenity_features)
                    .filter(([_, value]) => value === true)
                    .map(([amenity]) => (
                      <span
                        key={amenity}
                        className="inline-flex items-center rounded-full bg-brand-100 px-2 py-0.5 text-xs text-brand-800"
                      >
                        {amenity}
                      </span>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Business;
