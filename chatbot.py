# --- START OF FILE chatbot.py ---

import os
import json
import re
import requests
import time
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT, ROLE_SYSTEM, ROLE_USER, format_user_prompt
from os import getenv
from datetime import date, datetime, timedelta
# --- LLM and JSON Extraction (Většinou beze změny) ---
import random
from datetime import date, timedelta, datetime
import pandas as pd # Už tam pravděpodobně je
# Nové importy pro cache a případné datové struktury
import streamlit as st
import pandas as pd # Nyní potřebujeme pro přípravu dat v app.py

load_dotenv()

# LLM Config
OPENROUTER_API_KEY = getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MODEL = getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct:free")

# Stock API Config
ALPHA_VANTAGE_API_KEY = getenv("ALPHA_VANTAGE_API_KEY")
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"

# Retries Config
LLM_MAX_RETRIES = 2
LLM_RETRY_DELAY_SECONDS = 3
STOCK_API_MAX_RETRIES = 2
STOCK_API_RETRY_DELAY_SECONDS = 15



def create_mock_stock_data(symbol="MOCK", interval="daily", days_or_months=22):
    """
    Generuje falešná data časových řad akcií ve formátu podobném Alpha Vantage.

    Args:
        symbol (str): Ticker symbol pro mock data.
        interval (str): 'daily', 'weekly', nebo 'monthly'.
        days_or_months (int): Počet datových bodů (dnů, týdnů, měsíců) k vygenerování zpětně.

    Returns:
        dict: Slovník ve formátu, který očekává display_time_series v app.py.
              Obsahuje query_details, metadata a time_series.
    """
    print(f"--- Generating MOCK data for {symbol} ({interval}, {days_or_months} points) ---")
    time_series = {}
    current_date = date.today()
    price = round(random.uniform(100, 500), 2) # Start price

    date_format = "%Y-%m-%d"
    time_series_key = f"Time Series ({interval.capitalize()})"
    if interval == "monthly":
        time_series_key = "Monthly Adjusted Time Series" # AV klíč se může lišit
    elif interval == "weekly":
         time_series_key = "Weekly Adjusted Time Series"

    date_list = []
    # Generování seznamu dat zpětně
    temp_date = current_date
    if interval == "daily":
        # Generuj více dní a pak vyber pracovní dny
        all_dates = [temp_date - timedelta(days=i) for i in range(days_or_months * 2)] # Více pro jistotu
        # Filtruj jen pracovní dny (pondělí=0, neděle=6)
        business_days = [d for d in all_dates if d.weekday() < 5]
        date_list = sorted(business_days, reverse=True)[:days_or_months] # Vezmi posledních N pracovních dní
        date_list.reverse() # Seřaď od nejstaršího po nejnovější pro generování
    elif interval == "weekly":
        # Najdi poslední pátek a jdi týdny zpět
        temp_date -= timedelta(days=(temp_date.weekday() - 4) % 7) # Poslední pátek
        date_list = [temp_date - timedelta(weeks=i) for i in range(days_or_months)]
        date_list.reverse()
    elif interval == "monthly":
         # Najdi konec minulého měsíce a jdi měsíce zpět
         first_of_current_month = temp_date.replace(day=1)
         last_of_last_month = first_of_current_month - timedelta(days=1)
         date_list = []
         temp_month_end = last_of_last_month
         for _ in range(days_or_months):
             date_list.append(temp_month_end)
             first_of_prev_month = temp_month_end.replace(day=1)
             temp_month_end = first_of_prev_month - timedelta(days=1)
         date_list.reverse() # Od nejstaršího

    # Generování cenových dat
    date_to_str = current_date.strftime(date_format)
    date_from_str = date_list[0].strftime(date_format) if date_list else date_to_str

    for dt in date_list:
        date_str = dt.strftime(date_format)
        change_percent = random.uniform(-0.03, 0.03) # +/- 3% change
        open_price = round(price * (1 + random.uniform(-0.005, 0.005)), 2)
        close_price = round(price * (1 + change_percent), 2)
        high_price = round(max(open_price, close_price) * (1 + random.uniform(0, 0.015)), 2)
        low_price = round(min(open_price, close_price) * (1 - random.uniform(0, 0.015)), 2)
        volume = random.randint(5_000_000, 100_000_000)

        time_series[date_str] = {
            "1. open": str(open_price),
            "2. high": str(high_price),
            "3. low": str(low_price),
            "4. close": str(close_price),
            # Můžeme přidat i další klíče, které AV vrací
            "5. adjusted close": str(close_price), # Zjednodušení
            "6. volume": str(volume),
            "7. dividend amount": "0.0000",
            "8. split coefficient": "1.0"
        }
        price = close_price # Další den začíná na close ceně předchozího

    mock_request = {
        "symbol": symbol,
        "request_type": "time_series",
        "date_from": date_from_str,
        "date_to": date_to_str,
        "interval": interval,
        "required_fields": ["open", "high", "low", "close", "volume"]
    }

    mock_result_data = {
        "query_details": {
            **mock_request, # Zkopíruje všechny klíče z mock_request
            "api_function": f"MOCK_{interval.upper()}",
            "fetched_data_key": time_series_key,
            "filtering_applied": "date_range (mock)",
            "filtered_points_count": len(time_series)
        },
        "metadata": {
             "1. Information": f"Mock {interval.capitalize()} Adjusted Prices and Volumes",
             "2. Symbol": symbol,
             "3. Last Refreshed": date.today().strftime(date_format),
             "4. Output Size": "Full",
             "5. Time Zone": "US/Eastern" # Nebo jiná
        },
        "time_series_key": time_series_key,
        "time_series": time_series
    }

    print(f"--- Finished generating {len(time_series)} MOCK data points ---")
    # Vrátíme jak data, tak i "request", aby se mohl zobrazit v UI
    return mock_result_data, mock_request
