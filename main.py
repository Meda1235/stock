# --- START OF FILE main.py ---

# Use the new functions from the modified chatbot module
from chatbot import (
    build_request_json,
    fetch_stock_time_series,
    process_time_series_data,
    #print_time_series_summary,
    fetch_stock_overview,
    #print_stock_overview,
    fetch_stock_news,
    #print_stock_news
)
import json
from os import getenv

# API Call Tracking
API_CALL_TRACKING = {
    "llm": 0,
    "alpha_vantage": 0
}

# Example Queries - Now include overview and news
queries = [
    # "What was the closing price for Apple yesterday?", # time_series
    # "Show me Microsoft stock data for last week, daily interval.", # time_series
    # "Tell me about Google", # overview
    # "NVDA overview", # overview
    # "What is the market cap for Tesla?", # overview (LLM should map this)
    # "Latest news about Amazon", # news
    # "META stock news", # news
    # "IBM stock price from 2024-03-01 to 2024-04-30.", # time_series
    # "Show me IBM stock data for tomorrow", # time_series (should handle future date gracefully)
    # "Invalid Ticker XYZ stock price yesterday", # time_series (should fail)
    # "Overview for InvalidTickerABC", # overview (should fail)
    # "News for NonExistentTicker", # news (should fail or return no articles)
]

if __name__ == '__main__':
    total_counts_all_queries = {key: 0 for key in API_CALL_TRACKING}

    print(f"--- Initializing Stock Chatbot v2 ---")
    if not getenv("ALPHA_VANTAGE_API_KEY"):
        print("CRITICAL WARNING: ALPHA_VANTAGE_API_KEY environment variable not set!")
        # exit() # Optional: exit if key is mandatory
    if not getenv("OPENROUTER_API_KEY"):
        print("CRITICAL WARNING: OPENROUTER_API_KEY environment variable not set!")
        # exit()

    for i, query in enumerate(queries):
        print(f"\n==============================")
        print(f" Processing Query {i+1}/{len(queries)}")
        print(f" Query: {query}")
        print(f"==============================")

        current_api_counts = {key: 0 for key in API_CALL_TRACKING}
        request_json = None
        result_data = None

        try:
            # Step 1 & 2: Use LLM to get structured request (includes request_type)
            request_json = build_request_json(query, current_api_counts)
            print("\n Final JSON from LLM:")
            print(json.dumps(request_json, indent=2))

            request_type = request_json.get("request_type")

            # --- Branching based on request type ---
            if request_type == "time_series":
                print("\n-- Handling Time Series Request --")
                # Step 3 & 4: Fetch time series data
                raw_stock_data = fetch_stock_time_series(request_json, current_api_counts)
                # Step 5, 6, 7: Process (filter) time series data
                processed_stock_data = process_time_series_data(raw_stock_data, request_json)
                result_data = processed_stock_data # Store for potential JSON print
                # Print summary
              #  print_time_series_summary(processed_stock_data)

            elif request_type == "overview":
                print("\n-- Handling Overview Request --")
                # Step 3 & 4: Fetch overview data
                overview_data = fetch_stock_overview(request_json, current_api_counts)
                result_data = overview_data # Store for potential JSON print
                # Print summary
               # print_stock_overview(overview_data)

            elif request_type == "news":
                print("\n-- Handling News Request --")
                # Step 3 & 4: Fetch news data
                news_data = fetch_stock_news(request_json, current_api_counts)
                result_data = news_data # Store for potential JSON print
                # Print summary
                #print_stock_news(news_data)

            else:
                # Should not happen if build_request_json validates correctly
                print(f"\n--- UNKNOWN REQUEST TYPE ---")
                print(f"LLM returned an unknown request_type: '{request_type}'. Cannot proceed.")
                raise ValueError(f"Unhandled request_type: {request_type}")

            # Optional: Print the raw fetched data if needed for debugging
            # print("\n-- Raw Fetched Data (for debugging) --")
            # print(json.dumps(result_data, indent=2, default=str))


        except ValueError as e: # Catch specific errors (e.g., invalid symbol, bad LLM JSON, bad dates)
            print(f"\n--- VALUE ERROR PROCESSING QUERY ---")
            print(f"{e}")
            print("Processing stopped for this query due to invalid input, configuration, or non-retriable API error.")
            if request_json:
                 print(f"  (Input JSON from LLM: {json.dumps(request_json)})")

        except RuntimeError as e: # Catch runtime errors (e.g., API failures after retries, network issues)
             print(f"\n--- RUNTIME ERROR PROCESSING QUERY ---")
             print(f"{e}")
             print("Processing stopped for this query due to API or execution failure after retries.")
             if request_json:
                  print(f"  (Input JSON from LLM: {json.dumps(request_json)})")

        except Exception as e: # Catch any other unexpected errors
            print(f"\n--- UNEXPECTED ERROR PROCESSING QUERY ---")
            print(f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
            print("Processing stopped for this query.")
            if request_json:
                 print(f"  (Input JSON from LLM: {json.dumps(request_json)})")


        # --- API Call Count Summary for this Query ---
        print("\n--- API Call Counts for this Query ---")
        for api_name, count in current_api_counts.items():
            print(f"  {api_name.replace('_', ' ').title()} Calls: {count}")
        print(f"---------------------------------------------")
        print(f"==============================\n")

        # Update total counts
        for api_name, count in current_api_counts.items():
             total_counts_all_queries[api_name] += count

    # --- Overall Summary ---
    print("\n##############################")
    print(" Overall Summary for All Queries")
    print("##############################")
    print("Total API Calls:")
    for api_name, count in total_counts_all_queries.items():
         print(f"  {api_name.replace('_', ' ').title()}: {count}")
    print("------------------------------")
    print(f"Note: Alpha Vantage free tier has daily request limits. Calls include retries if the first attempt failed but retries were possible.")
    print("##############################")

# --- END OF FILE main.py ---