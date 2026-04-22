import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import glob
import os
from datetime import timedelta

# =========================================================
# CONFIGURAÇÃO GERAL
# =========================================================
st.set_page_config(
    page_title="Dashboard ONS - Sistema Elétrico",
    page_icon="⚡",
    layout="wide",
)

st.markdown("""
<style>
    .kpi-box {
        background-color: #1E1E1E;
        border-radius: 10px;
        padding: 18px;
        text-align: center;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.25);
        margin-bottom: 16px;
        border: 1px solid #2a2a2a;
    }
    .kpi-title { color: #A0A0A0; font-size: 14px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.4px; }
    .kpi-value { color: #00E676; font-size: 26px; font-weight: 700; line-height: 1.1; }
    .kpi-sub   { color: #B0B0B0; font-size: 12px; margin-top: 4px; }
    .kpi-delta-up   { color: #00E676; font-size: 13px; margin-top: 4px; font-weight: 600; }
    .kpi-delta-down { color: #FF5252; font-size: 13px; margin-top: 4px; font-weight: 600; }
    .alert-critical { background:#5A1A1A; border-left:4px solid #FF5252; padding:8px; border-radius:4px; margin-bottom:6px; font-size:13px; }
    .alert-warning  { background:#5A4A1A; border-left:4px solid #FFA726; padding:8px; border-radius:4px; margin-bottom:6px; font-size:13px; }
    .alert-ok       { background:#1A4A1A; border-left:4px solid #00E676; padding:8px; border-radius:4px; margin-bottom:6px; font-size:13px; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# CARREGAMENTO DE DADOS
# =========================================================
DADOS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dados")

# Alguns CSVs trazem o mesmo subsistema em grafias diferentes (ex.: "Norte", "NORTE",
# "SUDESTE/CENTRO-OESTE" vs "SUDESTE"). Normalizamos para evitar falha silenciosa do filtro.
MAPA_SUBSISTEMA = {
    "NORTE": "NORTE", "Norte": "NORTE",
    "NORDESTE": "NORDESTE", "Nordeste": "NORDESTE",
    "SUL": "SUL", "Sul": "SUL",
    "SUDESTE": "SUDESTE/CENTRO-OESTE", "Sudeste": "SUDESTE/CENTRO-OESTE",
    "SUDESTE/CENTRO-OESTE": "SUDESTE/CENTRO-OESTE", "Sudeste/Centro-Oeste": "SUDESTE/CENTRO-OESTE",
    "SISTEMA INTERLIGADO NACIONAL": "SIN", "SIN": "SIN",
}

SUBSISTEMAS_REGIONAIS = ["NORTE", "NORDESTE", "SUDESTE/CENTRO-OESTE", "SUL"]

CORES_SUBSISTEMA = {
    "NORTE": "#66BB6A",
    "NORDESTE": "#FFA726",
    "SUDESTE/CENTRO-OESTE": "#42A5F5",
    "SUL": "#AB47BC",
    "SIN": "#BDBDBD",
}

CORES_FONTES = {
    "val_gerhidraulica": "#2196F3",
    "val_gertermica": "#F44336",
    "val_gereolica": "#00BCD4",
    "val_gersolar": "#FFEB3B",
}
NOMES_FONTES = {
    "val_gerhidraulica": "Hidrelétrica",
    "val_gertermica": "Termelétrica",
    "val_gereolica": "Eólica",
    "val_gersolar": "Solar",
}

@st.cache_data(show_spinner=False)
def carregar_dados(padrao_arquivo, coluna_data):
    arquivos = glob.glob(os.path.join(DADOS_PATH, padrao_arquivo))
    if not arquivos:
        return pd.DataFrame()

    lista_df = []
    for arquivo in arquivos:
        try:
            lista_df.append(pd.read_csv(arquivo, sep=";"))
        except Exception as e:
            st.error(f"Erro ao ler {arquivo}: {e}")

    df = pd.concat(lista_df, ignore_index=True) if lista_df else pd.DataFrame()
    if coluna_data in df.columns:
        df[coluna_data] = pd.to_datetime(df[coluna_data], errors="coerce")
        df = df.dropna(subset=[coluna_data])
    if "nom_subsistema" in df.columns:
        df["nom_subsistema"] = df["nom_subsistema"].map(lambda x: MAPA_SUBSISTEMA.get(x, x))
    return df.sort_values(coluna_data) if coluna_data in df.columns else df

@st.cache_data(show_spinner="Carregando dados do ONS...")
def carregar_todos_dados():
    return (
        carregar_dados("BALANCO_ENERGIA_SUBSISTEMA_*.csv", "din_instante"),
        carregar_dados("CARGA_ENERGIA_*.csv", "din_instante"),
        carregar_dados("CMO_SEMANAL_*.csv", "din_instante"),
        carregar_dados("EAR_DIARIO_SUBSISTEMA_*.csv", "ear_data"),
        carregar_dados("ENA_DIARIO_SUBSISTEMA_*.csv", "ena_data"),
    )

df_balanco, df_carga, df_cmo, df_ear, df_ena = carregar_todos_dados()

if df_balanco.empty and df_ear.empty and df_carga.empty:
    st.error("Nenhum dado encontrado. Verifique o caminho da pasta de dados.")
    st.stop()

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.title("⚡ Filtros Globais")
st.sidebar.caption("Período e subsistemas aplicados em todas as abas.")

# --- Presets de período ---
if not df_balanco.empty:
    base_date = df_balanco["din_instante"]
elif not df_ear.empty:
    base_date = df_ear["ear_data"]
else:
    base_date = df_carga["din_instante"]
data_min = base_date.min().date()
data_max = base_date.max().date()

def _clamp_periodo(inicio, fim):
    inicio = max(data_min, min(data_max, inicio))
    fim = max(data_min, min(data_max, fim))
    if inicio > fim:
        inicio, fim = data_min, data_max
    return inicio, fim

preset = st.sidebar.selectbox(
    "Período pré-definido",
    [
        "Personalizado",
        "Todo o histórico",
        "Último ano",
        "Últimos 6 meses",
        "Ano atual",
        "Crise Hídrica 2021",
    ],
    index=1,
)

if preset == "Todo o histórico":
    default_inicio, default_fim = data_min, data_max
elif preset == "Último ano":
    default_inicio, default_fim = _clamp_periodo(data_max - timedelta(days=365), data_max)
elif preset == "Últimos 6 meses":
    default_inicio, default_fim = _clamp_periodo(data_max - timedelta(days=180), data_max)
elif preset == "Ano atual":
    default_inicio, default_fim = _clamp_periodo(pd.Timestamp(year=data_max.year, month=1, day=1).date(), data_max)
elif preset == "Crise Hídrica 2021":
    default_inicio, default_fim = _clamp_periodo(pd.Timestamp("2021-05-01").date(), pd.Timestamp("2022-04-30").date())
else:
    default_inicio, default_fim = data_min, data_max

periodo = st.sidebar.date_input(
    "Selecione o Período",
    value=[default_inicio, default_fim],
    min_value=data_min,
    max_value=data_max,
)
if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
    data_inicio, data_fim = periodo
else:
    data_inicio, data_fim = default_inicio, default_fim

subsistema_selecionado = st.sidebar.multiselect(
    "Subsistemas",
    options=SUBSISTEMAS_REGIONAIS,
    default=SUBSISTEMAS_REGIONAIS,
)
if not subsistema_selecionado:
    st.sidebar.warning("Selecione ao menos um subsistema.")
    st.stop()

# =========================================================
# APLICAÇÃO DE FILTROS
# =========================================================
def filtrar(df, coluna_data, incluir_sin=False):
    if df.empty:
        return df
    mask_data = (df[coluna_data].dt.date >= data_inicio) & (df[coluna_data].dt.date <= data_fim)
    if "nom_subsistema" in df.columns:
        subs = subsistema_selecionado + (["SIN"] if incluir_sin else [])
        mask_sub = df["nom_subsistema"].isin(subs)
        return df[mask_data & mask_sub]
    return df[mask_data]

df_balanco_reg = filtrar(df_balanco, "din_instante", incluir_sin=False)
df_carga_f = filtrar(df_carga, "din_instante")
df_cmo_f = filtrar(df_cmo, "din_instante")
df_ear_f = filtrar(df_ear, "ear_data")
df_ena_f = filtrar(df_ena, "ena_data")

# =========================================================
# SIDEBAR - ALERTAS DINÂMICOS
# =========================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🚨 Alertas (EAR mais recente)")
if not df_ear_f.empty:
    ultimos_ear = (
        df_ear_f.sort_values("ear_data")
        .groupby("nom_subsistema")
        .tail(1)
        .sort_values("nom_subsistema")
    )

    # SIN: média ponderada pela capacidade (ear_max) das últimas medições regionais
    sin_pct = None
    if {"ear_verif_subsistema_mwmes", "ear_max_subsistema"}.issubset(ultimos_ear.columns):
        soma_max = ultimos_ear["ear_max_subsistema"].sum()
        if soma_max > 0:
            sin_pct = ultimos_ear["ear_verif_subsistema_mwmes"].sum() / soma_max * 100

    def _render_alerta(sub, valor):
        if valor < 30:
            classe, icone = "alert-critical", "🔴"
        elif valor < 50:
            classe, icone = "alert-warning", "🟡"
        else:
            classe, icone = "alert-ok", "🟢"
        st.sidebar.markdown(
            f'<div class="{classe}">{icone} <b>{sub}</b>: {valor:.1f}%</div>',
            unsafe_allow_html=True,
        )

    if sin_pct is not None:
        _render_alerta("SIN (Nacional)", sin_pct)
    for _, row in ultimos_ear.iterrows():
        _render_alerta(row["nom_subsistema"], row["ear_verif_subsistema_percentual"])
else:
    st.sidebar.caption("Sem dados de EAR no período.")

# =========================================================
# HELPERS
# =========================================================
def kpi_card(titulo, valor, prefixo="", sufixo="", subtexto=None, delta=None, delta_inverso=False):
    """delta_inverso=True: queda é boa (ex.: geração térmica caindo indica sistema saudável)."""
    delta_html = ""
    if delta is not None and pd.notna(delta):
        positivo = delta >= 0
        classe = "kpi-delta-up" if (positivo ^ delta_inverso) else "kpi-delta-down"
        seta = "▲" if positivo else "▼"
        delta_html = f'<div class="{classe}">{seta} {abs(delta):.1f}% vs período anterior</div>'
    sub_html = f'<div class="kpi-sub">{subtexto}</div>' if subtexto else ""
    st.markdown(
        f"""
        <div class="kpi-box">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{prefixo}{valor}{sufixo}</div>
            {sub_html}
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

def delta_pct(atual, anterior):
    if anterior is None or anterior == 0 or pd.isna(anterior) or pd.isna(atual):
        return None
    return (atual - anterior) / anterior * 100

def calcular_periodo_anterior():
    dias = (data_fim - data_inicio).days + 1
    return data_inicio - timedelta(days=dias), data_inicio - timedelta(days=1)

def filtrar_por_data(df, coluna, ini, fim):
    if df.empty:
        return df
    return df[(df[coluna].dt.date >= ini) & (df[coluna].dt.date <= fim)]

def botao_download(df, nome_arquivo, label="📥 Baixar dados filtrados (CSV)"):
    if df.empty:
        return
    csv = df.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(label=label, data=csv, file_name=nome_arquivo, mime="text/csv")

# =========================================================
# TÍTULO + ABAS
# =========================================================
st.title("Análise do Sistema Elétrico Brasileiro (ONS)")
st.caption(
    f"Período ativo: **{data_inicio.strftime('%d/%m/%Y')} → {data_fim.strftime('%d/%m/%Y')}**  |  "
    f"Subsistemas: **{', '.join(subsistema_selecionado)}**"
)

abas = st.tabs([
    "🏠 Visão Geral",
    "🛡️ Segurança Energética",
    "🍃 Transição Energética",
    "🗺️ Subsistemas & Intercâmbio",
    "📅 Sazonalidade",
    "💰 Custo (CMO)",
    "🌧️ Impacto das Chuvas (ENA)",
    "📊 Comparação Anual",
])

# =========================================================
# ABA 1 - VISÃO GERAL
# =========================================================
with abas[0]:
    st.header("Visão Geral do Sistema")
    st.markdown("Resumo executivo com os principais indicadores do período selecionado.")

    ini_ant, fim_ant = calcular_periodo_anterior()
    df_ear_ant = filtrar_por_data(df_ear, "ear_data", ini_ant, fim_ant)
    df_ear_ant = df_ear_ant[df_ear_ant["nom_subsistema"].isin(subsistema_selecionado)]
    df_carga_ant = filtrar_por_data(df_carga, "din_instante", ini_ant, fim_ant)
    df_carga_ant = df_carga_ant[df_carga_ant["nom_subsistema"].isin(subsistema_selecionado)]
    df_cmo_ant = filtrar_por_data(df_cmo, "din_instante", ini_ant, fim_ant)
    df_cmo_ant = df_cmo_ant[df_cmo_ant["nom_subsistema"].isin(subsistema_selecionado)]
    df_balanco_ant = filtrar_por_data(df_balanco, "din_instante", ini_ant, fim_ant)
    df_balanco_ant = df_balanco_ant[df_balanco_ant["nom_subsistema"].isin(subsistema_selecionado)]

    ear_atual = df_ear_f["ear_verif_subsistema_percentual"].mean() if not df_ear_f.empty else None
    ear_ant = df_ear_ant["ear_verif_subsistema_percentual"].mean() if not df_ear_ant.empty else None
    carga_atual = df_carga_f["val_cargaenergiamwmed"].mean() if not df_carga_f.empty else None
    carga_ant = df_carga_ant["val_cargaenergiamwmed"].mean() if not df_carga_ant.empty else None
    cmo_atual = df_cmo_f["val_cmomediasemanal"].mean() if not df_cmo_f.empty else None
    cmo_ant = df_cmo_ant["val_cmomediasemanal"].mean() if not df_cmo_ant.empty else None
    termo_atual = df_balanco_reg["val_gertermica"].mean() if not df_balanco_reg.empty else None
    termo_ant = df_balanco_ant["val_gertermica"].mean() if not df_balanco_ant.empty else None

    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("EAR Médio", f"{ear_atual:.1f}" if ear_atual is not None else "—", sufixo="%", delta=delta_pct(ear_atual, ear_ant))
    with c2: kpi_card("Carga Média", f"{carga_atual:,.0f}" if carga_atual is not None else "—", sufixo=" MWmed", delta=delta_pct(carga_atual, carga_ant))
    with c3: kpi_card("CMO Médio", f"{cmo_atual:,.2f}" if cmo_atual is not None else "—", prefixo="R$ ", delta=delta_pct(cmo_atual, cmo_ant), delta_inverso=True)
    with c4: kpi_card("Geração Térmica", f"{termo_atual:,.0f}" if termo_atual is not None else "—", sufixo=" MWmed", delta=delta_pct(termo_atual, termo_ant), delta_inverso=True)

    # Matriz de geração (pizza) do período
    st.subheader("Matriz de Geração do Período")
    col_pizza, col_texto = st.columns([1, 1])
    if not df_balanco_reg.empty:
        fontes = list(CORES_FONTES.keys())
        totais = df_balanco_reg[fontes].sum()
        df_pizza = pd.DataFrame({
            "Fonte": [NOMES_FONTES[f] for f in fontes],
            "Total": totais.values,
        })
        fig_pizza = px.pie(
            df_pizza, values="Total", names="Fonte", hole=0.5,
            color="Fonte",
            color_discrete_map={NOMES_FONTES[f]: CORES_FONTES[f] for f in fontes},
        )
        fig_pizza.update_traces(textposition="outside", textinfo="label+percent")
        with col_pizza:
            st.plotly_chart(fig_pizza, use_container_width=True)

        with col_texto:
            df_pizza["%"] = df_pizza["Total"] / df_pizza["Total"].sum() * 100
            df_pizza = df_pizza.sort_values("%", ascending=False)
            st.markdown("**Participação por fonte:**")
            for _, r in df_pizza.iterrows():
                st.markdown(f"- **{r['Fonte']}**: {r['%']:.1f}%")
            renovaveis = df_pizza[df_pizza["Fonte"].isin(["Hidrelétrica", "Eólica", "Solar"])]["%"].sum()
            st.success(f"🌱 **Renováveis no período**: {renovaveis:.1f}%")

    # Carga x Geração Total (agregada entre subsistemas selecionados)
    st.subheader("Carga vs Geração Total (diário, subsistemas selecionados)")
    if not df_balanco_reg.empty:
        fontes_cols = list(CORES_FONTES.keys())
        # Soma entre subsistemas por hora → média por dia = MWmed diário
        por_hora = df_balanco_reg.groupby("din_instante")[fontes_cols + ["val_carga"]].sum().reset_index()
        por_hora["geracao_total"] = por_hora[fontes_cols].sum(axis=1)
        por_hora["data"] = por_hora["din_instante"].dt.date
        agg = por_hora.groupby("data")[["geracao_total", "val_carga"]].mean().reset_index()
        agg["data"] = pd.to_datetime(agg["data"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=agg["data"], y=agg["geracao_total"], name="Geração Total", line=dict(color="#00E676", width=2)))
        fig.add_trace(go.Scatter(x=agg["data"], y=agg["val_carga"], name="Carga", line=dict(color="#FF9800", width=2, dash="dot")))
        fig.update_layout(hovermode="x unified", xaxis_title="Data", yaxis_title="MWmed", legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, use_container_width=True)

# =========================================================
# ABA 2 - SEGURANÇA ENERGÉTICA
# =========================================================
with abas[1]:
    st.header("Segurança Energética: EAR vs Geração Térmica")
    st.markdown("Relação entre o nível dos reservatórios e o acionamento de usinas termelétricas.")

    if df_ear_f.empty or df_balanco_reg.empty:
        st.warning("Sem dados suficientes no período/subsistemas selecionados.")
    else:
        # Agrega termelétrica nacional (soma entre subs selecionados por hora → média diária = MWmed)
        termo_por_hora = df_balanco_reg.groupby("din_instante")["val_gertermica"].sum()
        termo_diario = termo_por_hora.groupby(termo_por_hora.index.date).mean()

        c1, c2, c3, c4 = st.columns(4)
        ear_medio = df_ear_f["ear_verif_subsistema_percentual"].mean()
        ear_min = df_ear_f["ear_verif_subsistema_percentual"].min()
        termo_media = termo_diario.mean()
        termo_max = termo_diario.max()

        with c1: kpi_card("EAR Médio", f"{ear_medio:.1f}", sufixo="%")
        with c2: kpi_card("EAR Mínimo", f"{ear_min:.1f}", sufixo="%")
        with c3: kpi_card("Térmica Média", f"{termo_media:,.0f}", sufixo=" MWmed")
        with c4: kpi_card("Térmica Pico (dia)", f"{termo_max:,.0f}", sufixo=" MWmed")

        df_ear_agg = (
            df_ear_f.groupby("ear_data")["ear_verif_subsistema_percentual"].mean().reset_index()
            .rename(columns={"ear_data": "data"})
        )
        df_termo_agg = (
            df_balanco_reg.assign(data=df_balanco_reg["din_instante"].dt.date)
            .groupby("data")["val_gertermica"].mean().reset_index()
        )
        df_termo_agg["data"] = pd.to_datetime(df_termo_agg["data"])
        df_ear_agg["data"] = pd.to_datetime(df_ear_agg["data"])

        fig_dual = go.Figure()
        fig_dual.add_trace(go.Scatter(
            x=df_ear_agg["data"], y=df_ear_agg["ear_verif_subsistema_percentual"],
            name="EAR (%)", line=dict(color="#00E676", width=2),
        ))
        fig_dual.add_trace(go.Scatter(
            x=df_termo_agg["data"], y=df_termo_agg["val_gertermica"],
            name="Geração Térmica (MWmed)", line=dict(color="#FF5252", width=2), yaxis="y2",
        ))
        fig_dual.update_layout(
            title="EAR e Geração Térmica (eixos duplos)",
            xaxis=dict(title="Data"),
            yaxis=dict(title="EAR (%)", side="left"),
            yaxis2=dict(title="Térmica (MWmed)", overlaying="y", side="right"),
            hovermode="x unified",
            legend=dict(orientation="h", y=1.15),
        )
        st.plotly_chart(fig_dual, use_container_width=True)

        st.subheader("Correlação: EAR vs Geração Térmica")
        df_corr = pd.merge(df_ear_agg, df_termo_agg, on="data", how="inner")
        if not df_corr.empty:
            fig_corr = px.scatter(
                df_corr,
                x="ear_verif_subsistema_percentual",
                y="val_gertermica",
                trendline="ols",
                labels={
                    "ear_verif_subsistema_percentual": "EAR (%)",
                    "val_gertermica": "Geração Térmica (MWmed)",
                },
                opacity=0.5,
                color_discrete_sequence=["#FFA726"],
            )
            coef = df_corr[["ear_verif_subsistema_percentual", "val_gertermica"]].corr().iloc[0, 1]
            st.plotly_chart(fig_corr, use_container_width=True)
            st.info(f"💡 Correlação de Pearson = **{coef:.2f}**. Valores negativos indicam que, quando o EAR cai, o despacho térmico sobe — comportamento esperado do operador para preservar a segurança energética.")

# =========================================================
# ABA 3 - TRANSIÇÃO ENERGÉTICA
# =========================================================
with abas[2]:
    st.header("Transição Energética: Matriz de Geração")
    st.markdown("Evolução da participação das diferentes fontes na matriz elétrica.")

    if df_balanco_reg.empty:
        st.warning("Sem dados no período/subsistemas selecionados.")
    else:
        fontes = list(CORES_FONTES.keys())
        df_fontes = df_balanco_reg[["din_instante"] + fontes].copy()
        df_fontes["ano_mes"] = df_fontes["din_instante"].dt.to_period("M").dt.to_timestamp()
        df_agg = df_fontes.groupby("ano_mes")[fontes].sum().reset_index()
        df_agg["total"] = df_agg[fontes].sum(axis=1)
        for f in fontes:
            df_agg[f + "_pct"] = df_agg[f] / df_agg["total"] * 100

        c1, c2, c3, c4 = st.columns(4)
        with c1: kpi_card("Hidrelétrica", f"{df_agg['val_gerhidraulica_pct'].mean():.1f}", sufixo="%")
        with c2: kpi_card("Termelétrica", f"{df_agg['val_gertermica_pct'].mean():.1f}", sufixo="%")
        with c3: kpi_card("Eólica", f"{df_agg['val_gereolica_pct'].mean():.1f}", sufixo="%")
        with c4: kpi_card("Solar", f"{df_agg['val_gersolar_pct'].mean():.1f}", sufixo="%")

        st.subheader("Geração por Fonte ao Longo do Tempo")
        fig_area = go.Figure()
        for f in fontes:
            fig_area.add_trace(go.Scatter(
                x=df_agg["ano_mes"], y=df_agg[f],
                name=NOMES_FONTES[f], stackgroup="one",
                line=dict(width=0.5, color=CORES_FONTES[f]),
            ))
        fig_area.update_layout(hovermode="x unified", xaxis_title="Tempo", yaxis_title="Geração (MWmed · h)")
        st.plotly_chart(fig_area, use_container_width=True)

        st.subheader("Participação Percentual por Fonte (%)")
        fig_pct = go.Figure()
        for f in fontes:
            fig_pct.add_trace(go.Scatter(
                x=df_agg["ano_mes"], y=df_agg[f + "_pct"],
                name=NOMES_FONTES[f], line=dict(color=CORES_FONTES[f], width=2),
            ))
        fig_pct.update_layout(hovermode="x unified", xaxis_title="Tempo", yaxis_title="Participação (%)")
        st.plotly_chart(fig_pct, use_container_width=True)

        # Crescimento renováveis (primeiros vs últimos meses)
        if len(df_agg) >= 6:
            inicio_ren = df_agg.head(3)[["val_gereolica_pct", "val_gersolar_pct"]].sum(axis=1).mean()
            fim_ren = df_agg.tail(3)[["val_gereolica_pct", "val_gersolar_pct"]].sum(axis=1).mean()
            st.info(f"💡 Participação Eólica+Solar: **{inicio_ren:.1f}%** (início) → **{fim_ren:.1f}%** (fim). Crescimento de **{fim_ren - inicio_ren:+.1f} p.p.** no período.")

# =========================================================
# ABA 4 - SUBSISTEMAS & INTERCÂMBIO
# =========================================================
with abas[3]:
    st.header("Análise por Subsistemas")
    st.markdown("Comparativo regional de carga, geração e intercâmbio.")

    if df_carga_f.empty:
        st.warning("Sem dados de carga no período selecionado.")
    else:
        df_sub = (
            df_carga_f.groupby("nom_subsistema")["val_cargaenergiamwmed"].mean().reset_index()
            .sort_values("val_cargaenergiamwmed", ascending=False)
        )
        c1, c2, c3 = st.columns(3)
        with c1: kpi_card("Carga Global Média", f"{df_carga_f['val_cargaenergiamwmed'].mean():,.0f}", sufixo=" MWmed")
        with c2: kpi_card("Maior Consumidor", df_sub.iloc[0]["nom_subsistema"])
        with c3: kpi_card("Menor Consumidor", df_sub.iloc[-1]["nom_subsistema"])

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Carga Média por Subsistema")
            fig_bar = px.bar(
                df_sub, x="nom_subsistema", y="val_cargaenergiamwmed",
                color="nom_subsistema",
                color_discrete_map=CORES_SUBSISTEMA,
                text_auto=".2s",
                labels={"nom_subsistema": "Subsistema", "val_cargaenergiamwmed": "Carga (MWmed)"},
            )
            fig_bar.update_layout(showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_b:
            st.subheader("Evolução Mensal da Carga")
            df_ct = (
                df_carga_f.assign(ano_mes=df_carga_f["din_instante"].dt.to_period("M").dt.to_timestamp())
                .groupby(["ano_mes", "nom_subsistema"])["val_cargaenergiamwmed"].mean().reset_index()
            )
            fig_line = px.line(
                df_ct, x="ano_mes", y="val_cargaenergiamwmed", color="nom_subsistema",
                color_discrete_map=CORES_SUBSISTEMA,
                labels={"ano_mes": "Tempo", "val_cargaenergiamwmed": "Carga (MWmed)", "nom_subsistema": "Subsistema"},
            )
            st.plotly_chart(fig_line, use_container_width=True)

    # Intercâmbio entre subsistemas (usa val_intercambio do BALANCO)
    st.subheader("Intercâmbio Líquido entre Subsistemas")
    st.caption("Valores positivos = subsistema exporta energia ao SIN. Negativos = importa.")
    if not df_balanco_reg.empty and "val_intercambio" in df_balanco_reg.columns:
        df_inter = (
            df_balanco_reg.assign(ano_mes=df_balanco_reg["din_instante"].dt.to_period("M").dt.to_timestamp())
            .groupby(["ano_mes", "nom_subsistema"])["val_intercambio"].mean().reset_index()
        )
        fig_inter = px.bar(
            df_inter, x="ano_mes", y="val_intercambio", color="nom_subsistema", barmode="relative",
            color_discrete_map=CORES_SUBSISTEMA,
            labels={"ano_mes": "Período", "val_intercambio": "Intercâmbio (MWmed)", "nom_subsistema": "Subsistema"},
        )
        fig_inter.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.6)
        st.plotly_chart(fig_inter, use_container_width=True)

    botao_download(df_carga_f, "carga_filtrada.csv", "📥 Baixar dados de Carga (CSV)")

# =========================================================
# ABA 5 - SAZONALIDADE
# =========================================================
with abas[4]:
    st.header("Sazonalidade da Demanda")
    st.markdown("Padrões mensais e anuais de consumo de energia.")

    if df_carga_f.empty:
        st.warning("Sem dados de carga no período.")
    else:
        df_s = df_carga_f.copy()
        df_s["mes"] = df_s["din_instante"].dt.month
        df_s["ano"] = df_s["din_instante"].dt.year

        c1, c2, c3 = st.columns(3)
        with c1: kpi_card("Carga Média", f"{df_s['val_cargaenergiamwmed'].mean():,.0f}", sufixo=" MWmed")
        with c2: kpi_card("Pico de Carga", f"{df_s['val_cargaenergiamwmed'].max():,.0f}", sufixo=" MWmed")
        with c3:
            mes_pico = df_s.groupby("mes")["val_cargaenergiamwmed"].mean().idxmax()
            nomes_mes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            kpi_card("Mês de Maior Consumo", nomes_mes[mes_pico - 1])

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Distribuição Mensal (Boxplot)")
            fig_box = px.box(
                df_s, x="mes", y="val_cargaenergiamwmed", color="mes",
                labels={"mes": "Mês", "val_cargaenergiamwmed": "Carga (MWmed)"},
            )
            fig_box.update_layout(showlegend=False)
            st.plotly_chart(fig_box, use_container_width=True)

        with col_b:
            st.subheader("Mapa de Calor: Ano × Mês")
            df_h = df_s.groupby(["ano", "mes"])["val_cargaenergiamwmed"].mean().reset_index()
            pivot = df_h.pivot(index="mes", columns="ano", values="val_cargaenergiamwmed")
            fig_heat = px.imshow(
                pivot, aspect="auto", color_continuous_scale="Viridis",
                labels=dict(x="Ano", y="Mês", color="Carga (MWmed)"),
            )
            st.plotly_chart(fig_heat, use_container_width=True)

        st.info(f"💡 No período selecionado, o pico médio ocorre em **{nomes_mes[mes_pico - 1]}**. O padrão clássico do SIN mostra picos em meses quentes (verão), impulsionados por refrigeração e ar condicionado.")

# =========================================================
# ABA 6 - CUSTO (CMO)
# =========================================================
with abas[5]:
    st.header("Custo Marginal de Operação (CMO)")
    st.markdown("Volatilidade do custo da energia ao longo do tempo.")

    if df_cmo_f.empty:
        st.warning("Sem dados de CMO no período.")
    else:
        c1, c2, c3 = st.columns(3)
        cmo_med = df_cmo_f["val_cmomediasemanal"].mean()
        cmo_max = df_cmo_f["val_cmomediasemanal"].max()
        cmo_min = df_cmo_f["val_cmomediasemanal"].min()
        with c1: kpi_card("CMO Médio", f"{cmo_med:,.2f}", prefixo="R$ ")
        with c2: kpi_card("CMO Máximo", f"{cmo_max:,.2f}", prefixo="R$ ")
        with c3: kpi_card("CMO Mínimo", f"{cmo_min:,.2f}", prefixo="R$ ")

        st.subheader("Evolução do CMO por Subsistema")
        df_cmo_sem = (
            df_cmo_f.groupby(["din_instante", "nom_subsistema"])["val_cmomediasemanal"].mean().reset_index()
        )
        fig_cmo = px.line(
            df_cmo_sem, x="din_instante", y="val_cmomediasemanal", color="nom_subsistema",
            color_discrete_map=CORES_SUBSISTEMA,
            labels={"din_instante": "Data", "val_cmomediasemanal": "CMO (R$/MWh)", "nom_subsistema": "Subsistema"},
        )
        st.plotly_chart(fig_cmo, use_container_width=True)

        # CMO vs EAR (novo insight)
        if not df_ear_f.empty:
            st.subheader("CMO × EAR: quando reservatórios caem, o custo sobe?")
            df_cmo_ag = df_cmo_f.groupby("din_instante")["val_cmomediasemanal"].mean().reset_index()
            df_cmo_ag.rename(columns={"din_instante": "data"}, inplace=True)
            df_ear_ag = df_ear_f.groupby("ear_data")["ear_verif_subsistema_percentual"].mean().reset_index()
            df_ear_ag.rename(columns={"ear_data": "data"}, inplace=True)
            df_mix = pd.merge_asof(
                df_cmo_ag.sort_values("data"),
                df_ear_ag.sort_values("data"),
                on="data",
                direction="nearest",
            )
            if not df_mix.empty:
                fig_mix = px.scatter(
                    df_mix, x="ear_verif_subsistema_percentual", y="val_cmomediasemanal",
                    trendline="ols", opacity=0.5, color_discrete_sequence=["#FF9800"],
                    labels={"ear_verif_subsistema_percentual": "EAR (%)", "val_cmomediasemanal": "CMO (R$/MWh)"},
                )
                st.plotly_chart(fig_mix, use_container_width=True)
                corr = df_mix[["ear_verif_subsistema_percentual", "val_cmomediasemanal"]].corr().iloc[0, 1]
                st.info(f"💡 Correlação EAR × CMO: **{corr:.2f}**. Quando os reservatórios enchem, o CMO tende a cair.")

        botao_download(df_cmo_f, "cmo_filtrado.csv", "📥 Baixar dados de CMO (CSV)")

# =========================================================
# ABA 7 - IMPACTO DAS CHUVAS (ENA)
# =========================================================
with abas[6]:
    st.header("Impacto das Chuvas: ENA vs EAR")
    st.markdown("Energia Natural Afluente (chuvas/vazão) e nível de Armazenamento (EAR).")

    if df_ena_f.empty or df_ear_f.empty:
        st.warning("Sem dados suficientes de ENA ou EAR no período.")
    else:
        c1, c2, c3 = st.columns(3)
        ena_med = df_ena_f["ena_bruta_regiao_percentualmlt"].mean()
        ena_min = df_ena_f["ena_bruta_regiao_percentualmlt"].min()
        ena_max = df_ena_f["ena_bruta_regiao_percentualmlt"].max()
        with c1: kpi_card("ENA Média (% MLT)", f"{ena_med:.1f}", sufixo="%")
        with c2: kpi_card("ENA Mínima (% MLT)", f"{ena_min:.1f}", sufixo="%")
        with c3: kpi_card("ENA Máxima (% MLT)", f"{ena_max:.1f}", sufixo="%")

        df_ena_ag = df_ena_f.groupby("ena_data")["ena_bruta_regiao_percentualmlt"].mean().reset_index().rename(columns={"ena_data": "data"})
        df_ear_ag = df_ear_f.groupby("ear_data")["ear_verif_subsistema_percentual"].mean().reset_index().rename(columns={"ear_data": "data"})

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_ena_ag["data"], y=df_ena_ag["ena_bruta_regiao_percentualmlt"], name="ENA (% MLT)", line=dict(color="#03A9F4")))
        fig.add_trace(go.Scatter(x=df_ear_ag["data"], y=df_ear_ag["ear_verif_subsistema_percentual"], name="EAR (%)", line=dict(color="#4CAF50")))
        fig.add_hline(y=100, line_dash="dot", line_color="gray", opacity=0.5, annotation_text="MLT (100%)")
        fig.update_layout(title="ENA vs EAR", xaxis_title="Tempo", yaxis_title="%", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        df_corr = pd.merge(df_ena_ag, df_ear_ag, on="data", how="inner")
        if not df_corr.empty:
            fig_scatter = px.scatter(
                df_corr, x="ena_bruta_regiao_percentualmlt", y="ear_verif_subsistema_percentual",
                trendline="ols", opacity=0.5, color_discrete_sequence=["#9C27B0"],
                labels={"ena_bruta_regiao_percentualmlt": "ENA (% MLT)", "ear_verif_subsistema_percentual": "EAR (%)"},
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

# =========================================================
# ABA 8 - COMPARAÇÃO ANUAL
# =========================================================
with abas[7]:
    st.header("Comparação Ano a Ano")
    st.markdown("Compare o mesmo indicador em anos diferentes (ignora o filtro de período, usa o filtro de subsistemas).")

    metrica = st.selectbox(
        "Indicador",
        [
            "Carga (MWmed)",
            "EAR (%)",
            "ENA (% MLT)",
            "CMO (R$/MWh)",
            "Geração Térmica (MWmed)",
        ],
    )

    mapa_metrica = {
        "Carga (MWmed)": (df_carga, "din_instante", "val_cargaenergiamwmed"),
        "EAR (%)": (df_ear, "ear_data", "ear_verif_subsistema_percentual"),
        "ENA (% MLT)": (df_ena, "ena_data", "ena_bruta_regiao_percentualmlt"),
        "CMO (R$/MWh)": (df_cmo, "din_instante", "val_cmomediasemanal"),
        "Geração Térmica (MWmed)": (df_balanco, "din_instante", "val_gertermica"),
    }
    df_m, col_data, col_valor = mapa_metrica[metrica]
    df_m = df_m[df_m["nom_subsistema"].isin(subsistema_selecionado)]

    if df_m.empty:
        st.warning("Sem dados para a métrica selecionada.")
    else:
        df_m = df_m.copy()
        df_m["ano"] = df_m[col_data].dt.year
        df_m["dia_do_ano"] = df_m[col_data].dt.dayofyear
        df_plot = df_m.groupby(["ano", "dia_do_ano"])[col_valor].mean().reset_index()

        fig_anos = px.line(
            df_plot, x="dia_do_ano", y=col_valor, color="ano",
            labels={"dia_do_ano": "Dia do ano", col_valor: metrica, "ano": "Ano"},
        )
        fig_anos.update_layout(hovermode="x unified")
        st.plotly_chart(fig_anos, use_container_width=True)

        # Tabela resumo por ano
        resumo = df_m.groupby("ano")[col_valor].agg(["mean", "min", "max"]).round(2).reset_index()
        resumo.columns = ["Ano", "Média", "Mínimo", "Máximo"]
        st.subheader("Resumo Estatístico por Ano")
        st.dataframe(resumo, use_container_width=True)