def extract_json_from_text(text: str) -> dict:
    """
    Extracts the first valid JSON object matching the expected stock structure.
    Prioritizes ```json ... ``` blocks, then looks for the first parsable {...}.
    """
    # 1. Prioritize ```json ``` blocks
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        json_str = match.group(1)
        try:
            parsed = json.loads(json_str)
            if "request_type" in parsed:
                 print("Found JSON inside ```json ... ``` block.")
                 return parsed
            else:
                 print("Warning: Found ```json ... ``` block, but missing 'request_type'. Continuing search.")
        except json.JSONDecodeError as e:
            print(f"Warning: Found ```json block, but failed to parse: {e}. Continuing search.")

    # 2. Search for the first plausible {...} block
    print("No valid ```json ... ``` block found or parsed. Searching for first general {...} block.")
    first_brace = text.find('{')
    if first_brace == -1:
        raise ValueError("No opening brace '{' found in model response.")

    brace_level = 0
    potential_json_str = ""
    try:
        for i in range(first_brace, len(text)):
            char = text[i]
            if char == '{':
                brace_level += 1
            elif char == '}':
                if brace_level > 0:
                    brace_level -= 1
                    if brace_level == 0:
                        potential_json_str = text[first_brace : i + 1]
                        break
    except Exception as e:
         print(f"Error during brace matching: {e}")

    if potential_json_str:
        try:
            parsed = json.loads(potential_json_str)
            if "request_type" in parsed:
                 print(f"Found first plausible {{...}} block and parsed successfully.")
                 return parsed
            else:
                 print("Warning: Parsed first {...} block, but content missing 'request_type'.")
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse the first {{...}} block: {e}")

    # 3. If neither method worked, raise an error
    raise ValueError("No valid JSON object with 'request_type' found in model response.")


