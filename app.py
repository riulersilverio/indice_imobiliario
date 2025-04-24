# -*- coding: utf-8 -*- # Garante codificação correta

import streamlit as st
import requests
import pandas as pd
from itertools import combinations
from collections import OrderedDict
from datetime import date, timedelta
import locale # Para nomes de meses em português
import re # Para parsear nomes combinados

# --- Configuração da Página (MOVIDO PARA CÁ - DEVE SER O PRIMEIRO COMANDO st.*) ---
st.set_page_config(layout="wide", page_title="Painel de Inflação BCB | LocX", initial_sidebar_state="expanded")
# -----------------------------------------------------------------------------------

# --- DEFINIR LOCALE PARA PORTUGUÊS ---
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'ptb')
        except locale.Error:
            # ATENÇÃO: Usando print() aqui para evitar erro de ordem do Streamlit.
            # Esta mensagem aparecerá nos logs do Streamlit Cloud se o locale falhar.
            print("Warning: Não foi possível definir o locale para Português (pt_BR).")
# ------------------------------------


# --- Cabeçalho com Logo ---
# Comentado pois precisa do arquivo de imagem no repositório
# col_espaco, col_logo = st.columns([0.85, 0.15])
# with col_logo:
#    try:
#        st.image("locx logo.png", width=120) # Certifique-se que 'locx logo.png' está no repo
#    except Exception as e:
#        st.error(f"Erro ao carregar logo: {e}")

# --- Título ---
st.title("📊 Painel de Índices de Inflação (BCB SGS)")
st.markdown("Consulte e compare a inflação acumulada.")

# --- Configuração Índices ---
INDICES_IDS = OrderedDict([
    ('IPCA', 433),
    ('INPC', 188),
    ('IGP-DI', 190),
    ('INCC', 192),
    ('IGP-M', 189),
    ('IPC-FIPE', 191)
])

# --- Busca Dados BCB (Cache) ---
@st.cache_data(ttl=3600) # Cache por 1 hora
def get_bcb_data(codigo_sgs, period=None, start_date=None, end_date=None):
    """Busca dados da API SGS do BCB."""
    if period:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_sgs}/dados/ultimos/{period}?formato=json"
    elif start_date and end_date:
        start_str = start_date.strftime('%d/%m/%Y')
        end_str = end_date.strftime('%d/%m/%Y')
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_sgs}/dados?formato=json&dataInicial={start_str}&dataFinal={end_str}"
    else:
        print(f"Erro BCB ({codigo_sgs}): Nem 'period' nem 'start/end_date' fornecidos.")
        return None # Precisa de um período ou datas

    try:
        response = requests.get(url, timeout=20) # Aumentado timeout
        response.raise_for_status() # Verifica erros HTTP (4xx, 5xx)
        data = response.json()

        if not data: # Lista vazia retornada pela API
            print(f"BCB ({codigo_sgs}): Nenhum dado retornado pela API para o período/datas.")
            return None

        df = pd.DataFrame(data)
        df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y')
        df = df.set_index('data')
        col_name = f'sgs_{codigo_sgs}'
        df = df.rename(columns={'valor': col_name})
        df[col_name] = pd.to_numeric(df[col_name], errors='coerce')
        df = df.dropna(subset=[col_name]) # Remove linhas onde a conversão falhou

        if df.empty:
             print(f"BCB ({codigo_sgs}): DataFrame vazio após limpeza inicial.")
             return None

        # Filtra novamente pelas datas exatas se fornecidas (API pode retornar um pouco mais)
        if start_date and end_date:
            df.index = pd.to_datetime(df.index)
            df = df[(df.index >= pd.to_datetime(start_date)) & (df.index <= pd.to_datetime(end_date))]
            # Garante índice único (em caso de dados duplicados raros na API)
            df = df[~df.index.duplicated(keep='first')]

        if df.empty:
             print(f"BCB ({codigo_sgs}): DataFrame vazio após filtro final de datas.")
             return None

        return df[[col_name]] # Retorna apenas a coluna de valor

    except requests.exceptions.Timeout:
        st.error(f"Erro BCB ({codigo_sgs}): Timeout ao acessar API.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Erro BCB ({codigo_sgs}): Erro na requisição - {e}")
        return None
    except Exception as e:
        st.error(f"Erro processando dados BCB ({codigo_sgs}): {e}")
        return None

# --- Cálculo Acumulado (Comparação) ---
def calculate_accumulated_inflation(df, column_name):
    """Calcula inflação acumulada para uma coluna em um DataFrame."""
    if column_name not in df.columns:
        print(f"Erro Acumulado: Coluna '{column_name}' não encontrada.")
        return None
    try:
        # Converte para numérico, tratando erros e removendo NaNs resultantes
        numeric_series = pd.to_numeric(df[column_name], errors='coerce').dropna()

        if numeric_series.empty:
            print(f"Erro Acumulado ({column_name}): Série vazia após conversão/limpeza.")
            return None
        if len(numeric_series) < 1: # Precisa de pelo menos um valor
             print(f"Erro Acumulado ({column_name}): Menos de 1 valor válido.")
             return None
        # Verifica se todos os valores são realmente numéricos e finitos
        if not pd.api.types.is_numeric_dtype(numeric_series) or not all(numeric_series.apply(lambda x: pd.notna(x) and abs(x) != float('inf'))):
             print(f"Erro Acumulado ({column_name}): Contém valores não numéricos ou infinitos.")
             return None

        # Cálculo da inflação acumulada
        accumulated_inflation = (numeric_series.apply(lambda x: 1 + (x / 100)).prod() - 1) * 100
        return accumulated_inflation
    except Exception as e:
        print(f"Erro inesperado em calculate_accumulated_inflation ({column_name}): {e}")
        return None

