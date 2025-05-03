# --- START OF FILE app.py ---

import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots # Import pro subploty
from datetime import datetime
from os import getenv
import numpy as np

# Importy potřebných knihoven a vlastního modulu
from chatbot import (
    build_request_json,
    fetch_stock_time_series,
    process_time_series_data,
    fetch_stock_overview,
    fetch_stock_news,
    create_mock_stock_data # Funkce pro generování testovacích (mock) dat
)

# --- Konfigurace stránky a globální proměnné ---
st.set_page_config(page_title="Stock AI Assistant", layout="wide")
st.title("📈 Stock AI Assistant")
st.caption(f"Powered by LLM ({getenv('OPENROUTER_MODEL', 'Unknown Model')}) and Alpha Vantage API")

# API klíče se načítají z prostředí (viz chatbot.py)
# Zobrazíme varování, pokud klíče chybí, ale neblokujeme MOCK dotazy
api_key_warning = False
if not getenv("ALPHA_VANTAGE_API_KEY"):
    st.warning("Varování: ALPHA_VANTAGE_API_KEY není nastaven. Budou fungovat pouze MOCK dotazy.")
    api_key_warning = True
if not getenv("OPENROUTER_API_KEY"):
    st.warning("Varování: OPENROUTER_API_KEY není nastaven. Budou fungovat pouze MOCK dotazy.")
    api_key_warning = True

# Inicializace session state pro uchování stavu mezi interakcemi
if 'total_api_counts' not in st.session_state:
    st.session_state.total_api_counts = {"llm": 0, "alpha_vantage": 0} # Celkové počty volání
if 'query_api_counts' not in st.session_state:
    st.session_state.query_api_counts = {"llm": 0, "alpha_vantage": 0} # Počty pro aktuální dotaz
if 'last_result' not in st.session_state:
    st.session_state.last_result = None # Poslední získaný výsledek
if 'last_request_json' not in st.session_state:
     st.session_state.last_request_json = None # Poslední vygenerovaný JSON požadavek


# --- Funkce pro zobrazení výsledků ---