def transform_query_to_json(query: str, api_counts: dict) -> dict:
    """ Uses LLM to transform natural language query into a structured JSON request. """
    user_message_content = format_user_prompt(query=query)
    messages = [
        {"role": ROLE_SYSTEM, "content": SYSTEM_PROMPT},
        {"role": ROLE_USER, "content": user_message_content}
    ]

    print(f"--- Sending to LLM ({OPENROUTER_MODEL}) ---")
    print(f"User Query (for LLM): {query}")
    print(f"System Prompt Context: Instructs JSON extraction (Overview/News/TimeSeries, Date: {date.today().isoformat()})")
    print("-" * 20)

    last_error = None
    extracted_json = None
    # Count first attempt only - handled outside cache later
    # api_counts["llm"] += 1
    # print(f"  [API Call] Incrementing LLM count to: {api_counts['llm']} (Attempt 1)")

    for attempt in range(LLM_MAX_RETRIES + 1):
        # Increment LLM count only on the *first* actual attempt to call
        if attempt == 0:
            api_counts["llm"] += 1
            print(f"  [API Call] Incrementing LLM count to: {api_counts['llm']} (Attempt {attempt + 1})")

        print(f"  LLM Call Attempt {attempt + 1}/{LLM_MAX_RETRIES + 1}")
        if attempt > 0:
            print(f"  Waiting {LLM_RETRY_DELAY_SECONDS}s before retrying...")
            time.sleep(LLM_RETRY_DELAY_SECONDS)
            # Do not increment count on retries

        raw_response_text = None
        response_status_code = None
        raw_output = None

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": getenv("YOUR_SITE_URL", "http://localhost"),
                    "X-Title": getenv("YOUR_APP_NAME", "Stock Chatbot v2"),
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": messages,
                    "max_tokens": 400,
                    "temperature": 0.1,
                },
                timeout=45
            )
            response_status_code = response.status_code
            raw_response_text = response.text

            print(f"--- LLM API Response (Attempt {attempt + 1}) ---")
            print(f"Status Code: {response_status_code}")
            # print(f"Raw Body Text:\n<<<\n{raw_response_text[:1000]}{'...' if len(raw_response_text) > 1000 else ''}\n>>>") # Less verbose logging
            print("-" * 20)

            response.raise_for_status()
            result = response.json()

            if "choices" not in result or not result["choices"] or "message" not in result["choices"][0]:
                error_info = result.get('error', {})
                error_msg = error_info.get('message', 'API OK but response lacks choices/message structure.')
                print(f"API Error (parsed JSON): {error_msg}")
                last_error = RuntimeError(f"LLM API call successful but response structure invalid: {error_msg}")
                continue

            raw_output = result["choices"][0]["message"].get("content")
            if not raw_output or raw_output.isspace():
                 print(f"Warning: LLM returned empty or whitespace content.")
                 last_error = ValueError("LLM returned empty content.")
                 continue

            print(f"Attempting to extract JSON from LLM content...")
            extracted_json = extract_json_from_text(raw_output)

            # --- Validation based on request_type ---
            if not isinstance(extracted_json, dict):
                 last_error = ValueError("Extracted content is not a dictionary."); extracted_json = None; continue
            if "request_type" not in extracted_json:
                 last_error = ValueError("Extracted JSON missing 'request_type'."); extracted_json = None; continue
            if extracted_json.get("symbol", "").upper() == "UNKNOWN" or not extracted_json.get("symbol"):
                 last_error = ValueError("Stock symbol extraction failed or returned UNKNOWN."); extracted_json = None; continue

            req_type = extracted_json["request_type"]
            print(f"  Identified request_type: {req_type}")

            if req_type == "time_series":
                required_keys = ["symbol", "date_from", "date_to", "interval"]
                missing_keys = [k for k in required_keys if k not in extracted_json]
                if missing_keys:
                    last_error = ValueError(f"Time series request missing keys: {missing_keys}"); extracted_json = None; continue
                valid_intervals = ['1min', '5min', '15min', '30min', '60min', 'daily', 'weekly', 'monthly']
                if extracted_json.get("interval") not in valid_intervals:
                    print(f"Warning: Invalid interval '{extracted_json.get('interval')}' for time series. Defaulting to 'daily'.")
                    extracted_json["interval"] = "daily"
                 # Basic date format validation (optional but good)
                try:
                     datetime.strptime(extracted_json["date_from"], "%Y-%m-%d")
                     datetime.strptime(extracted_json["date_to"], "%Y-%m-%d")
                except ValueError:
                     last_error = ValueError("Invalid date format in time_series request."); extracted_json = None; continue

            elif req_type not in ["overview", "news"]:
                 last_error = ValueError(f"Unknown request_type: {req_type}"); extracted_json = None; continue

            print("Successfully extracted and validated JSON.")
            break # Exit retry loop

        # --- Error Handling ---
        except requests.exceptions.Timeout as e:
             print(f"Error: LLM API call timed out (Attempt {attempt + 1})")
             last_error = RuntimeError(f"LLM API call timed out: {e}")
        except requests.exceptions.RequestException as e:
            print(f"Error calling LLM API (Attempt {attempt + 1}): {e}")
            if e.response is not None: print(f"  Status: {e.response.status_code}, Body: {e.response.text[:200]}...")
            last_error = RuntimeError(f"LLM API call failed: {e}")
        except json.JSONDecodeError as e:
            print(f"Error: LLM API response not valid JSON (Attempt {attempt + 1}). Status: {response_status_code}. Error: {e}")
            if 'raw_response_text' in locals(): print(f"Raw Text was: {raw_response_text[:200]}...")
            last_error = RuntimeError(f"LLM API response not valid JSON (status {response_status_code})")
        except ValueError as e: # Catch JSON extraction/validation errors
            print(f"Error processing LLM output or validating JSON (Attempt {attempt + 1}): {e}")
            if 'raw_output' in locals() and raw_output: print(f"Raw output was: '{raw_output[:200]}...'")
            last_error = e
        except Exception as e:
            print(f"An unexpected error occurred during LLM processing (Attempt {attempt + 1}): {e}")
            import traceback; traceback.print_exc()
            last_error = e
            break # Break on truly unexpected errors

    # After the loop
    if extracted_json:
        return extracted_json
    else:
        print(f"LLM call failed after {LLM_MAX_RETRIES + 1} attempts.")
        raise last_error or RuntimeError("LLM failed to produce valid JSON after multiple retries.")


