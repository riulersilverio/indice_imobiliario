# -*- coding: utf-8 -*- # Garante codificação correta

import streamlit as st
import requests
import pandas as pd
from itertools import combinations
from collections import OrderedDict
from datetime import date, timedelta
import locale # Para nomes de meses em português
import re # Para parsear nomes combinados

# --- DEFINIR LOCALE PARA PORTUGUÊS ---
try: locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    try: locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252')
    except locale.Error:
        try: locale.setlocale(locale.LC_TIME, 'ptb')
        except locale.Error: st.warning("Não foi possível definir o locale para Português (pt_BR).")
# ------------------------------------

# --- Configuração da Página ---
st.set_page_config(layout="wide", page_title="Painel de Inflação BCB | LocX", initial_sidebar_state="expanded")

# --- Cabeçalho com Logo ---
col_espaco, col_logo = st.columns([0.85, 0.15])
#with col_logo:
#    try: st.image("locx logo.png", width=120)
#    except FileNotFoundError: st.error("Erro: Arquivo 'locx logo.png' não encontrado.")
#    except Exception as e: st.error(f"Erro ao carregar logo: {e}")

# --- Título ---
st.title("📊 Painel de Índices de Inflação (BCB SGS)"); st.markdown("Consulte e compare a inflação acumulada.")

# --- Configuração Índices ---
INDICES_IDS = OrderedDict([('IPCA', 433), ('INPC', 188), ('IGP-DI', 190), ('INCC', 192), ('IGP-M', 189), ('IPC-FIPE', 191)])

# --- Busca Dados BCB (Cache) ---
@st.cache_data(ttl=3600)
def get_bcb_data(codigo_sgs, period=None, start_date=None, end_date=None):
    # ... (código da função get_bcb_data - sem alterações) ...
    if period: url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_sgs}/dados/ultimos/{period}?formato=json"
    elif start_date and end_date: start_str = start_date.strftime('%d/%m/%Y'); end_str = end_date.strftime('%d/%m/%Y'); url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_sgs}/dados?formato=json&dataInicial={start_str}&dataFinal={end_str}"
    else: return None
    try:
        response = requests.get(url, timeout=15); response.raise_for_status(); data = response.json()
        if not data: return None
        df = pd.DataFrame(data); df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y'); df = df.set_index('data')
        col_name = f'sgs_{codigo_sgs}'; df = df.rename(columns={'valor': col_name}); df[col_name] = pd.to_numeric(df[col_name], errors='coerce'); df = df.dropna(subset=[col_name])
        if df.empty: return None
        if start_date and end_date: df.index = pd.to_datetime(df.index); df = df[(df.index >= pd.to_datetime(start_date)) & (df.index <= pd.to_datetime(end_date))]; df = df[~df.index.duplicated(keep='first')]
        if df.empty: return None
        return df[[col_name]]
    except requests.exceptions.RequestException: return None
    except Exception as e: st.error(f"Erro processando dados BCB ({codigo_sgs}): {e}"); return None

# --- Cálculo Acumulado (Comparação) ---
def calculate_accumulated_inflation(df, column_name):
    # ... (código da função - sem alterações) ...
    if column_name not in df.columns: return None
    try:
        numeric_series = pd.to_numeric(df[column_name], errors='coerce').dropna();
        if numeric_series.empty or len(numeric_series) < 1: return None;
        if not pd.api.types.is_numeric_dtype(numeric_series) or not all(numeric_series.apply(lambda x: pd.notna(x) and abs(x) != float('inf'))): return None;
        accumulated_inflation = (numeric_series.apply(lambda x: 1 + (x / 100)).prod() - 1) * 100; return accumulated_inflation
    except Exception: return None

# --- Cálculo Acumulado 12M (Histórico/Aluguel) ---
def calculate_rolling_12m_accumulation(series_window_monthly_perc):
    # ... (código da função - sem alterações) ...
    valid_series = series_window_monthly_perc.dropna();
    if len(valid_series) == 12:
        try: accumulation = (valid_series.apply(lambda x: 1 + (x / 100)).prod() - 1) * 100; return accumulation
        except Exception: return pd.NA
    else: return pd.NA