# --- Cálculo Acumulado 12M (Histórico/Aluguel) ---
def calculate_rolling_12m_accumulation(series_window_monthly_perc):
    """Função para ser usada com .rolling().apply() para calcular acum. 12 meses."""
    valid_series = series_window_monthly_perc.dropna()
    if len(valid_series) == 12: # Só calcula se tiver exatamente 12 meses válidos na janela
        try:
            accumulation = (valid_series.apply(lambda x: 1 + (x / 100)).prod() - 1) * 100
            return accumulation
        except Exception:
            return pd.NA # Retorna NA em caso de erro no cálculo
    else:
        return pd.NA # Retorna NA se não tiver 12 meses válidos

# --- Controles Barra Lateral ---
st.sidebar.header("⚙️ Configurações da Comparação")
period_mode = st.sidebar.radio(
    "Definir período da comparação por:",
    ("Últimos N Meses", "Intervalo de Datas"),
    index=0,
    key="period_mode_radio"
)

period = None
start_date = None
end_date = None
period_label = ""

if period_mode == "Últimos N Meses":
    period = st.sidebar.number_input(
        "Número de meses:",
        min_value=1, max_value=360, value=12, step=1,
        help="Número aproximado de meses anteriores para buscar.",
        key="period_number_input"
    )
    period_label = f"{period} últimos meses (aprox.)"
else: # Intervalo de Datas
    today = date.today()
    default_start = today - timedelta(days=366) # Default: último ano
    start_date = st.sidebar.date_input(
        "Data Inicial:",
        value=default_start,
        min_value=date(1990, 1, 1), # Limite razoável para início das séries
        max_value=today,
        key="start_date_input"
    )
    end_date = st.sidebar.date_input(
        "Data Final:",
        value=today,
        min_value=start_date, # Data final não pode ser antes da inicial
        max_value=today,
        key="end_date_input"
    )
    # Validação adicional
    if start_date and end_date and start_date > end_date:
        st.sidebar.error("Erro: Data Final não pode ser anterior à Data Inicial.")
        st.stop() # Interrompe execução se datas inválidas

# Atualiza label se modo de data foi escolhido
if not period_label and start_date and end_date:
    period_label = f"de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"

default_indices = list(INDICES_IDS.keys())
selected_indices_names = st.sidebar.multiselect(
    "Selecione os Índices para Comparar:",
    options=default_indices,
    default=default_indices[:3], # Default: os 3 primeiros da lista
    help="Escolha um ou mais índices para a análise acumulada.",
    key="indices_multiselect"
)

# --- Lógica Principal da Comparação Acumulada ---
st.header(f"📈 Comparação Acumulada ({period_label})")

if not selected_indices_names:
    st.warning("👈 Selecione pelo menos um índice na barra lateral para iniciar a comparação.")
    st.stop()

dataframes = {}
indices_validos_busca = [] # Guarda nomes dos índices que retornaram dados

# Busca dados para cada índice selecionado
# Usar st.spinner para feedback visual durante a busca
with st.spinner(f"Buscando dados para comparação ({len(selected_indices_names)} índice(s), {period_label})..."):
    for indice_name in selected_indices_names:
        if indice_name in INDICES_IDS:
            codigo_sgs = INDICES_IDS[indice_name]
            # Passa os parâmetros corretos (period OU start/end_date)
            df = get_bcb_data(codigo_sgs, period=period, start_date=start_date, end_date=end_date)

            if df is not None and not df.empty:
                # Renomeia a coluna para o nome do índice (IPCA, INPC, etc.)
                col_name_sgs = f'sgs_{codigo_sgs}'
                df = df.rename(columns={col_name_sgs: indice_name})
                dataframes[indice_name] = df # Guarda o DataFrame no dicionário
                indices_validos_busca.append(indice_name)
            else:
                 print(f"Comparação: Nenhum dado válido retornado para {indice_name}.")
        else:
            st.warning(f"Índice '{indice_name}' não reconhecido.") # Caso raro

# Verifica se algum dado foi obtido
if not indices_validos_busca:
    st.error("Nenhum dado pôde ser obtido para os índices selecionados no período especificado.")
    st.stop()

# Combina os DataFrames obtidos
indices_df_comp = None
if dataframes:
    try:
        # Usa concat com outer join para manter todas as datas e preencher com NaN onde não há dados
        indices_df_comp = pd.concat(dataframes.values(), axis=1, join='outer')
        # Ordena pelo índice (data)
        indices_df_comp = indices_df_comp.sort_index()
    except Exception as e:
        st.error(f"Erro ao combinar DataFrames para comparação: {e}")
        st.stop()

