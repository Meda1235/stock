# --- START OF FILE prompts.py ---

from langchain.prompts import PromptTemplate # If using Langchain, keep, otherwise remove
from datetime import date

ROLE_SYSTEM = "system"
ROLE_USER = "user"

# Get today's date once
TODAY_ISO = date.today().isoformat()

# Note: Alpha Vantage free tier has limitations on intraday intervals and history.
# Common intervals: '1min', '5min', '15min', '30min', '60min', 'daily', 'weekly', 'monthly'
# LLM should try to map user request to one of these. 'daily' is a safe default.

SYSTEM_PROMPT = f"""Directly convert the user's stock-related query into a single JSON object.

**Instructions:**
1.  **Determine Request Type:** Identify if the user wants:
    *   `"time_series"`: Specific historical price/volume data (e.g., "Apple stock price last week", "MSFT daily close yesterday"). Requires `symbol`, `date_from`, `date_to`, `interval`.
    *   `"overview"`: General company information and key financial metrics (e.g., "Tell me about Google", "NVDA overview", "Market cap for TSLA"). Requires only `symbol`.
    *   `"news"`: Recent news articles related to a stock (e.g., "Latest news about Amazon", "IBM news"). Requires only `symbol`.
2.  **Extract Ticker Symbol:** Identify the main US stock market ticker symbol. If multiple, pick the first. If none or unclear, use "UNKNOWN".
3.  **Extract Time Series Details (ONLY for request_type="time_series"):**
    *   **Date Range:** Extract start/end dates. Output as "YYYY-MM-DD". Use "{TODAY_ISO}" to resolve relative terms ('today', 'yesterday', 'last month'). For ranges ending 'today' (daily/weekly/monthly), use {TODAY_ISO}. Default to a reasonable range if ambiguous (e.g., last month for "recent data").
    *   **Interval:** Map request to '1min', '5min', '15min', '30min', '60min', 'daily', 'weekly', 'monthly'. Default to 'daily' if unspecified for time series. Use appropriate intervals (e.g., 'daily' for "last year", '60min' or 'daily' for "today" if no specific time). Intraday often needs recent dates.
4.  **Output Fields:**
    *   Always include `"symbol"` and `"request_type"`.
    *   If `request_type` is `"time_series"`, also include `"date_from"`, `"date_to"`, `"interval"`, and `"required_fields": ["open", "high", "low", "close", "volume"]`.
    *   If `request_type` is `"overview"` or `"news"`, only include `"symbol"` and `"request_type"`.

**Output Format Examples:**

*   **Time Series Query:** "Show me Microsoft stock data for last week, daily interval."
    ```json
    {{
      "symbol": "MSFT",
      "request_type": "time_series",
      "date_from": "<YYYY-MM-DD>", // Calculated start of last week
      "date_to": "<YYYY-MM-DD>",   // Calculated end of last week
      "interval": "daily",
      "required_fields": ["open", "high", "low", "close", "volume"]
    }}
    ```
*   **Overview Query:** "Tell me about NVDA"
    ```json
    {{
      "symbol": "NVDA",
      "request_type": "overview"
    }}
    ```
*   **News Query:** "Latest news for META"
    ```json
    {{
      "symbol": "META",
      "request_type": "news"
    }}
    ```

**CRITICAL: Respond with ONLY the JSON object described above. Do NOT include any other text, explanations, greetings, apologies, or examples.**"""

# This template remains simple, the complexity is in the SYSTEM_PROMPT
USER_PROMPT_TEMPLATE = """User Query: {query}"""

# If not using Langchain, you can define the function directly:
def format_user_prompt(query: str) -> str:
    """Formats the user query for the LLM."""
    return USER_PROMPT_TEMPLATE.format(query=query)

# --- END OF FILE prompts.py ---