# --- Controles Barra Lateral ---
# ... (Código barra lateral - sem alterações) ...
st.sidebar.header("⚙️ Configurações da Comparação"); period_mode = st.sidebar.radio("Definir período da comparação por:", ("Últimos N Meses", "Intervalo de Datas"), index=0, key="period_mode_radio"); period = None; start_date = None; end_date = None; period_label = ""
if period_mode == "Últimos N Meses": period = st.sidebar.number_input("Número de meses:", min_value=1, max_value=360, value=12, step=1, help="Número aproximado de meses anteriores.", key="period_number_input"); period_label = f"{period} últimos meses (aprox.)"
else: today = date.today(); default_start = today - timedelta(days=366); start_date = st.sidebar.date_input("Data Inicial:", value=default_start, min_value=date(1990, 1, 1), max_value=today, key="start_date_input"); end_date = st.sidebar.date_input("Data Final:", value=today, min_value=start_date, max_value=today, key="end_date_input");
if start_date and end_date and start_date > end_date: st.sidebar.error("Erro: Data Final < Data Inicial."); st.stop()
if not period_label and start_date and end_date: period_label = f"de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
default_indices = list(INDICES_IDS.keys()); selected_indices_names = st.sidebar.multiselect("Selecione os Índices para Comparar:", options=default_indices, default=default_indices[:3], help="Escolha um ou mais índices.", key="indices_multiselect")