# Se a combinação falhar ou resultar em vazio
if indices_df_comp is None or indices_df_comp.empty:
    st.error("Falha ao criar ou DataFrame combinado vazio para comparação.")
    st.stop()

# Refiltra por datas se o modo de intervalo foi usado (garante limites exatos)
if start_date and end_date:
    indices_df_comp.index = pd.to_datetime(indices_df_comp.index) # Garante que é DatetimeIndex
    indices_df_comp = indices_df_comp[(indices_df_comp.index >= pd.to_datetime(start_date)) & (indices_df_comp.index <= pd.to_datetime(end_date))]

# Remove linhas que só contenham NaN (após o join e possível refiltro)
indices_df_comp.dropna(axis=0, how='all', subset=indices_validos_busca, inplace=True)

# Verifica se ainda há dados após a limpeza
if indices_df_comp.empty:
    st.warning(f"Nenhum dado comum encontrado para os índices no período {period_label} após combinação e limpeza.")
    st.stop()

# Calcula e exibe a inflação acumulada para cada índice válido
accumulated_inflation_comp = {}
final_valid_indices_comp = [] # Índices que tiveram acumulado calculado com sucesso

# Exibe o período efetivo que está sendo comparado (pode ser menor que o solicitado)
if not indices_df_comp.empty:
    actual_start_comp = indices_df_comp.index.min().strftime('%d/%m/%Y')
    actual_end_comp = indices_df_comp.index.max().strftime('%d/%m/%Y')
    st.markdown(f"*Período efetivo considerado na comparação: **{actual_start_comp} a {actual_end_comp}***")

# Cria colunas para exibir as métricas lado a lado
num_indices_plot = len(indices_validos_busca)
cols_metrics = st.columns(num_indices_plot) if num_indices_plot > 0 else [st] # Fallback se 0
idx_col = 0

for indice_name in indices_validos_busca: # Itera sobre os que retornaram dados
     if indice_name in indices_df_comp.columns:
         # Passa apenas o DataFrame com a coluna relevante
         inflation = calculate_accumulated_inflation(indices_df_comp[[indice_name]], indice_name)
         if inflation is not None:
             accumulated_inflation_comp[indice_name] = inflation # Guarda o resultado
             # Seleciona a coluna para exibir a métrica
             current_col = cols_metrics[idx_col % num_indices_plot] if num_indices_plot > 0 else st
             with current_col:
                 st.metric(label=f"{indice_name} (Acum.)", value=f"{inflation:.2f}%")
             final_valid_indices_comp.append(indice_name) # Adiciona à lista final
             idx_col += 1
         else:
              print(f"Comparação: Não foi possível calcular acumulado para {indice_name}.")

# Se nenhum acumulado pôde ser calculado
if not final_valid_indices_comp:
    st.error("Não foi possível calcular a inflação acumulada para nenhum dos índices selecionados neste período.")
    st.stop()

# Expander para mostrar os dados brutos mensais usados na comparação
with st.expander("Ver dados mensais brutos (%) usados na Comparação Acumulada"):
    st.dataframe(indices_df_comp[indices_validos_busca].style.format("{:.2f}", na_rep="-"))

# Análise Combinada (Médias e Mínimos) - Somente se houver 2 ou mais índices com resultado
if len(final_valid_indices_comp) >= 2:
    st.subheader("Análise Combinada da Comparação")
    mean_results_list = []
    min_results_list = []

    # Gera combinações de 2 até N índices
    for r in range(2, len(final_valid_indices_comp) + 1):
        for combination in combinations(final_valid_indices_comp, r):
            indices_list = list(combination)
            indices_str = ", ".join(indices_list) # Para exibição

            # Cálculo da Média
            try:
                # Garante que todos os índices da combinação têm um valor calculado
                if all(indice in accumulated_inflation_comp for indice in indices_list):
                    mean_inflation = sum(accumulated_inflation_comp[indice] for indice in indices_list) / len(indices_list)
                    mean_results_list.append(f"Média acumulada para ({indices_str}): **{mean_inflation:.2f}%**")
                else:
                    mean_results_list.append(f"Média acumulada para ({indices_str}): Erro (Dados ausentes para um ou mais índices)")
            except Exception as e:
                mean_results_list.append(f"Média acumulada para ({indices_str}): Erro ({type(e).__name__})")

            # Cálculo do Mínimo
            try:
                 # Filtra apenas os valores válidos (não None) para a combinação atual
                 valid_values = {k: v for k, v in accumulated_inflation_comp.items() if k in indices_list and v is not None}
                 if not valid_values: # Se não houver valores válidos
                     min_results_list.append(f"Menor acumulada entre ({indices_str}): N/A (nenhum valor válido)")
                     continue
                 # Encontra o menor valor e o nome do índice correspondente
                 min_inflation_val = min(valid_values.values())
                 min_index_name = min(valid_values, key=valid_values.get) # Encontra a chave (nome) com o menor valor
                 min_results_list.append(f"Menor acumulada entre ({indices_str}): **{min_inflation_val:.2f}%** ({min_index_name})")
            except Exception as e:
                 min_results_list.append(f"Menor acumulada entre ({indices_str}): Erro ({type(e).__name__})")

    # Exibe os resultados das médias e mínimos
    st.markdown("--- **Médias entre Índices** ---")
    st.markdown("\n".join(mean_results_list)) # Usa markdown para negrito
    st.markdown("--- **Menor Índice em Comparação** ---")
    st.markdown("\n".join(min_results_list))

