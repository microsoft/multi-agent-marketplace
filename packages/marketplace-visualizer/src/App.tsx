import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import BusinessPanel from "./components/BusinessPanel";
import CustomerPanel from "./components/CustomerPanel";
import MarketplaceCenter from "./components/MarketplaceCenter";
import { databaseService } from "./services/database";
import { AnalyticsData, Business, Customer, MarketplaceData } from "./types";

function App() {
  const [data, setData] = useState<MarketplaceData | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [selectedBusiness, setSelectedBusiness] = useState<Business | null>(null);

  // Load customers and businesses once on initial mount
  const loadInitialData = async () => {
    setIsLoading(true);
    try {
      console.log("Loading customers & businesses...");
      const [customers, businesses] = await Promise.all([
        databaseService.getCustomers(),
        databaseService.getBusinesses(),
      ]);

      setData({
        customers,
        businesses,
        messages: [],
        messageThreads: [],
      });
      console.log("Loaded:", {
        customers: customers.length,
        businesses: businesses.length,
      });
    } catch (error) {
      console.error("Error loading initial data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // Load messages, threads, and analytics (polled frequently)
  const loadMessages = useCallback(async () => {
    setIsLoadingConversations(true);
    try {
      const marketplaceData = await databaseService.getMarketplaceData();
      setData((prev) =>
        prev
          ? {
              ...prev,
              messages: marketplaceData.messages,
              messageThreads: marketplaceData.messageThreads,
              analytics: marketplaceData.analytics,
            }
          : null,
      );
      // Update analytics state
      if (marketplaceData.analytics) {
        setAnalytics(marketplaceData.analytics);
      }
      setLastUpdate(new Date());
    } catch (error) {
      console.error("Error loading messages:", error);
    } finally {
      setIsLoadingConversations(false);
    }
  }, []);

  // Filter message threads based on selected customer and business
  const filteredMessageThreads = useMemo(() => {
    if (!data?.messageThreads) return [];

    let filtered = data.messageThreads;

    if (selectedCustomer) {
      filtered = filtered.filter(
        (thread) => thread.participants.customer.id === selectedCustomer.id,
      );
    }

    if (selectedBusiness) {
      filtered = filtered.filter(
        (thread) => thread.participants.business.id === selectedBusiness.id,
      );
    }

    return filtered;
  }, [data?.messageThreads, selectedCustomer, selectedBusiness]);

  const handleCustomerClick = (customer: Customer) => {
    setSelectedCustomer(selectedCustomer?.id === customer.id ? null : customer);
  };

  const handleBusinessClick = (business: Business) => {
    setSelectedBusiness(selectedBusiness?.id === business.id ? null : business);
  };

  useEffect(() => {
    const initializeApp = async () => {
      await loadInitialData();

      // Load messages immediately after initial data is loaded
      loadMessages();

      // Poll for message updates every 5 seconds
      const interval = setInterval(loadMessages, 5000);

      return () => clearInterval(interval);
    };

    const cleanup = initializeApp();

    return () => {
      cleanup.then((cleanupFn) => cleanupFn?.());
    };
  }, [loadMessages]);

  if (isLoading && !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-gray-100">
        <div className="text-center">
          <RefreshCw className="mx-auto mb-4 h-12 w-12 animate-spin text-brand-500" />
          <h2 className="mb-2 text-2xl font-bold text-gray-800">Loading Magentic Marketplace...</h2>
          <p className="text-gray-600">Connecting to the marketplace simulation</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-gradient-to-br from-brand-50 to-gray-50">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-brand-400 bg-white shadow-md">
        <div className="w-full px-4 py-5">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <img src="/logo.svg" alt="Magentic Logo" className="h-8 w-8" />
              <div>
                <h1
                  className="bg-clip-text text-xl font-bold text-transparent"
                  style={{ backgroundImage: "linear-gradient(120deg,  #fb81ff, #922185 30%)" }}
                >
                  Magentic Marketplace
                </h1>
              </div>
            </div>

            <div className="flex flex-1 items-center justify-end gap-3">
              {/* Marketplace Summary */}
              {analytics?.marketplace_summary && (
                <div className="flex items-center gap-2 text-xs">
                  <div className="rounded-full bg-brand-100 px-3 py-1.5 font-semibold text-brand-700">
                    Total Utility: ${analytics.marketplace_summary.total_utility.toFixed(2)}
                  </div>
                  <div className="rounded-full bg-brand-100 px-3 py-1.5 font-semibold text-brand-700">
                    Payments: {analytics.marketplace_summary.total_payments}
                  </div>
                  <div className="rounded-full bg-brand-100 px-3 py-1.5 font-semibold text-brand-700">
                    Proposals: {analytics.marketplace_summary.total_proposals}
                  </div>
                </div>
              )}

              <div className="flex items-center space-x-3 text-xs">
                <button
                  onClick={loadMessages}
                  disabled={isLoadingConversations}
                  title={`Last Update: ${lastUpdate.toLocaleTimeString()}`}
                  className="flex items-center space-x-1 rounded-md bg-gray-100 px-3 py-1.5 text-xs text-gray-700 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed"
                >
                  <RefreshCw
                    className={`h-3 w-3 ${isLoadingConversations ? "animate-spin" : ""}`}
                  />
                  <span>Refresh</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="min-h-0 flex-1 overflow-hidden px-8 py-4">
        <div className="grid h-full min-h-0 grid-cols-12 gap-5">
          {/* Customers Panel */}
          <div className="col-span-3 h-full min-h-0 pl-2">
            <CustomerPanel
              customers={data?.customers || []}
              isLoading={isLoading}
              selectedCustomer={selectedCustomer}
              onCustomerClick={handleCustomerClick}
              analytics={analytics?.customer_analytics}
            />
          </div>

          {/* Marketplace Center */}
          <div className="col-span-6 h-full min-h-0">
            <MarketplaceCenter
              messageThreads={filteredMessageThreads}
              businesses={data?.businesses || []}
              isLoading={isLoading}
              selectedCustomer={selectedCustomer}
              selectedBusiness={selectedBusiness}
              onClearCustomer={() => setSelectedCustomer(null)}
              onClearBusiness={() => setSelectedBusiness(null)}
            />
          </div>

          {/* Businesses Panel */}
          <div className="col-span-3 h-full min-h-0 pr-2">
            <BusinessPanel
              businesses={data?.businesses || []}
              isLoading={isLoading}
              selectedBusiness={selectedBusiness}
              onBusinessClick={handleBusinessClick}
              analytics={analytics?.business_analytics}
            />
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