def display_time_series(result_data):
    """
    Zobrazí časovou řadu (graf) a související informace.
    Funkce zpracuje data, vypočítá indikátory (S/R, Fibonacci)
    a vykreslí interaktivní graf pomocí Plotly. Skrývá víkendy/svátky.
    """
    if not result_data or "time_series" not in result_data or not result_data.get("time_series"):
        st.warning("Nebyly nalezeny žádné časové řady pro zadaná kritéria.")
        return

    ts_data = result_data["time_series"]
    metadata = result_data.get("metadata", {})
    query_details = result_data.get("query_details", {})
    symbol = query_details.get('symbol', metadata.get('2. Symbol', 'N/A'))
    is_mock = "MOCK_" in query_details.get("api_function", "") # Zjistíme, zda jde o mock data

    st.subheader(f"Time Series Data for {symbol}" + (" (MOCK)" if is_mock else ""))
    st.write(f"**Interval:** {query_details.get('interval', 'N/A')}")
    st.write(f"**Požadovaný rozsah:** {query_details.get('date_from')} to {query_details.get('date_to')}")

    if not ts_data:
        st.info("V tomto rozsahu nejsou žádná data k zobrazení v grafu.")
        return

    # Převod na Pandas DataFrame pro snadnější manipulaci a vykreslení
    try:
        df = pd.DataFrame.from_dict(ts_data, orient='index')
        df.index = pd.to_datetime(df.index) # Index jako datum a čas
        df = df.sort_index() # Seřadit podle data

        # Přejmenování sloupců (odstranění prefixů jako '1. open')
        rename_map = {col: col.split('. ')[1].replace(' ', '_') for col in df.columns if '. ' in col}
        df.rename(columns=rename_map, inplace=True)

        # Převod klíčových sloupců na numerické typy, neplatné hodnoty nahradit NaN
        numeric_cols = ['open', 'high', 'low', 'close', 'adjusted_close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Odstranění řádků s chybějící 'close' hodnotou (nutné pro graf a výpočty)
        df.dropna(subset=['close'], inplace=True)

        # Kontrola, zda po čištění zůstala nějaká data
        if df.empty:
            st.warning("Po zpracování nezůstala žádná platná data pro zobrazení.")
            return

        st.write(f"**Zobrazeno datových bodů (po čištění):** {len(df)}")

    except Exception as e:
        st.error(f"Chyba při přípravě dat pro graf: {e}")
        st.dataframe(ts_data) # Zobrazit alespoň surová data
        return

    # --- Výpočet Indikátorů ---
    # Jednoduchý Support / Resistance (minimum a maximum v období)
    period_low = df['low'].min()
    period_high = df['high'].max()

    # Fibonacci Retracements (počítáno z high a low daného období)
    fib_levels = []
    fib_range = period_high - period_low
    if fib_range > 0: # Výpočet má smysl jen pokud existuje cenový rozsah
        # Standardní úrovně (od High dolů)
        fib_levels.append({'level': 0.0, 'price': period_high, 'label': '100.0% (High)'})
        fib_levels.append({'level': 0.236, 'price': period_high - fib_range * 0.236, 'label': '76.4%'})
        fib_levels.append({'level': 0.382, 'price': period_high - fib_range * 0.382, 'label': '61.8%'})
        fib_levels.append({'level': 0.5, 'price': period_high - fib_range * 0.5, 'label': '50.0%'})
        fib_levels.append({'level': 0.618, 'price': period_high - fib_range * 0.618, 'label': '38.2%'})
        # fib_levels.append({'level': 0.764, 'price': period_high - fib_range * 0.764, 'label': '23.6%'}) # Méně častá úroveň
        fib_levels.append({'level': 1.0, 'price': period_low, 'label': '0.0% (Low)'})

    # --- UI pro volitelné indikátory ---
    st.subheader("Indikátory Grafu")
    cols = st.columns(4) # Rozložení checkboxů do sloupců
    with cols[0]:
        st.write("**Objem:**")
        show_volume = st.checkbox("Zobrazit objem", value=True) # Defaultně zapnuto
    with cols[1]:
        st.write("**Úrovně:**")
        show_support = st.checkbox("Support (Min)", value=False)
        show_resistance = st.checkbox("Resistance (Max)", value=False)
    with cols[2]:
        st.write("**Fibonacci:**")
        show_fibonacci = st.checkbox("Retracement", value=False)

    # --- Vytvoření grafu pomocí Plotly Subplots ---
    st.subheader("Graf")

    # Figura se dvěma subploty (cena nahoře, objem dole)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, # Malá mezera mezi grafy
                        row_heights=[0.75, 0.25]) # Poměr výšky grafů

    # 1. Hlavní graf (Cena - Candlestick nebo Line) v horním subplotu
    if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        # Máme OHLC data, použijeme Candlestick
        fig.add_trace(go.Candlestick(x=df.index,
                                     open=df['open'],
                                     high=df['high'],
                                     low=df['low'],
                                     close=df['close'],
                                     name=symbol),
                      row=1, col=1)
    elif 'close' in df.columns:
         # Máme jen 'close', použijeme čárový graf
         fig.add_trace(go.Scatter(x=df.index, y=df['close'], mode='lines', name='Close Price'),
                       row=1, col=1)
    else:
         # Nemáme ani 'close' (nemělo by nastat díky df.dropna), zobrazíme varování
         st.warning("Data neobsahují 'close' sloupec pro zobrazení grafu.")
         st.dataframe(df)
         return

    # 2. Graf Objemu (pokud je zapnutý a data existují) ve spodním subplotu
    if show_volume and 'volume' in df.columns:
         # Barva sloupce objemu podle růstu/poklesu ceny
         colors = ['green' if row['close'] >= row['open'] else 'red' for index, row in df.iterrows()]
         fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color=colors, showlegend=False), # Legenda pro objem není nutná
                       row=2, col=1)
         fig.update_yaxes(title_text="Volume", row=2, col=1) # Popisek osy Y pro objem


    # 3. Přidání Support/Resistance (pokud jsou zapnuté) do horního subplotu
    line_color_support = 'rgba(0, 128, 0, 0.7)' # Poloprůhledná zelená
    line_color_resistance = 'rgba(255, 0, 0, 0.7)' # Poloprůhledná červená

    if show_support:
         fig.add_trace(go.Scatter(x=df.index, y=[period_low]*len(df), # Horizontální čára
                                   mode='lines',
                                   line=dict(color=line_color_support, width=1.5, dash='dash'),
                                   name=f'Support {period_low:.2f}',
                                   showlegend=True), # Zobrazit v legendě
                       row=1, col=1)

    if show_resistance:
         fig.add_trace(go.Scatter(x=df.index, y=[period_high]*len(df), # Horizontální čára
                                   mode='lines',
                                   line=dict(color=line_color_resistance, width=1.5, dash='dash'),
                                   name=f'Resistance {period_high:.2f}',
                                   showlegend=True),
                       row=1, col=1)


    # 4. Přidání Fibonacci Retracements (pokud jsou zapnuté) do horního subplotu
    if show_fibonacci and fib_levels:
        fib_colors = ['rgba(153, 50, 204, 0.7)', 'rgba(70, 130, 180, 0.7)', 'rgba(255, 165, 0, 0.7)', 'rgba(50, 205, 50, 0.7)', 'rgba(255, 69, 0, 0.7)']
        color_idx = 0
        for level_data in fib_levels:
             # Přeskakujeme 0% a 100% (High/Low), ty jsou reprezentovány S/R
             if level_data['level'] == 0.0 or level_data['level'] == 1.0: continue

             fig.add_trace(go.Scatter(x=df.index, y=[level_data['price']]*len(df),
                                      mode='lines',
                                      line=dict(color=fib_colors[color_idx % len(fib_colors)], width=1, dash='dot'),
                                      name=f"Fib {level_data['label'].split(' ')[0]} ({level_data['price']:.2f})", # Kratší název pro legendu
                                      showlegend=True),
                           row=1, col=1)
             color_idx += 1

    # --- Nastavení vzhledu (Layoutu) grafu ---
    fig.update_layout(
        title=f'{symbol} Stock Price ({query_details.get("interval", "N/A")})' + (" (MOCK)" if is_mock else ""),
        xaxis_title=None, # Společná osa X nepotřebuje název nahoře
        yaxis_title='Price (USD)', # Popisek horní osy Y
        height=700, # Celková výška grafu
        legend_title_text='Legenda',
        xaxis_rangeslider_visible=False, # Skrytí defaultního range slideru
        xaxis2_rangeslider_visible=False, # Skrytí i pro spodní graf
        hovermode="x unified", # Zobrazí tooltip pro všechny stopy na dané X pozici
        margin=dict(l=50, r=50, t=80, b=50) # Okraje grafu
    )

    # Skrytí víkendů a svátků na ose X (aplikuje se na sdílenou osu)
    fig.update_xaxes(rangebreaks=[
        dict(bounds=["sat", "mon"]), # Skryje sobotu a neděli
        # dict(values=["YYYY-MM-DD", ...]) # Zde lze přidat konkrétní data svátků
    ], row=1, col=1) # Aplikujeme na osu prvního (hlavního) subplotu

    # Zajistíme zobrazení popisků osy X na obou subplotech
    fig.update_xaxes(showticklabels=True, row=1, col=1)
    fig.update_xaxes(showticklabels=True, row=2, col=1)

    # Popisek osy X zobrazíme jen u spodního grafu
    fig.update_xaxes(title_text=None, row=1, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=1)

    # Zobrazení grafu ve Streamlit aplikaci
    st.plotly_chart(fig, use_container_width=True)

    # Volitelně zobrazit data v tabulce pod grafem
    with st.expander("Zobrazit data v tabulce"):
        df_display = df.copy()
        # Formátování čísel pro lepší čitelnost v tabulce
        numeric_cols_to_format = df_display.select_dtypes(include=np.number).columns
        for col in numeric_cols_to_format:
             if col in ['open','high','low','close','adjusted_close']:
                 # Ceny na 2 desetinná místa
                 df_display[col] = df_display[col].map('{:.2f}'.format)
             elif col == 'volume':
                  # Objem s oddělovačem tisíců
                  df_display[col] = df_display[col].map('{:,.0f}'.format)

        st.dataframe(df_display)