def build_request_json(query: str, api_counts: dict) -> dict:
    """ Transforms query to JSON via LLM and performs initial validation. """
    print(f"\nStep 1: Transforming query to request JSON via LLM...")
    llm_json = transform_query_to_json(query, api_counts)
    print(f"LLM Result (JSON): {json.dumps(llm_json)}")

    req_type = llm_json.get("request_type")
    if not req_type or req_type not in ["time_series", "overview", "news"]:
         raise ValueError(f"Invalid or missing request_type from LLM: {req_type}")
    if not llm_json.get("symbol") or llm_json["symbol"] == "UNKNOWN":
        raise ValueError("LLM did not return a valid stock symbol.")

    print(f"\nStep 2: JSON parsed. Request Type: '{req_type}', Symbol: '{llm_json['symbol']}'. Ready for API call.")
    return llm_json

# --- Alpha Vantage API Call Functions ---

# Internal function without cache - performs the actual API call and retry logic
def _call_alpha_vantage(params: dict, api_key_name: str, api_counts: dict) -> dict:
    """ Generic helper to call Alpha Vantage API with retries. """
    last_error = None
    function_name = params.get("function", "UNKNOWN_FUNCTION")
    symbol = params.get("symbol", params.get("tickers", "N/A")) # Get symbol for logging

    # Retry loop
    for attempt in range(STOCK_API_MAX_RETRIES + 1):
        # Note: api_counts is incremented *before* the cached call wrapper now
        if attempt > 0 :
            print(f"    Waiting {STOCK_API_RETRY_DELAY_SECONDS}s before retrying Alpha Vantage call ({function_name}, Attempt {attempt+1})...")
            time.sleep(STOCK_API_RETRY_DELAY_SECONDS)
        else:
             # Log the first attempt clearly
             print(f"    Attempting Alpha Vantage API call (Function: {function_name}, Symbol: {symbol}, Attempt {attempt+1})...")

        try:
            # The actual external HTTP request happens here
            response = requests.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=60)
            response.raise_for_status()
            raw_data = response.json()

            # --- Check for Alpha Vantage Specific Errors/Info ---
            if not raw_data:
                 print(f"    Warning: Alpha Vantage returned an empty response for {function_name} (Attempt {attempt+1}).")
                 last_error = ValueError(f"Alpha Vantage returned empty response for {function_name}")
                 continue # Retry potentially empty response

            if "Error Message" in raw_data:
                error_msg = raw_data["Error Message"]
                print(f"    Error from Alpha Vantage API: {error_msg} (Attempt {attempt+1})")
                if "Invalid API call" in error_msg or "invalid symbol" in error_msg.lower():
                     raise ValueError(f"Alpha Vantage API Error (No Retry / {function_name}): {error_msg}") # Non-retriable
                last_error = ValueError(f"Alpha Vantage API Error ({function_name}): {error_msg}")
                continue # Retry other errors

            if "Information" in raw_data:
                 info_msg = raw_data["Information"]
                 print(f"    Information from Alpha Vantage API: {info_msg} (Attempt {attempt+1})")
                 if "call frequency" in info_msg.lower() or "limit" in info_msg.lower():
                     last_error = RuntimeError(f"Alpha Vantage Rate Limit Info ({function_name}): {info_msg}")
                     print(f"    Rate limit likely hit. Retrying after delay...")
                     continue # Retry rate limits
                 # Handle cases where 'Information' is present but no useful data (let callers decide)

            # --- Success ---
            print(f"    Successfully fetched data for {function_name} (Attempt {attempt + 1}).")
            return raw_data # Return the full successful response

        # --- Error Handling ---
        except requests.exceptions.Timeout as e:
             print(f"    Error: Alpha Vantage API call timed out ({function_name}, Attempt {attempt + 1})")
             last_error = RuntimeError(f"Alpha Vantage API call timed out ({function_name}): {e}")
        except requests.exceptions.RequestException as e:
            print(f"    Error calling Alpha Vantage API ({function_name}, Attempt {attempt + 1}): {e}")
            if e.response is not None: print(f"      Status: {e.response.status_code}, Body: {e.response.text[:200]}...")
            last_error = RuntimeError(f"Alpha Vantage API call failed ({function_name}): {e}")
        except json.JSONDecodeError as e:
             print(f"    Error: Alpha Vantage API response not valid JSON ({function_name}, Attempt {attempt + 1}). Status: {response.status_code if 'response' in locals() else 'Unknown'}")
             if 'response' in locals(): print(f"    Raw Text: {response.text[:200]}...")
             last_error = RuntimeError(f"Alpha Vantage API response not valid JSON ({function_name}).")
        except ValueError as e: # Catch our specific ValueErrors (like invalid symbol)
             print(f"    ValueError during Alpha Vantage call/check ({function_name}, Attempt {attempt + 1}): {e}")
             last_error = e
             if "No Retry" in str(e): # Check for non-retriable marker
                 print("    Error marked as non-retriable. Aborting fetch.")
                 break # Exit loop immediately
             # Else continue loop for other ValueErrors
        except Exception as e:
            print(f"    An unexpected error occurred during AV fetch ({function_name}, Attempt {attempt + 1}): {e}")
            import traceback; traceback.print_exc()
            last_error = e
            break # Break on unexpected errors

    # --- After the Loop ---
    print(f"API call failed for {function_name} after {STOCK_API_MAX_RETRIES + 1} attempts.")
    raise last_error or RuntimeError(f"Failed to fetch data using {function_name} after multiple retries.")