# --- Seção do Gráfico Histórico COMPARATIVO (Acumulado 12 Meses) ---
st.divider()
st.header("📜 Histórico Comparativo de Índices")
st.markdown("Visualize e compare a inflação **acumulada em 12 meses** para múltiplos índices ao longo do tempo.")

historical_indices_options = list(INDICES_IDS.keys())
selected_historical_indices = st.multiselect(
    "Escolha o(s) índice(s) para ver o histórico:",
    options=historical_indices_options,
    default=historical_indices_options[:1], # Default: apenas o primeiro índice
    key="hist_indices_multiselect"
)

if selected_historical_indices:
    # Opções de período para o gráfico histórico
    historical_range_options = {
        "Últimos 3 Meses": 3, "Últimos 6 Meses": 6, "Último Ano": 12,
        "Últimos 3 Anos": 36, "Últimos 5 Anos": 60, #"Tudo (desde 1995 aprox.)": 350
    }
    selected_range_label = st.radio(
        "Selecione o período para visualizar o gráfico:",
        options=list(historical_range_options.keys()),
        horizontal=True,
        index=2, # Default: Último Ano
        key="hist_range_radio"
    )
    months_in_range = historical_range_options[selected_range_label]

    # Determina a data inicial para buscar dados (precisa de 11 meses extras para o cálculo rolling)
    MONTHS_TO_FETCH_FOR_ROLLING = months_in_range + 11 # Busca dados suficientes para a janela móvel
    today_hist = date.today()
    # Define uma data inicial segura para a busca (evita buscar décadas desnecessariamente)
    # Usa uma data fixa mínima se o período for muito longo ou "Tudo"
    min_hist_date = date(1994, 7, 1) # Pouco antes do Plano Real
    start_date_fetch = max(today_hist - timedelta(days=MONTHS_TO_FETCH_FOR_ROLLING * 31), min_hist_date) # Pega a data mais recente

    historical_rolling_dfs = {} # Dicionário para armazenar os DataFrames com acumulado 12m calculado
    valid_hist_indices = [] # Nomes dos índices com histórico calculado

    with st.spinner(f"Buscando e calculando histórico acumulado 12m para {len(selected_historical_indices)} índice(s)..."):
        for index_name in selected_historical_indices:
            if index_name in INDICES_IDS:
                codigo_sgs_hist = INDICES_IDS[index_name]
                # Busca os dados MENSAIS para o período estendido
                historical_df_monthly = get_bcb_data(codigo_sgs=codigo_sgs_hist, start_date=start_date_fetch, end_date=today_hist)

                if historical_df_monthly is not None and not historical_df_monthly.empty:
                    col_name_monthly = f'sgs_{codigo_sgs_hist}'
                    if col_name_monthly not in historical_df_monthly.columns:
                         print(f"Histórico: Coluna {col_name_monthly} não encontrada para {index_name} após busca.")
                         continue # Pula para o próximo índice se a coluna esperada não existir

                    # Renomeia coluna e garante índice Datetime
                    historical_df_monthly = historical_df_monthly.rename(columns={col_name_monthly: index_name})
                    historical_df_monthly.index = pd.to_datetime(historical_df_monthly.index)

                    window_size = 12 # Janela para acumulado 12 meses
                    rolling_accum_col_name = f"{index_name}_Acum12M" # Nome da nova coluna

                    # Calcula o acumulado 12 meses usando rolling().apply()
                    # raw=False é importante para passar a série correta para a função
                    historical_df_monthly[rolling_accum_col_name] = historical_df_monthly[index_name].rolling(
                        window=window_size,
                        min_periods=window_size # Garante que só calcula com 12 períodos completos
                    ).apply(calculate_rolling_12m_accumulation, raw=False)

                    # Seleciona apenas a coluna calculada e remove NaNs (gerados no início do rolling)
                    df_to_store = historical_df_monthly[[rolling_accum_col_name]].dropna()

                    if not df_to_store.empty:
                        historical_rolling_dfs[index_name] = df_to_store
                        valid_hist_indices.append(index_name)
                    else:
                        print(f"Histórico: DataFrame acumulado 12m vazio para {index_name} após cálculo/dropna.")
                else:
                     print(f"Histórico: Nenhum dado mensal encontrado para {index_name} no período de busca.")
            else:
                 st.warning(f"Índice histórico '{index_name}' não reconhecido.")

    # Se nenhum histórico pôde ser calculado
    if not valid_hist_indices:
        st.error("Não foi possível calcular o histórico acumulado em 12 meses para nenhum dos índices selecionados.")
        st.stop()

    # Combina os DataFrames de acumulado 12m (um por índice)
    combined_rolling_df = None
    try:
        if historical_rolling_dfs:
            # Concatena usando as colunas calculadas (e nomes dos índices)
            combined_rolling_df = pd.concat(historical_rolling_dfs.values(), axis=1)
            # Renomeia as colunas para os nomes dos índices (sem o sufixo _Acum12M) para o gráfico
            rename_map = {f"{name}_Acum12M": name for name in valid_hist_indices}
            combined_rolling_df.rename(columns=rename_map, inplace=True)
            combined_rolling_df = combined_rolling_df.sort_index() # Garante ordem cronológica
        else:
            st.warning("Nenhum DataFrame histórico válido para concatenar após cálculos.")
            st.stop()
    except Exception as e:
        st.error(f"Erro ao combinar dados históricos acumulados: {e}")
        st.stop()

    # Se a combinação falhar
    if combined_rolling_df is None or combined_rolling_df.empty:
        st.error("Falha ao criar DataFrame combinado histórico ou resultado vazio.")
        st.stop()

    # Filtra o DataFrame combinado para o período de VISUALIZAÇÃO selecionado pelo usuário
    end_date_display = today_hist
    # Calcula a data de início da visualização baseada nos meses selecionados
    start_date_display = end_date_display - pd.DateOffset(months=months_in_range)
    # Garante que não tenta exibir antes da data mínima disponível no DF combinado
    start_date_display = max(pd.to_datetime(start_date_display), combined_rolling_df.index.min())


    # Filtra o DataFrame para o período de exibição
    combined_rolling_df_display = combined_rolling_df[
        (combined_rolling_df.index >= pd.to_datetime(start_date_display)) &
        (combined_rolling_df.index <= pd.to_datetime(end_date_display))
    ].copy() # .copy() para evitar SettingWithCopyWarning

    # Remove linhas que só contenham NaN no período de exibição
    combined_rolling_df_display.dropna(axis=0, how='all', inplace=True)

    # Exibe o gráfico e dados se houver algo para mostrar
    if not combined_rolling_df_display.empty:
        actual_start_display = combined_rolling_df_display.index.min().strftime('%m/%Y')
        actual_end_display = combined_rolling_df_display.index.max().strftime('%m/%Y')
        st.markdown(f"**Médias do Acum. 12M no Período Selecionado ({actual_start_display} a {actual_end_display}):**")

        # Exibe métricas da média do acumulado 12m no período visualizado
        cols_hist_metrics = st.columns(len(valid_hist_indices)) if len(valid_hist_indices) > 0 else [st]
        idx_hist_col = 0
        for index_name in valid_hist_indices: # Itera sobre os índices que têm dados
            if index_name in combined_rolling_df_display.columns:
                # Calcula a média da coluna (que representa o acum. 12m)
                average_val = combined_rolling_df_display[index_name].mean()
                if pd.notna(average_val):
                    current_col = cols_hist_metrics[idx_hist_col % len(valid_hist_indices)] if len(valid_hist_indices)>0 else st
                    with current_col:
                         help_text = f"Média da inflação acumulada em 12 meses de {index_name} entre {actual_start_display} e {actual_end_display}."
                         st.metric(label=f"{index_name}", value=f"{average_val:.2f}%", help=help_text)
                    idx_hist_col += 1

        # Plota o gráfico de linhas
        st.line_chart(combined_rolling_df_display)

        # Expander para mostrar os dados do gráfico
        with st.expander("Ver dados do gráfico (Inflação Acumulada 12 Meses %)"):
            st.dataframe(combined_rolling_df_display.style.format("{:.2f}", na_rep="-"))
    else:
        # Mensagem se não houver dados no período de visualização selecionado
        st.info(f"Não há dados de inflação acumulada em 12 meses para os índices selecionados no período ({selected_range_label}) após o cálculo.")