def display_overview(result_data):
    """ Zobrazí přehledové informace o společnosti (Overview). """
    if not result_data or "overview_data" not in result_data or not result_data["overview_data"]:
        st.warning("Nebyly nalezeny žádné informace (Overview) pro tento symbol.")
        return

    data = result_data["overview_data"]
    symbol = data.get('Symbol', 'N/A')
    st.subheader(f"Company Overview for {symbol}")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Symbol", data.get('Symbol', 'N/A'))
        st.write(f"**Name:** {data.get('Name', 'N/A')}")
        st.write(f"**Industry:** {data.get('Industry', 'N/A')}")
        st.write(f"**Sector:** {data.get('Sector', 'N/A')}")
        st.write(f"**CEO:** {data.get('CEO', 'N/A')}")

    with col2:
        # Pomocná funkce pro formátování čísel (měna, velká čísla)
        def format_metric(value, is_currency=False, is_large_num=False):
             if value is None or value == 'None' or value == '-': return "N/A"
             try:
                 num = float(value)
                 if is_large_num: # Převod na T, B, M
                     if abs(num) >= 1e12: return f"{num / 1e12:.2f}T"
                     if abs(num) >= 1e9: return f"{num / 1e9:.2f}B"
                     if abs(num) >= 1e6: return f"{num / 1e6:.2f}M"
                     return f"{num:,.0f}" # Bez des. míst u velkých čísel pod milion
                 if is_currency: return f"${num:,.2f}" # Formát měny
                 return f"{num:.2f}" # Běžné číslo na 2 des. místa
             except (ValueError, TypeError): return str(value) # Pokud není číslo, vrátit jako string

        st.metric("Market Cap", format_metric(data.get('MarketCapitalization'), is_large_num=True))
        st.metric("P/E Ratio", format_metric(data.get('PERatio')))
        dividend_yield = data.get('DividendYield')
        # Dividendový výnos zobrazit v procentech
        st.metric("Dividend Yield", f"{format_metric(float(dividend_yield) * 100)}%" if dividend_yield not in [None, 'None', '0', 0, '-'] else "N/A")
        st.metric("EPS (TTM)", format_metric(data.get('EPS')))


    st.write(f"**Description:** {data.get('Description', 'N/A')}")

    # Další finanční metriky v rozbalovacím bloku
    with st.expander("Další metriky"):
         st.write(f"**Forward P/E:** {format_metric(data.get('ForwardPE'))}")
         st.write(f"**PEG Ratio:** {format_metric(data.get('PEGRatio'))}")
         st.write(f"**Price/Sales (TTM):** {format_metric(data.get('PriceToSalesRatioTTM'))}")
         st.write(f"**Price/Book:** {format_metric(data.get('PriceToBookRatio'))}")
         roe = data.get('ReturnOnEquityTTM')
         # ROE zobrazit v procentech
         st.write(f"**ROE (TTM):** {format_metric(float(roe) * 100)}%" if roe not in [None, 'None', '-'] else "N/A")
         st.write(f"**52 Week High:** {format_metric(data.get('52WeekHigh'), is_currency=True)}")
         st.write(f"**52 Week Low:** {format_metric(data.get('52WeekLow'), is_currency=True)}")
         st.write(f"**Analyst Target Price:** {format_metric(data.get('AnalystTargetPrice'), is_currency=True)}")