# Cached wrapper function for Streamlit
@st.cache_data(ttl=3600, show_spinner=False) # Cache for 1 hour, hide default spinner
def _call_alpha_vantage_cached(_params_tuple: tuple, api_key_name: str) -> dict:
    """ Cached wrapper for _call_alpha_vantage.
        Uses tuple of params as cache key.
        api_counts dict cannot be passed directly here for reliable updates within cache.
    """
    # NOTE: This function is now simpler. It converts the tuple back to a dict
    # and calls the *non-cached* internal function. The api_counts dict is
    # managed *outside* this cached function.
    params = dict(_params_tuple)
    print(f"    Executing _call_alpha_vantage_cached -> _call_alpha_vantage for function: {params.get('function')} (Cache miss or first call)")
    # We create a temporary count dict here just to pass to the underlying function,
    # it doesn't affect the global count state reliably due to caching.
    temp_api_counts = {api_key_name: 0}
    return _call_alpha_vantage(params, api_key_name, temp_api_counts)


# --- Public Fetch Functions (Modified to use cache) ---

def fetch_stock_time_series(request_json: dict, api_counts: dict) -> dict:
    """ Fetches Time Series data from Alpha Vantage using cache. """
    symbol = request_json["symbol"]
    interval = request_json["interval"]
    date_from = request_json["date_from"]
    date_to = request_json["date_to"]
    api_key_name = "alpha_vantage"

    print(f"\nStep 3: Fetching Time Series data for {symbol} (Interval: {interval}, From: {date_from}, To: {date_to})...")
    params = { "symbol": symbol, "apikey": ALPHA_VANTAGE_API_KEY, "datatype": "json" }

    is_intraday = interval in ['1min', '5min', '15min', '30min', '60min']
    if is_intraday: av_function = "TIME_SERIES_INTRADAY"; params["interval"] = interval; params["outputsize"] = "full"
    elif interval == 'daily': av_function = "TIME_SERIES_DAILY_ADJUSTED"; params["outputsize"] = "full"
    elif interval == 'weekly': av_function = "TIME_SERIES_WEEKLY_ADJUSTED"
    elif interval == 'monthly': av_function = "TIME_SERIES_MONTHLY_ADJUSTED"
    else: raise ValueError(f"Unsupported interval for Time Series: {interval}")
    params["function"] = av_function
    print(f"  Alpha Vantage Function: {av_function}")

    try:
        # Increment count *before* the cached call attempt
        api_counts[api_key_name] += 1
        print(f"    [API Call] Incrementing {api_key_name} count to: {api_counts[api_key_name]} (before cached call)")
        # Convert params dict to sorted tuple for hashable cache key
        params_tuple = tuple(sorted(params.items()))
        # Call the cached function wrapper
        raw_data = _call_alpha_vantage_cached(params_tuple, api_key_name) # Pass tuple

        # --- Process raw_data (same as before) ---
        time_series_key = next((k for k in raw_data if k.startswith("Time Series")), None)
        if not time_series_key or not isinstance(raw_data.get(time_series_key), dict):
             if "Information" in raw_data and not time_series_key: raise ValueError(f"No time series data found. API Info: {raw_data['Information']}")
             raise ValueError("Could not find valid time series data block in Alpha Vantage response.")
        time_series = raw_data.get(time_series_key, {})
        if not time_series: print(f"    Warning: Alpha Vantage returned an empty time series for {symbol} ({interval}).")

        print("Step 4: Time Series data fetching complete.")
        return {
            "query_details": {**request_json, "api_function": av_function, "fetched_data_key": time_series_key},
            "metadata": raw_data.get("Meta Data"),
            "time_series_key": time_series_key,
            "time_series": time_series
        }
    except (ValueError, RuntimeError) as e:
         print(f"Error during time series fetch/processing: {e}")
         raise RuntimeError(f"Failed to get valid time series data for {symbol}: {e}") from e
    except Exception as e:
        print(f"Unexpected error during time series fetch for {symbol}: {e}")
        raise