# --- Lógica Principal da Comparação Acumulada ---
# ... (Código da seção de comparação acumulada - sem alterações) ...
st.header(f"📈 Comparação Acumulada ({period_label})");
if not selected_indices_names: st.warning("👈 Selecione índices na barra lateral para a comparação."); st.stop()
dataframes = {}; indices_validos_busca = []
with st.spinner(f"Buscando dados para comparação ({len(selected_indices_names)} índice(s), {period_label})..."):
    for indice_name in selected_indices_names:
        if indice_name in INDICES_IDS: codigo_sgs = INDICES_IDS[indice_name]; df = get_bcb_data(codigo_sgs, period=period, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty: col_name_sgs = f'sgs_{codigo_sgs}'; df = df.rename(columns={col_name_sgs: indice_name}); dataframes[indice_name] = df; indices_validos_busca.append(indice_name)
if not indices_validos_busca: st.error("Nenhum dado obtido para os índices selecionados na comparação."); st.stop()
indices_df_comp = None
if dataframes:
    try: indices_df_comp = pd.concat(dataframes.values(), axis=1, join='outer'); indices_df_comp = indices_df_comp.sort_index()
    except Exception as e: st.error(f"Erro ao combinar DataFrames para comparação: {e}"); st.stop()
if indices_df_comp is None: st.error("Falha ao criar DataFrame para comparação."); st.stop()
if start_date and end_date: indices_df_comp.index = pd.to_datetime(indices_df_comp.index); indices_df_comp = indices_df_comp[(indices_df_comp.index >= pd.to_datetime(start_date)) & (indices_df_comp.index <= pd.to_datetime(end_date))]
indices_df_comp.dropna(axis=0, how='all', subset=indices_validos_busca, inplace=True)
if indices_df_comp.empty: st.warning(f"Nenhum dado comum encontrado para os índices no período {period_label} após combinação."); st.stop()
accumulated_inflation_comp = {}; final_valid_indices_comp = []
if not indices_df_comp.empty: actual_start_comp = indices_df_comp.index.min().strftime('%d/%m/%Y'); actual_end_comp = indices_df_comp.index.max().strftime('%d/%m/%Y'); st.markdown(f"*Período efetivo comparado: {actual_start_comp} a {actual_end_comp}*")
num_indices_plot = len(indices_validos_busca); cols_metrics = st.columns(num_indices_plot) if num_indices_plot > 0 else [st]; idx_col = 0
for indice_name in indices_validos_busca: # Exibição das Métricas Individuais
     if indice_name in indices_df_comp.columns:
         inflation = calculate_accumulated_inflation(indices_df_comp[[indice_name]], indice_name)
         if inflation is not None:
             accumulated_inflation_comp[indice_name] = inflation; current_col = cols_metrics[idx_col % num_indices_plot] if num_indices_plot > 0 else st
             with current_col: st.metric(label=f"{indice_name} (Acum.)", value=f"{inflation:.2f}%")
             final_valid_indices_comp.append(indice_name); idx_col += 1
if not final_valid_indices_comp: st.error("Não foi possível calcular o acumulado para nenhum índice na comparação."); st.stop()
with st.expander("Ver dados mensais brutos (%) da Comparação"): st.dataframe(indices_df_comp[indices_validos_busca].style.format("{:.2f}", na_rep="-"))
if len(final_valid_indices_comp) >= 2: # Análise Combinada (média e mínimo da comparação)
    st.subheader("Análise Combinada da Comparação")
    mean_results_list = []; min_results_list = []
    for r in range(2, len(final_valid_indices_comp) + 1):
        for combination in combinations(final_valid_indices_comp, r):
            indices_list = list(combination); indices_str = ", ".join(indices_list)
            try: # Médias
                if all(indice in accumulated_inflation_comp for indice in indices_list): mean_inflation = sum(accumulated_inflation_comp[indice] for indice in indices_list) / len(indices_list); mean_results_list.append(f"Média acumulada para {indices_str}: {mean_inflation:.2f}%")
                else: mean_results_list.append(f"Média acumulada para {indices_str}: Erro (Dados ausentes)")
            except Exception as e: mean_results_list.append(f"Média acumulada para {indices_str}: Erro ({type(e).__name__})")
            try: # Mínimos
                 valid_values = {k: v for k, v in accumulated_inflation_comp.items() if k in indices_list and v is not None}
                 if not valid_values: min_results_list.append(f"Menor acumulada entre {indices_str}: N/A"); continue
                 min_inflation_val = min(valid_values.values()); min_index_name = min(valid_values, key=valid_values.get)
                 min_results_list.append(f"Menor acumulada entre {indices_str}: {min_inflation_val:.2f}% ({min_index_name})")
            except Exception as e: min_results_list.append(f"Menor acumulada entre {indices_str}: Erro ({type(e).__name__})")
    st.markdown("--- Médias entre Índices ---"); st.text("\n".join(mean_results_list))
    st.markdown("--- Menor Índice em Comparação ---"); st.text("\n".join(min_results_list))

# --- Seção do Gráfico Histórico COMPARATIVO (Acumulado 12 Meses) ---
# ... (Código da seção do gráfico histórico - sem alterações) ...
st.divider(); st.header("📜 Histórico Comparativo de Índices"); st.markdown("Visualize e compare a inflação **acumulada em 12 meses** para múltiplos índices.")
historical_indices_options = list(INDICES_IDS.keys()); selected_historical_indices = st.multiselect("Escolha o(s) índice(s) para ver o histórico:", options=historical_indices_options, default=historical_indices_options[:1], key="hist_indices_multiselect")
if selected_historical_indices:
    historical_range_options = {"Últimos 3 Meses": 3, "Últimos 6 Meses": 6, "Último Ano": 12, "Últimos 3 Anos": 36, "Últimos 5 Anos": 60,}; selected_range_label = st.radio("Selecione o período para visualizar:", options=list(historical_range_options.keys()), horizontal=True, key="hist_range_radio"); months_in_range = historical_range_options[selected_range_label]
    MONTHS_TO_FETCH_FOR_ROLLING = 60 + 11; today_hist = date.today(); start_date_fetch = today_hist - timedelta(days=MONTHS_TO_FETCH_FOR_ROLLING * 31)
    historical_rolling_dfs = {}; valid_hist_indices = []
    with st.spinner(f"Buscando e calculando histórico para {len(selected_historical_indices)} índice(s)..."):
        for index_name in selected_historical_indices:
            if index_name in INDICES_IDS: codigo_sgs_hist = INDICES_IDS[index_name]; historical_df_monthly = get_bcb_data(codigo_sgs=codigo_sgs_hist, start_date=start_date_fetch, end_date=today_hist)
            if historical_df_monthly is not None and not historical_df_monthly.empty:
                col_name_monthly = f'sgs_{codigo_sgs_hist}'
                if col_name_monthly not in historical_df_monthly.columns: continue
                historical_df_monthly = historical_df_monthly.rename(columns={col_name_monthly: index_name}); historical_df_monthly.index = pd.to_datetime(historical_df_monthly.index)
                window_size = 12; rolling_accum_col_name = f"{index_name}_Acum12M"
                historical_df_monthly[rolling_accum_col_name] = historical_df_monthly[index_name].rolling(window=window_size, min_periods=window_size).apply(calculate_rolling_12m_accumulation, raw=False)
                df_to_store = historical_df_monthly[[rolling_accum_col_name]].dropna()
                if not df_to_store.empty: historical_rolling_dfs[index_name] = df_to_store; valid_hist_indices.append(index_name)
    if not valid_hist_indices: st.error("Não foi possível calcular o histórico acumulado 12 meses para nenhum índice selecionado."); st.stop()
    combined_rolling_df = None
    try:
        if historical_rolling_dfs: combined_rolling_df = pd.concat(historical_rolling_dfs.values(), axis=1); combined_rolling_df.columns = valid_hist_indices; combined_rolling_df = combined_rolling_df.sort_index() # Outer join implícito se índices diferentes
        else: st.warning("Nenhum DataFrame histórico válido para concatenar."); st.stop()
    except Exception as e: st.error(f"Erro ao combinar dados históricos: {e}"); st.stop()
    if combined_rolling_df is None: st.error("Falha ao criar DataFrame combinado histórico."); st.stop()
    end_date_display = today_hist; start_date_display = end_date_display - timedelta(days=months_in_range * 30.5)
    combined_rolling_df_display = combined_rolling_df[(combined_rolling_df.index >= pd.to_datetime(start_date_display)) & (combined_rolling_df.index <= pd.to_datetime(end_date_display))].copy(); combined_rolling_df_display.dropna(axis=0, how='all', inplace=True)
    if not combined_rolling_df_display.empty:
        st.markdown("**Médias do Acum. 12M no Período Selecionado:**"); cols_hist_metrics = st.columns(len(valid_hist_indices)) if len(valid_hist_indices) > 0 else [st]; idx_hist_col = 0
        for index_name in valid_hist_indices: # Exibição das Métricas do Histórico
            if index_name in combined_rolling_df_display.columns:
                average_val = combined_rolling_df_display[index_name].mean()
                if pd.notna(average_val):
                    current_col = cols_hist_metrics[idx_hist_col % len(valid_hist_indices)] if len(valid_hist_indices)>0 else st
                    with current_col: st.metric(label=f"{index_name}", value=f"{average_val:.2f}%", help=f"Média do acumulado 12m de {index_name} entre {start_date_display.strftime('%m/%Y')} e {end_date_display.strftime('%m/%Y')}.")
                    idx_hist_col += 1
        st.line_chart(combined_rolling_df_display)
        with st.expander("Ver dados do gráfico (Acumulado 12 Meses %)"): st.dataframe(combined_rolling_df_display.style.format("{:.2f}", na_rep="-"))
    else: st.info(f"Não há dados de inflação acumulada em 12 meses para os índices no período ({selected_range_label}).")
else: st.info("👆 Selecione um ou mais índices acima para visualizar o histórico comparativo.")


# --- Seção de Cálculo de Reajuste de Aluguel --- # SEÇÃO MODIFICADA #

st.divider()
st.header("💸 Calculadora de Reajuste de Aluguel")
st.markdown("Simule o reajuste do seu aluguel com base em diferentes índices (individuais, média ou mínimo de combinações).")

# --- Inputs para o Cálculo do Aluguel ---
rent_col1, rent_col2 = st.columns(2)
with rent_col1:
    initial_rent = st.number_input("Valor Inicial do Aluguel (R$):", min_value=0.01, value=1000.0, step=100.0, format="%.2f", key="rent_initial_value")
    contract_start_date = st.date_input("Data de Início do Contrato:", value=date.today() - timedelta(days=365*2), max_value=date.today() - timedelta(days=31), help="O contrato deve ter pelo menos 1 mês.", key="rent_start_date")
with rent_col2:
    rent_index_options = ["Selecione o índice..."] + list(INDICES_IDS.keys())
    actual_rent_index = st.selectbox("Índice Aplicado no Contrato:", options=rent_index_options, index=0, help="Qual índice foi usado para reajustar seu aluguel?", key="rent_actual_index")
    contract_end_date = st.date_input("Data Final do Contrato (ou hoje):", value=date.today(), min_value=contract_start_date + timedelta(days=30), max_value=date.today() + timedelta(days=365*10), key="rent_end_date")

calculate_button = st.button("Calcular Reajuste e Comparar Cenários", key="rent_calculate_btn") # Nome do botão atualizado

# --- Lógica do Cálculo (Executa ao clicar no botão) ---
if calculate_button and actual_rent_index != "Selecione o índice...":

    # 1. Determinar período e buscar dados MENSAIS para TODOS os índices base
    fetch_start_date = contract_start_date - pd.DateOffset(months=12); fetch_end_date = contract_end_date
    all_base_indices = list(INDICES_IDS.keys())
    monthly_data_all_indices = {}; failed_indices_fetch = []
    with st.spinner(f"Buscando dados mensais ({fetch_start_date.strftime('%m/%Y')}-{fetch_end_date.strftime('%m/%Y')})..."):
        for index_name in all_base_indices:
            codigo_sgs = INDICES_IDS[index_name]
            df_monthly = get_bcb_data(codigo_sgs=codigo_sgs, start_date=fetch_start_date, end_date=fetch_end_date)
            if df_monthly is not None and not df_monthly.empty:
                col_name_sgs = f'sgs_{codigo_sgs}'
                if col_name_sgs in df_monthly.columns: df_monthly = df_monthly.rename(columns={col_name_sgs: index_name}); monthly_data_all_indices[index_name] = df_monthly[[index_name]]
                else: failed_indices_fetch.append(index_name)
            else: failed_indices_fetch.append(index_name)
    if actual_rent_index not in monthly_data_all_indices: st.error(f"Dados históricos ausentes para o índice base ({actual_rent_index})."); st.stop()
    if failed_indices_fetch: st.warning(f"Dados ausentes para comparação: {', '.join(failed_indices_fetch)}")
    valid_base_indices = list(monthly_data_all_indices.keys())

    # 2. PRÉ-CALCULAR Acumulado 12 Meses para TODOS os índices base válidos
    rolling_12m_all_indices = {} # Dicionário para guardar as séries Acum12m
    with st.spinner("Calculando acumulado 12 meses para índices base..."):
        for index_name in valid_base_indices:
            df_monthly = monthly_data_all_indices[index_name]
            rolling_accum_col = f"{index_name}_Acum12M" # Sufixo _Acum12M para clareza
            df_monthly.index = pd.to_datetime(df_monthly.index)
            df_monthly[rolling_accum_col] = df_monthly[index_name].rolling(window=12, min_periods=12).apply(calculate_rolling_12m_accumulation, raw=False)
            rolling_12m_all_indices[index_name] = df_monthly[[rolling_accum_col]].dropna() # Guarda só a coluna calculada sem NaN inicial

    # 3. Função MODIFICADA para Simular Pagamentos (aceita nomes combinados)
    def simulate_rent_payments_v2(start_rent, start_date, end_date, simulation_index_name, precalculated_rolling_data):
        payment_history = []; current_rent = start_rent; total_paid = 0
        date_range = pd.date_range(start=start_date, end=end_date, freq='MS')
        base_indices_in_sim = []; sim_type = "base" # Padrão

        # Parseia o nome para identificar tipo e índices base
        if simulation_index_name.startswith("Média (") and simulation_index_name.endswith(")"):
            sim_type = "media"; base_indices_in_sim = [idx.strip() for idx in re.findall(r'\((.*?)\)', simulation_index_name)[0].split(',')]
        elif simulation_index_name.startswith("Mínimo (") and simulation_index_name.endswith(")"):
            sim_type = "minimo"; base_indices_in_sim = [idx.strip() for idx in re.findall(r'\((.*?)\)', simulation_index_name)[0].split(',')]
        elif simulation_index_name in precalculated_rolling_data: base_indices_in_sim = [simulation_index_name]
        else: return None, 0, f"Índice '{simulation_index_name}' inválido."

        if not all(idx in precalculated_rolling_data for idx in base_indices_in_sim): missing = [idx for idx in base_indices_in_sim if idx not in precalculated_rolling_data]; return None, 0, f"Dados ausentes para: {', '.join(missing)}"

        for current_month_start in date_range:
            adjustment_perc = pd.NA; adjusted_value = 0.0
            if current_month_start.month == start_date.month and current_month_start > pd.Timestamp(start_date):
                adjustment_index_date = current_month_start - pd.DateOffset(months=1); adjustment_month_period = adjustment_index_date.to_period('M')
                accum_values_for_month = []
                for base_idx in base_indices_in_sim:
                    rolling_col = f"{base_idx}_Acum12M"
                    try:
                        # Busca valor pré-calculado do mês anterior
                        val = precalculated_rolling_data[base_idx].loc[precalculated_rolling_data[base_idx].index.to_period('M') == adjustment_month_period, rolling_col].iloc[0]
                        if pd.notna(val): accum_values_for_month.append(val)
                        else: accum_values_for_month = []; break # Se algum for NA, não calcula média/min
                    except IndexError: accum_values_for_month = []; break # Data não encontrada
                    except Exception: accum_values_for_month = []; break # Outro erro

                if accum_values_for_month: # Se conseguiu buscar todos os valores necessários
                    if sim_type == "base": adjustment_perc = accum_values_for_month[0]
                    elif sim_type == "media": adjustment_perc = sum(accum_values_for_month) / len(accum_values_for_month)
                    elif sim_type == "minimo": adjustment_perc = min(accum_values_for_month)

                    if pd.notna(adjustment_perc):
                        new_rent = current_rent * (1 + adjustment_perc / 100)
                        adjusted_value = new_rent - current_rent; current_rent = new_rent

            payment_history.append({"Mês/Ano": current_month_start.strftime("%m/%Y"), "Índice Mês Reajuste (%)": adjustment_perc if current_month_start.month == start_date.month else None, "Valor Reajuste (R$)": adjusted_value if adjusted_value != 0 else None, "Aluguel Pago (R$)": current_rent})
            total_paid += current_rent
        history_df = pd.DataFrame(payment_history); return history_df, total_paid, None

    # 4. Simular o Contrato Real
    st.subheader(f"Simulação do Contrato Real (Índice: {actual_rent_index})")
    actual_history_df, actual_total_paid, error_msg = simulate_rent_payments_v2(initial_rent, contract_start_date, contract_end_date, actual_rent_index, rolling_12m_all_indices)
    if error_msg: st.error(f"Erro ao simular contrato real: {error_msg}"); st.stop()
    if actual_history_df is not None:
        st.dataframe(actual_history_df.style.format({"Índice Mês Reajuste (%)": "{:.2f}%", "Valor Reajuste (R$)": "R$ {:,.2f}", "Aluguel Pago (R$)": "R$ {:,.2f}",}, na_rep="-").hide(axis="index"))
        st.metric(label=f"Total Pago com {actual_rent_index} (R$)", value=f"{actual_total_paid:,.2f}")
    else: st.error("Não foi possível gerar histórico para o contrato real."); st.stop()

    # 5. Gerar Opções Combinadas e Simular Comparações
    st.subheader("Comparação com Outros Cenários")
    comparison_results = []; indices_to_compare_final = []
    indices_to_compare_final.extend([idx for idx in valid_base_indices if idx != actual_rent_index]) # Adiciona base
    # Gera combinações de Média/Mínimo para 2 e 3 índices
    for r in range(2, 4):
        for combo in combinations(valid_base_indices, r):
            combo_str = ", ".join(combo)
            indices_to_compare_final.append(f"Média ({combo_str})")
            indices_to_compare_final.append(f"Mínimo ({combo_str})")

    if indices_to_compare_final:
        with st.spinner("Simulando outros cenários..."):
            for sim_index_name in indices_to_compare_final:
                sim_history_df, sim_total_paid, error_msg_sim = simulate_rent_payments_v2(initial_rent, contract_start_date, contract_end_date, sim_index_name, rolling_12m_all_indices)
                status = "Calculado"; difference = pd.NA
                if error_msg_sim: status = f"{error_msg_sim}"; sim_total_paid = pd.NA; # Mostra o erro específico
                elif sim_total_paid is not None: difference = sim_total_paid - actual_total_paid
                else: status = "Erro desconhecido"; sim_total_paid = pd.NA;
                comparison_results.append({"Cenário Simulado": sim_index_name, "Total Pago Simulado (R$)": sim_total_paid, "Diferença vs Contrato (R$)": difference, "Status": status})
        if comparison_results:
            comparison_df = pd.DataFrame(comparison_results)
            # --- ORDENAÇÃO ADICIONADA AQUI ---
            comparison_df = comparison_df.sort_values(by="Diferença vs Contrato (R$)", ascending=True, na_position='last')
            st.dataframe(comparison_df.style.format({"Total Pago Simulado (R$)": "R$ {:,.2f}", "Diferença vs Contrato (R$)": "{:+,.2f}"}, na_rep="-").applymap(lambda x: 'color: red' if isinstance(x, (int, float)) and x > 0 else ('color: green' if isinstance(x, (int, float)) and x < 0 else ''), subset=['Diferença vs Contrato (R$)']).hide(axis="index"))
        else: st.info("Não foi possível calcular comparação.")
    else: st.info("Não há outros cenários com dados disponíveis para comparação.")

# --- Fim da Seção de Cálculo de Reajuste de Aluguel ---

# --- Rodapé na Barra Lateral ---
st.sidebar.markdown("---"); st.sidebar.info("Dados: API de Séries Temporais do Banco Central do Brasil (SGS)."); st.sidebar.info("Cache de dados da API ativo por 1 hora."); st.sidebar.info("Criado por Riuler");