else:
    # Mensagem se nenhum índice for selecionado para o histórico
    st.info("👆 Selecione um ou mais índices acima para visualizar o histórico comparativo.")


# --- Seção de Cálculo de Reajuste de Aluguel ---
st.divider()
st.header("💸 Calculadora de Reajuste de Aluguel")
st.markdown("Simule o reajuste do seu aluguel com base em diferentes índices (individuais, média ou mínimo de combinações).")

# --- Inputs para o Cálculo do Aluguel ---
rent_col1, rent_col2 = st.columns(2)
with rent_col1:
    initial_rent = st.number_input(
        "Valor Inicial do Aluguel (R$):",
        min_value=0.01, value=1000.0, step=100.0, format="%.2f",
        key="rent_initial_value"
    )
    # Data de início: Pelo menos 1 mês atrás
    contract_start_date = st.date_input(
        "Data de Início do Contrato:",
        value=date.today() - timedelta(days=365*2), # Default 2 anos atrás
        max_value=date.today() - timedelta(days=31), # Máximo 1 mês atrás
        help="A data que define o mês de aniversário do reajuste.",
        key="rent_start_date"
    )
with rent_col2:
    # Opção para selecionar o índice REALMENTE usado no contrato
    rent_index_options = ["Selecione o índice..."] + list(INDICES_IDS.keys())
    actual_rent_index = st.selectbox(
        "Índice Aplicado no Contrato Real:",
        options=rent_index_options,
        index=0, # Default "Selecione..."
        help="Qual índice consta no seu contrato para reajuste anual?",
        key="rent_actual_index"
    )
    # Data final: Pelo menos 1 mês depois do início
    contract_end_date = st.date_input(
        "Data Final do Contrato (ou data desejada para simulação):",
        value=date.today(), # Default hoje
        min_value=contract_start_date + timedelta(days=30),
        max_value=date.today() + timedelta(days=365*10), # Limite futuro
        key="rent_end_date"
    )