def fetch_stock_overview(request_json: dict, api_counts: dict) -> dict:
    """ Fetches Company Overview data using cache. """
    symbol = request_json["symbol"]
    api_key_name = "alpha_vantage"
    print(f"\nStep 3: Fetching Company Overview data for {symbol}...")
    params = { "function": "OVERVIEW", "symbol": symbol, "apikey": ALPHA_VANTAGE_API_KEY }

    try:
        # Increment count and call cached function
        api_counts[api_key_name] += 1
        print(f"    [API Call] Incrementing {api_key_name} count to: {api_counts[api_key_name]} (before cached call)")
        params_tuple = tuple(sorted(params.items()))
        raw_data = _call_alpha_vantage_cached(params_tuple, api_key_name)

        # --- Process raw_data (same as before) ---
        if not raw_data or (len(raw_data) == 1 and raw_data.get("Symbol") == symbol):
             raise ValueError(f"No overview data found for symbol '{symbol}'. It might be invalid or not supported.")

        print("Step 4: Company Overview data fetching complete.")
        return {
            "query_details": {**request_json, "api_function": "OVERVIEW"},
            "overview_data": raw_data
        }
    except (ValueError, RuntimeError) as e:
         print(f"Error during overview fetch: {e}")
         raise RuntimeError(f"Failed to get overview data for {symbol}: {e}") from e
    except Exception as e:
        print(f"Unexpected error during overview fetch for {symbol}: {e}")
        raise