def display_news(result_data):
    """ Zobrazí seznam nedávných zpráv (News). """
    if not result_data or "news_feed" not in result_data:
        st.warning("Nebyly nalezeny žádné zprávy pro tento symbol.")
        return

    feed = result_data["news_feed"]
    query_details = result_data.get("query_details", {})
    symbol = query_details.get('symbol', 'N/A')

    st.subheader(f"Recent News for {symbol}")
    st.write(f"Nalezeno článků: {len(feed)}")

    if not feed:
        st.info("Žádné články nenalezeny.")
        return

    # Projít a zobrazit jednotlivé články
    for i, article in enumerate(feed):
        with st.container(): # Oddělení článků pomocí containeru
            st.markdown(f"**{i+1}. {article.get('title', 'No Title')}**")
            col1, col2 = st.columns([3, 1]) # Rozložení na text a metadata
            with col1:
                st.write(f"Zdroj: {article.get('source', 'N/A')} ({article.get('source_domain', 'N/A')})")
                st.caption(f"Shrnutí: {article.get('summary', 'N/A')}")
                st.write(f"[Odkaz na článek]({article.get('url', '#')})")
            with col2:
                 # Zpracování a formátování času publikace
                 time_str = article.get('time_published', '')
                 if time_str and len(time_str) >= 13: # Základní kontrola formátu
                     try:
                         # Standardní formát Alpha Vantage
                         dt_obj = datetime.strptime(time_str, '%Y%m%dT%H%M%S')
                         st.write(f"Publikováno: {dt_obj.strftime('%Y-%m-%d %H:%M')}")
                     except ValueError:
                         # Pokud formát nesedí, zobrazit původní řetězec
                         st.write(f"Publikováno: {time_str}")
                 else:
                      st.write(f"Publikováno: {time_str}") # Zobrazit krátký nebo prázdný řetězec

                 # Zobrazení sentimentu, pokud je k dispozici
                 s_label = article.get('overall_sentiment_label')
                 s_score_str = article.get('overall_sentiment_score')
                 s_score = None
                 if s_score_str: # Pokus o převod skóre na float
                    try: s_score = float(s_score_str)
                    except (ValueError, TypeError): pass

                 if s_label:
                     if s_score is not None:
                         st.write(f"Sentiment: {s_label} ({s_score:.2f})")
                     else:
                          st.write(f"Sentiment: {s_label}")
                 else:
                      st.write("Sentiment: N/A")
            st.divider() # Oddělovač mezi články


