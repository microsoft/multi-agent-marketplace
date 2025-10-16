import { ArrowDownAZ, ArrowUpAZ, User } from "lucide-react";
import React, { useMemo, useState } from "react";

import { Customer as CustomerType, CustomerAnalytics } from "../types";
import Customer from "./Customer";

interface CustomerPanelProps {
  customers: CustomerType[];
  isLoading: boolean;
  selectedCustomer?: CustomerType | null;
  onCustomerClick?: (customer: CustomerType) => void;
  analytics?: Record<string, CustomerAnalytics>;
}

const CustomerPanel: React.FC<CustomerPanelProps> = ({
  customers,
  isLoading,
  selectedCustomer,
  onCustomerClick,
  analytics,
}) => {
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  // Sort customers by utility
  const sortedCustomers = useMemo(() => {
    if (!analytics) return customers;

    return [...customers].sort((a, b) => {
      const utilityA = analytics[a.id]?.utility ?? 0;
      const utilityB = analytics[b.id]?.utility ?? 0;
      return sortOrder === "desc" ? utilityB - utilityA : utilityA - utilityB;
    });
  }, [customers, analytics, sortOrder]);

  const toggleSortOrder = () => {
    setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
  };
  if (isLoading && customers.length === 0) {
    return (
      <div className="h-full rounded-2xl bg-white p-6 shadow-lg">
        <div className="animate-pulse">
          <div className="mb-6 h-6 rounded bg-gray-200"></div>
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex items-center space-x-3">
                <div className="h-12 w-12 rounded-full bg-gray-200"></div>
                <div className="flex-1">
                  <div className="mb-2 h-4 rounded bg-gray-200"></div>
                  <div className="h-3 rounded bg-gray-100"></div>
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
            <User className="h-5 w-5 text-gray-600" />
            <h2 className="text-xl font-bold text-gray-800">Customers</h2>
            <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-sm font-medium text-gray-700">
              {customers.length}
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

      {/* Customer List */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-3 p-4">
          {sortedCustomers.map((customer) => (
            <Customer
              key={customer.id}
              customer={customer}
              isSelected={selectedCustomer?.id === customer.id}
              onClick={() => onCustomerClick?.(customer)}
              analytics={analytics?.[customer.id]}
            />
          ))}

          {customers.length === 0 && !isLoading && (
            <div className="py-12 text-center">
              <User className="mx-auto mb-4 h-16 w-16 text-gray-300" />
              <p className="text-gray-500">No customers found</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CustomerPanel;
