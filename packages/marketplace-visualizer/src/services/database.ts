import { Business, Customer, MarketplaceData } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

class DatabaseService {
  private cache: MarketplaceData | null = null;
  private lastFetch: number = 0;
  private cacheDuration: number = 2000; // Cache for 2 seconds
  private pendingRequest: Promise<
    Pick<MarketplaceData, "messages" | "messageThreads" | "analytics">
  > | null = null;

  constructor() {
    console.log("Database service initialized - connecting to Python server at", API_BASE_URL);
  }

  private async fetchWithTimeout(url: string, timeout: number = 5000): Promise<Response> {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
        },
      });
      clearTimeout(id);
      return response;
    } catch (error) {
      clearTimeout(id);
      throw error;
    }
  }

  private parseMessageContent(content: unknown): unknown {
    // If content is already an object, return as is
    if (typeof content === "object" && content !== null) {
      return content;
    }

    // If content is a string, try to parse it as JSON
    if (typeof content === "string") {
      // If it looks like JSON, parse it
      if (content.startsWith("{") || content.startsWith("[")) {
        try {
          return JSON.parse(content);
        } catch {
          return content;
        }
      }
      return content;
    }

    return content;
  }

  async getMarketplaceData(): Promise<
    Pick<MarketplaceData, "messages" | "messageThreads" | "analytics">
  > {
    const now = Date.now();

    // Return cached data if it's still fresh
    if (this.cache && now - this.lastFetch < this.cacheDuration) {
      return {
        messages: this.cache.messages,
        messageThreads: this.cache.messageThreads,
        analytics: this.cache.analytics,
      };
    }

    // If there's already a pending request, return it instead of making a new one
    if (this.pendingRequest) {
      return this.pendingRequest;
    }

    // Create a new request
    this.pendingRequest = (async () => {
      try {
        console.log("Fetching marketplace data from server...");
        const response = await this.fetchWithTimeout(`${API_BASE_URL}/marketplace-data`, 10000);

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Parse message content if it's JSON strings
        if (data.messageThreads) {
          data.messageThreads.forEach((thread: { messages: Array<{ content: unknown }> }) => {
            thread.messages.forEach((message) => {
              message.content = this.parseMessageContent(message.content);
            });
          });
        }

        // Update cache with new messages/threads/analytics
        if (this.cache) {
          this.cache.messages = data.messages;
          this.cache.messageThreads = data.messageThreads;
          this.cache.analytics = data.analytics;
        }
        this.lastFetch = now;

        console.log("Marketplace data loaded:", {
          messages: data.messages.length,
          threads: data.messageThreads.length,
          analytics: data.analytics ? "included" : "missing",
        });

        return data;
      } catch (error) {
        // Handle AbortError silently (it's expected when requests are cancelled)
        if (error instanceof Error && error.name === "AbortError") {
          console.log("Request was aborted (likely due to timeout or new request)");
        } else {
          console.error("Error fetching marketplace data:", error);
        }

        // Return cached data if available, even if expired
        if (this.cache) {
          console.log("Using cached data due to error");
          return {
            messages: this.cache.messages,
            messageThreads: this.cache.messageThreads,
            analytics: this.cache.analytics,
          };
        }

        // Return empty data as fallback
        return {
          messages: [],
          messageThreads: [],
          analytics: undefined,
        };
      } finally {
        // Clear pending request when done
        this.pendingRequest = null;
      }
    })();

    return this.pendingRequest;
  }

  async getCustomers(): Promise<Customer[]> {
    try {
      const response = await this.fetchWithTimeout(`${API_BASE_URL}/customers`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error("Error fetching customers:", error);
      return [];
    }
  }

  async getBusinesses(): Promise<Business[]> {
    try {
      const response = await this.fetchWithTimeout(`${API_BASE_URL}/businesses`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error("Error fetching businesses:", error);
      return [];
    }
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await this.fetchWithTimeout(`${API_BASE_URL}/health`, 3000);
      return response.ok;
    } catch (error) {
      console.error("Health check failed:", error);
      return false;
    }
  }

  // Clear cache to force refresh
  clearCache(): void {
    this.cache = null;
    this.lastFetch = 0;
    this.pendingRequest = null;
  }

  // Get cache status
  getCacheInfo(): { cached: boolean; age: number } {
    const now = Date.now();
    return {
      cached: this.cache !== null,
      age: this.cache ? now - this.lastFetch : 0,
    };
  }
}

export const databaseService = new DatabaseService();