# --- UI Elementy (Vstupní pole a tlačítko) ---
query = st.text_input("Zadejte svůj dotaz na akcie:", placeholder="např. Apple stock price last month, MSFT overview, TSLA news, nebo MOCK_AAPL_DAILY")
submit_button = st.button("Odeslat dotaz")

# --- Hlavní logika zpracování dotazu ---
if submit_button and query:
    st.session_state.last_result = None # Vyčistit předchozí výsledek
    st.session_state.last_request_json = None # Vyčistit předchozí request
    st.session_state.query_api_counts = {"llm": 0, "alpha_vantage": 0} # Resetovat počty pro nový dotaz

    # Detekce MOCK dotazu (začíná na "MOCK_")
    is_mock_query = False
    mock_symbol = "MOCK"
    mock_interval = "daily"
    mock_points = 22 # Default: cca měsíc denních dat

    query_upper = query.strip().upper()
    if query_upper.startswith("MOCK_"):
        is_mock_query = True
        parts = query_upper.split('_')
        # Zpracování částí MOCK dotazu (SYMBOL, INTERVAL, POČET BODŮ)
        if len(parts) >= 2 and parts[1]: # Musí být alespoň MOCK_SYMBOL
            mock_symbol = parts[1]
        if len(parts) >= 3:
            potential_interval = parts[2].lower()
            if potential_interval in ["daily", "weekly", "monthly"]:
                mock_interval = potential_interval
                # Defaultní počet bodů podle intervalu
                if mock_interval == "daily": mock_points = 22
                elif mock_interval == "weekly": mock_points = 12 # Cca 3 měsíce
                elif mock_interval == "monthly": mock_points = 12 # Cca rok
            else: # Pokud třetí část není interval, zkusíme ji brát jako počet bodů
                try:
                    num_points = int(parts[2])
                    if num_points > 0: mock_points = num_points
                except ValueError: pass # Ignorovat, pokud není platné číslo

        if len(parts) >= 4: # Čtvrtá část může být počet bodů, pokud třetí byl interval
             try:
                 num_points = int(parts[3])
                 if num_points > 0: mock_points = num_points
             except ValueError: pass

        st.info(f"➡️ Generuji MOCK data pro symbol '{mock_symbol}', interval '{mock_interval}', počet bodů: {mock_points}")
        try:
            # Volání funkce pro generování mock dat
            mock_result, mock_request = create_mock_stock_data(
                symbol=mock_symbol,
                interval=mock_interval,
                days_or_months=mock_points
            )
            # Uložení vygenerovaných dat do session state
            st.session_state.last_result = mock_result
            st.session_state.last_request_json = mock_request
            st.session_state.query_api_counts = {"llm": 0, "alpha_vantage": 0} # Mock dotazy nevolají API

            # Pojistka: zajistit, že request_type je nastaven (měl by být z mock funkce)
            if "request_type" not in st.session_state.last_request_json:
                st.session_state.last_request_json["request_type"] = "time_series"

        except Exception as e:
             st.error(f"Chyba při generování MOCK dat: {e}")
             import traceback
             st.exception(traceback.format_exc()) # Zobrazit detail chyby
             st.session_state.last_result = None # Resetovat v případě chyby
             st.session_state.last_request_json = None

    # --- Zpracování skutečného (ne-MOCK) dotazu ---
    if not is_mock_query:
        # Zkontrolovat API klíče POUZE pokud nejde o mock dotaz
        if api_key_warning:
             st.error("API klíče nejsou nastaveny. Nelze zpracovat skutečný dotaz. Použijte MOCK_<SYMBOL> nebo nastavte klíče.")
             # Tady by mohl být st.stop() pro striktní zastavení
        else:
            # Klíče jsou v pořádku nebo nejsou potřeba (mock), pokračujeme
            with st.spinner("Zpracovávám dotaz... (Volám LLM a API)"):
                try:
                    # Krok 1 & 2: Převod dotazu na strukturovaný JSON pomocí LLM
                    request_json = build_request_json(query, st.session_state.query_api_counts)
                    st.session_state.last_request_json = request_json # Uložit pro zobrazení/debug

                    request_type = request_json.get("request_type")
                    result_data = None

                    # Krok 3 & 4: Volání příslušné funkce na základě typu požadavku z LLM
                    if request_type == "time_series":
                        raw_stock_data = fetch_stock_time_series(request_json, st.session_state.query_api_counts)
                        # Krok 5, 6, 7: Zpracování a filtrování dat časové řady
                        result_data = process_time_series_data(raw_stock_data, request_json)
                    elif request_type == "overview":
                        result_data = fetch_stock_overview(request_json, st.session_state.query_api_counts)
                    elif request_type == "news":
                        result_data = fetch_stock_news(request_json, st.session_state.query_api_counts)
                    else:
                        st.error(f"Neznámý typ požadavku od LLM: {request_type}")
                        result_data = None

                    st.session_state.last_result = result_data # Uložit finální výsledek

                    # Aktualizace celkových počtů API volání v session
                    for key in st.session_state.total_api_counts:
                        st.session_state.total_api_counts[key] += st.session_state.query_api_counts[key]

                except (ValueError, RuntimeError) as e: # Očekávané chyby (např. z LLM nebo API)
                    st.error(f"Došlo k chybě při zpracování dotazu: {e}")
                    # Zobrazit LLM JSON pro debug, pokud existuje
                    if st.session_state.last_request_json:
                         with st.expander("LLM Request JSON (Při chybě)"):
                             st.json(st.session_state.last_request_json)
                    st.session_state.last_result = None # Vyčistit výsledek při chybě
                except Exception as e: # Neočekávané systémové chyby
                    st.error(f"Došlo k neočekávané chybě: {e}")
                    import traceback
                    st.exception(traceback.format_exc()) # Zobrazit celý traceback
                    st.session_state.last_result = None