def fetch_stock_news(request_json: dict, api_counts: dict) -> dict:
    """ Fetches News & Sentiment data using cache. """
    symbol = request_json["symbol"]
    api_key_name = "alpha_vantage"
    news_limit = request_json.get("limit", 15)
    print(f"\nStep 3: Fetching News & Sentiment data for {symbol} (Limit: {news_limit})...")
    params = { "function": "NEWS_SENTIMENT", "tickers": symbol, "apikey": ALPHA_VANTAGE_API_KEY, "limit": news_limit, "sort": "LATEST" }

    try:
        # Increment count and call cached function
        api_counts[api_key_name] += 1
        print(f"    [API Call] Incrementing {api_key_name} count to: {api_counts[api_key_name]} (before cached call)")
        params_tuple = tuple(sorted(params.items()))
        raw_data = _call_alpha_vantage_cached(params_tuple, api_key_name)

        # --- Process raw_data (same as before) ---
        news_feed = []
        if "feed" not in raw_data or not isinstance(raw_data.get("feed"), list):
            info_msg = raw_data.get("Information", "No specific info provided.")
            if "No articles found" in info_msg or ("feed" in raw_data and isinstance(raw_data["feed"], list) and not raw_data["feed"]):
                 print(f"    Information: No news articles found for {symbol} with current filters.")
                 # Keep news_feed as empty list
            else:
                raise ValueError(f"Could not find valid 'feed' data in News API response. Info: {info_msg}")
        else:
            news_feed = raw_data["feed"]

        print(f"Step 4: News & Sentiment data fetching complete (Found {len(news_feed)} articles).")
        return {
            "query_details": {**request_json, "api_function": "NEWS_SENTIMENT", "limit": news_limit},
            "news_feed": news_feed
        }
    except (ValueError, RuntimeError) as e:
         print(f"Error during news fetch: {e}")
         raise RuntimeError(f"Failed to get news data for {symbol}: {e}") from e
    except Exception as e:
        print(f"Unexpected error during news fetch for {symbol}: {e}")
        raise

# --- Data Processing Functions ---

def filter_stock_data_by_date(time_series_data: dict, date_from_str: str, date_to_str: str) -> dict:
    """ Filters Time Series data by date range. """
    if not time_series_data or "time_series" not in time_series_data or not time_series_data["time_series"]:
        print("  No time series data to filter by date.")
        return time_series_data

    print(f"Step 5: Filtering time series data by date range ({date_from_str} to {date_to_str})...")
    original_ts = time_series_data["time_series"]
    filtered_ts = {}

    try:
        start_date = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_to_str, "%Y-%m-%d").date()
    except ValueError as e:
        print(f"  Warning: Invalid date format for filtering '{date_from_str}' or '{date_to_str}': {e}. Skipping filtering.")
        return time_series_data

    count_original = len(original_ts)
    count_filtered = 0

    for timestamp_str, data_point in original_ts.items():
        try:
            # Handle both date and datetime strings from AV
            current_date = pd.to_datetime(timestamp_str).date() # Use Pandas for robust parsing
            if start_date <= current_date <= end_date:
                filtered_ts[timestamp_str] = data_point
                count_filtered += 1
        except (ValueError, TypeError):
            print(f"  Warning: Could not parse timestamp '{timestamp_str}' for date filtering. Skipping.")
            continue

    print(f"  Filtering complete. Kept {count_filtered} out of {count_original} data points.")

    time_series_data["time_series"] = filtered_ts
    if "query_details" in time_series_data:
        time_series_data["query_details"]["filtering_applied"] = "date_range"
        time_series_data["query_details"]["filtered_points_count"] = count_filtered

    return time_series_data


def process_time_series_data(stock_data: dict, request_json: dict) -> dict:
    """ Processes fetched time series data (currently just date filtering). """
    print(f"\nStep 5 & 6: Processing fetched Time Series data...") # Conceptual steps

    if not stock_data:
        print("  No time series data to process.")
        return stock_data

    # Apply date filtering if dates are valid in the request
    if request_json.get("date_from") and request_json.get("date_to"):
         filtered_data = filter_stock_data_by_date(
             stock_data,
             request_json["date_from"],
             request_json["date_to"]
         )
    else:
         print("  Skipping date filtering due to missing dates in request.")
         filtered_data = stock_data # No filtering if dates aren't provided

    print("Step 7: Time Series data processing complete.")
    return filtered_data


# --- Console Print Functions (Optional - Handled by Streamlit app.py) ---
# These can be kept for debugging or removed if only running via Streamlit.

# def print_time_series_summary(stock_data):
#     """ Prints a summary of the fetched Time Series stock data to console. """
#     print("\n--- Stock Time Series Summary (Console) ---")
#     # ... (implementation similar to previous versions) ...

# def print_stock_overview(overview_result: dict):
#     """ Prints a formatted summary of the Company Overview data to console. """
#     print("\n--- Stock Overview Summary (Console) ---")
#      # ... (implementation similar to previous versions) ...

# def print_stock_news(news_result: dict):
#     """ Prints a summary of the fetched Stock News to console. """
#     print("\n--- Stock News Summary (Console) ---")
#     # ... (implementation similar to previous versions) ...

# --- END OF FILE chatbot.py ---