# Botão para iniciar o cálculo
calculate_button = st.button("Calcular Reajuste e Comparar Cenários", key="rent_calculate_btn")

# --- Lógica do Cálculo (Executa ao clicar no botão e se índice real foi selecionado) ---
if calculate_button and actual_rent_index != "Selecione o índice...":

    # 1. Determinar período de busca e buscar dados MENSAIS para TODOS os índices base
    # Busca desde 12 meses ANTES do início do contrato para ter dados pro 1º reajuste
    fetch_start_date = pd.to_datetime(contract_start_date) - pd.DateOffset(months=12)
    fetch_end_date = pd.to_datetime(contract_end_date) # Usa a data final fornecida

    all_base_indices = list(INDICES_IDS.keys()) # Lista de todos os índices disponíveis
    monthly_data_all_indices = {} # Dicionário para guardar DFs mensais
    failed_indices_fetch = [] # Guarda nomes dos que falharam na busca

    with st.spinner(f"Buscando dados mensais ({fetch_start_date.strftime('%m/%Y')} a {fetch_end_date.strftime('%m/%Y')})..."):
        for index_name in all_base_indices:
            codigo_sgs = INDICES_IDS[index_name]
            # Busca os dados mensais
            df_monthly = get_bcb_data(codigo_sgs=codigo_sgs, start_date=fetch_start_date.date(), end_date=fetch_end_date.date())

            if df_monthly is not None and not df_monthly.empty:
                col_name_sgs = f'sgs_{codigo_sgs}'
                if col_name_sgs in df_monthly.columns:
                    df_monthly = df_monthly.rename(columns={col_name_sgs: index_name})
                    monthly_data_all_indices[index_name] = df_monthly[[index_name]] # Guarda só a coluna do índice
                else:
                    failed_indices_fetch.append(index_name) # Falha se coluna não encontrada
            else:
                failed_indices_fetch.append(index_name) # Falha se não retornou dados

    # Verifica se o índice REAL do contrato foi obtido
    if actual_rent_index not in monthly_data_all_indices:
        st.error(f"Dados históricos mensais ausentes para o índice base do contrato ({actual_rent_index}). Não é possível continuar.")
        st.stop()

    # Avisa sobre outros índices que falharam (para a comparação)
    if failed_indices_fetch:
        st.warning(f"Não foi possível obter dados mensais para comparar com: {', '.join(failed_indices_fetch)}")

    valid_base_indices = list(monthly_data_all_indices.keys()) # Índices que tiveram dados mensais obtidos

    # 2. PRÉ-CALCULAR Acumulado 12 Meses para TODOS os índices base válidos
    # Isso evita recalcular o rolling para cada cenário de simulação
    rolling_12m_all_indices = {} # Dicionário para guardar as séries Acum12m pré-calculadas

    with st.spinner("Calculando acumulado 12 meses para índices base..."):
        for index_name in valid_base_indices:
            df_monthly = monthly_data_all_indices[index_name] # Pega o DF mensal
            rolling_accum_col = f"{index_name}_Acum12M" # Nome da coluna de acumulado

            df_monthly.index = pd.to_datetime(df_monthly.index) # Garante DatetimeIndex
            # Calcula o rolling e guarda na coluna nova
            df_monthly[rolling_accum_col] = df_monthly[index_name].rolling(
                window=12, min_periods=12
            ).apply(calculate_rolling_12m_accumulation, raw=False)

            # Guarda SOMENTE a série de acumulado 12m (sem NaNs iniciais) no dicionário
            rolling_12m_all_indices[index_name] = df_monthly[[rolling_accum_col]].dropna()

    # 3. Função para Simular Pagamentos (aceita nomes de índices base, média ou mínimo)
    def simulate_rent_payments_v3(start_rent, start_date, end_date, simulation_index_name, precalculated_rolling_data):
        """Simula pagamentos de aluguel mês a mês, aplicando reajuste anual."""
        payment_history = []
        current_rent = start_rent
        total_paid = 0.0
        # Gera o range de meses do contrato
        date_range = pd.date_range(start=start_date, end=end_date, freq='MS') # MS = Month Start

        base_indices_in_sim = []
        sim_type = "base" # Tipo de simulação: 'base', 'media', 'minimo'

        # --- Identifica o tipo de simulação e os índices base envolvidos ---
        if simulation_index_name.startswith("Média (") and simulation_index_name.endswith(")"):
            sim_type = "media"
            # Extrai os nomes dos índices da string (ex: "Média (IGP-M, IPCA)")
            try: base_indices_in_sim = [idx.strip() for idx in re.findall(r'\((.*?)\)', simulation_index_name)[0].split(',')]
            except IndexError: return None, 0, f"Formato inválido para Média: {simulation_index_name}"
        elif simulation_index_name.startswith("Mínimo (") and simulation_index_name.endswith(")"):
            sim_type = "minimo"
            try: base_indices_in_sim = [idx.strip() for idx in re.findall(r'\((.*?)\)', simulation_index_name)[0].split(',')]
            except IndexError: return None, 0, f"Formato inválido para Mínimo: {simulation_index_name}"
        elif simulation_index_name in precalculated_rolling_data:
            sim_type = "base"
            base_indices_in_sim = [simulation_index_name]
        else:
            # Se o nome não corresponde a nenhum formato conhecido ou índice base
            return None, 0, f"Índice/Cenário '{simulation_index_name}' inválido ou sem dados pré-calculados."

        # Verifica se temos os dados pré-calculados para TODOS os índices base necessários
        missing_data = [idx for idx in base_indices_in_sim if idx not in precalculated_rolling_data]
        if missing_data:
            return None, 0, f"Dados acumulados 12m ausentes para simular com: {', '.join(missing_data)}"
        #-------------------------------------------------------------------------

        # Itera sobre cada mês do contrato
        for current_month_start in date_range:
            adjustment_perc = pd.NA # Percentual de reajuste aplicado (NA se não for mês de reajuste)
            adjusted_value = 0.0 # Valor do reajuste (0 se não houver)

            # Verifica se é mês de aniversário do contrato (e não o primeiro mês)
            if current_month_start.month == pd.Timestamp(start_date).month and current_month_start > pd.Timestamp(start_date):

                # A data do índice para reajuste é o mês ANTERIOR ao mês do reajuste
                adjustment_index_date = current_month_start - pd.DateOffset(months=1)
                # Converte para Period('M') para buscar no índice pré-calculado
                adjustment_month_period = adjustment_index_date.to_period('M')

                accum_values_for_month = [] # Guarda os valores acumulados 12m dos índices base
                indices_found_for_month = True # Flag para verificar se todos foram encontrados

                # Busca o valor acumulado 12m para cada índice base necessário
                for base_idx in base_indices_in_sim:
                    rolling_col = f"{base_idx}_Acum12M" # Nome da coluna pré-calculada
                    try:
                        # Busca o valor no DataFrame pré-calculado correspondente ao mês/ano
                        val = precalculated_rolling_data[base_idx].loc[precalculated_rolling_data[base_idx].index.to_period('M') == adjustment_month_period, rolling_col].iloc[0]
                        if pd.notna(val):
                            accum_values_for_month.append(val)
                        else:
                            # Se UM valor for NA, não podemos calcular média/mínimo confiavelmente
                            indices_found_for_month = False; break
                    except IndexError:
                        # Mês/Ano não encontrado nos dados pré-calculados (raro, mas possível)
                        print(f"Simulação {simulation_index_name}: Índice {base_idx} não encontrado para {adjustment_month_period}")
                        indices_found_for_month = False; break
                    except Exception as e:
                         print(f"Simulação {simulation_index_name}: Erro buscando {base_idx} em {adjustment_month_period}: {e}")
                         indices_found_for_month = False; break

                # Se todos os valores necessários foram encontrados com sucesso
                if indices_found_for_month and accum_values_for_month:
                    # Aplica a lógica baseada no tipo de simulação
                    if sim_type == "base":
                        adjustment_perc = accum_values_for_month[0] # Pega o único valor
                    elif sim_type == "media":
                        adjustment_perc = sum(accum_values_for_month) / len(accum_values_for_month)
                    elif sim_type == "minimo":
                        adjustment_perc = min(accum_values_for_month)

                    # Se o percentual foi calculado (não é NA)
                    if pd.notna(adjustment_perc):
                        new_rent = current_rent * (1 + adjustment_perc / 100)
                        adjusted_value = new_rent - current_rent # Calcula a diferença
                        current_rent = new_rent # Atualiza o aluguel para os próximos meses
                    else:
                        # Caso onde o cálculo da média/min resultou em NA (pode acontecer?)
                         adjustment_perc = pd.NA # Garante que fica NA
                         print(f"Simulação {simulation_index_name}: Cálculo de ajuste resultou em NA para {current_month_start.strftime('%m/%Y')}")


            # Adiciona o registro do mês ao histórico
            payment_history.append({
                "Mês/Ano": current_month_start.strftime("%m/%Y"),
                "Índice Mês Reajuste (%)": adjustment_perc if pd.notna(adjustment_perc) else None, # Só mostra se houve reajuste
                "Valor Reajuste (R$)": adjusted_value if adjusted_value != 0 else None,
                "Aluguel Pago (R$)": current_rent
            })
            total_paid += current_rent # Acumula o total pago

        # Cria o DataFrame do histórico
        history_df = pd.DataFrame(payment_history)
        return history_df, total_paid, None # Retorna DF, Total e None (sem erro)


    # 4. Simular o Contrato Real (usando o índice selecionado pelo usuário)
    st.subheader(f"Simulação do Contrato Real (Índice: {actual_rent_index})")
    actual_history_df, actual_total_paid, error_msg = simulate_rent_payments_v3(
        initial_rent, contract_start_date, contract_end_date, actual_rent_index, rolling_12m_all_indices
    )

    # Se houve erro na simulação real, para aqui
    if error_msg:
        st.error(f"Erro crítico ao simular o contrato real: {error_msg}")
        st.stop()

    # Exibe o histórico e o total pago do contrato real
    if actual_history_df is not None:
        st.dataframe(
            actual_history_df.style.format({
                "Índice Mês Reajuste (%)": "{:.2f}%",
                "Valor Reajuste (R$)": "R$ {:,.2f}",
                "Aluguel Pago (R$)": "R$ {:,.2f}",
            }, na_rep="-").hide(axis="index") # Esconde o índice do DF
        )
        st.metric(label=f"Total Pago Estimado com {actual_rent_index} (R$)", value=f"{actual_total_paid:,.2f}")
    else:
        st.error("Não foi possível gerar o histórico de pagamentos para o contrato real.")
        st.stop() # Para se a simulação real falhou por algum motivo inesperado

    # 5. Gerar Opções Combinadas e Simular Comparações
    st.subheader("Comparação com Outros Cenários de Reajuste")
    comparison_results = [] # Lista para guardar os resultados das comparações
    indices_to_compare_final = [] # Lista de nomes dos cenários a comparar

    # Adiciona os índices base (exceto o já usado no contrato real)
    indices_to_compare_final.extend([idx for idx in valid_base_indices if idx != actual_rent_index])

    # Gera nomes para cenários de Média e Mínimo (combinações de 2 e 3 índices)
    # Limita a 3 para não gerar combinações demais
    max_combo_size = min(len(valid_base_indices), 3)
    for r in range(2, max_combo_size + 1):
        for combo in combinations(valid_base_indices, r):
            combo_str = ", ".join(combo)
            # Adiciona os nomes formatados à lista de cenários
            indices_to_compare_final.append(f"Média ({combo_str})")
            indices_to_compare_final.append(f"Mínimo ({combo_str})")

    # Se houver cenários para comparar
    if indices_to_compare_final:
        with st.spinner("Simulando outros cenários de reajuste..."):
            for sim_index_name in indices_to_compare_final:
                # Roda a simulação para cada cenário
                sim_history_df, sim_total_paid, error_msg_sim = simulate_rent_payments_v3(
                    initial_rent, contract_start_date, contract_end_date, sim_index_name, rolling_12m_all_indices
                )

                status = "Calculado"
                difference = pd.NA # Diferença em relação ao contrato real

                if error_msg_sim:
                    status = f"Erro: {error_msg_sim}" # Mostra a mensagem de erro específica
                    sim_total_paid = pd.NA # Define total como NA se houve erro
                elif sim_total_paid is not None and pd.notna(sim_total_paid):
                    # Calcula a diferença apenas se a simulação foi bem-sucedida
                    difference = sim_total_paid - actual_total_paid
                else:
                    # Caso de erro inesperado onde não houve mensagem mas total é None/NA
                    status = "Erro desconhecido na simulação"
                    sim_total_paid = pd.NA

                # Adiciona o resultado à lista
                comparison_results.append({
                    "Cenário Simulado": sim_index_name,
                    "Total Pago Simulado (R$)": sim_total_paid,
                    "Diferença vs Contrato (R$)": difference,
                    "Status": status
                })

        # Se a lista de resultados não estiver vazia
        if comparison_results:
            # Cria o DataFrame de comparação
            comparison_df = pd.DataFrame(comparison_results)
            # Ordena pela diferença (menor diferença primeiro), colocando erros no final
            comparison_df = comparison_df.sort_values(by="Diferença vs Contrato (R$)", ascending=True, na_position='last')

            # Exibe o DataFrame formatado
            st.dataframe(
                comparison_df.style.format({
                    "Total Pago Simulado (R$)": "R$ {:,.2f}",
                    "Diferença vs Contrato (R$)": "{:+,.2f}" # Sinal de + ou -
                }, na_rep="-")
                .applymap( # Colore a diferença: vermelho > 0, verde < 0
                    lambda x: 'color: red' if isinstance(x, (int, float)) and x > 0 else ('color: green' if isinstance(x, (int, float)) and x < 0 else ''),
                    subset=['Diferença vs Contrato (R$)']
                ).hide(axis="index") # Esconde o índice do DF
            )
        else:
            st.info("Não foi possível calcular nenhum cenário de comparação.")
    else:
        st.info("Não há outros índices com dados disponíveis para gerar cenários de comparação.")

# --- Fim da Seção de Cálculo de Reajuste de Aluguel ---

# --- Rodapé na Barra Lateral ---
st.sidebar.markdown("---")
st.sidebar.info("Fonte dos Dados: API de Séries Temporais do Banco Central do Brasil (BCB SGS).")
st.sidebar.markdown("Cache de dados da API ativo por **1 hora**.")
# st.sidebar.info("Criado por Riuler") # Descomente se quiser