# --- Zobrazení výsledků (pokud existují v session state) ---
# Tato část se provede po zpracování dotazu (nebo při obnovení stránky, pokud data zůstala v session)
# Funguje pro MOCK i skutečná data, pokud mají očekávanou strukturu.
if st.session_state.last_result:
    result_data = st.session_state.last_result
    request_json = st.session_state.last_request_json # Může být mock nebo skutečný
    is_mock_result = False
    request_type = None

    # Získání typu požadavku a určení, zda jde o mock výsledek
    if request_json:
        request_type = request_json.get("request_type")
        # Detekce mock výsledku (např. podle speciálního pole v datech nebo requestu)
        if result_data.get("query_details", {}).get("api_function", "").startswith("MOCK_"):
            is_mock_result = True
    else:
        # Pokud nemáme request JSON (např. chyba při generování mock), nelze zobrazit
        st.warning("Nebylo možné získat detaily požadavku pro zobrazení výsledků.")
        request_type = None

    # Zobrazení výsledků podle typu požadavku
    if request_type:
        st.success("Dotaz úspěšně zpracován!" + (" (Použita MOCK data)" if is_mock_result else ""))

        # Volání správné zobrazovací funkce
        if request_type == "time_series":
            display_time_series(result_data)
        elif request_type == "overview":
            if is_mock_result:
                 st.info("Zobrazení mock dat pro Overview zatím není implementováno.")
                 st.json(result_data) # Zobrazit alespoň JSON
            else:
                 display_overview(result_data)
        elif request_type == "news":
            if is_mock_result:
                 st.info("Zobrazení mock dat pro News zatím není implementováno.")
                 st.json(result_data) # Zobrazit alespoň JSON
            else:
                display_news(result_data)
        else:
            # Nemělo by nastat, pokud je request_type validní
             st.error(f"Neznámý typ požadavku '{request_type}' pro zobrazení.")

        # Zobrazení detailů zpracování (JSON request a API počty)
        if request_json:
            with st.expander("Detaily zpracování (Request & API Počty)"):
                st.write("**Požadavek (z LLM nebo MOCK):**")
                st.json(request_json)
                st.write("**API volání pro tento dotaz:**")
                # Pro mock dotazy zde budou nuly
                st.json(st.session_state.query_api_counts)
        else:
             # Pokud request JSON chybí, zobrazit alespoň počty (měly by být 0)
             with st.expander("Detaily zpracování (Request & API Počty)"):
                 st.write("**Požadavek:** Není k dispozici.")
                 st.write("**API volání pro tento dotaz:**")
                 st.json(st.session_state.query_api_counts)


# Sidebar se statistikami
st.sidebar.title("Statistiky")
st.sidebar.write("**Celková API volání (od spuštění aplikace):**")
st.sidebar.metric("LLM Calls", st.session_state.total_api_counts["llm"])
st.sidebar.metric("Alpha Vantage Calls", st.session_state.total_api_counts["alpha_vantage"])
st.sidebar.caption("Pozn.: Alpha Vantage free tier má limity. Mock dotazy se nezapočítávají.")

