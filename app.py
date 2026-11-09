"""Interface Streamlit v0.2 para o motor de quantitativos de conservação da APPE.

Execute: python -m streamlit run app.py
Os cálculos e validações são importados do pacote motor_lvc_sie.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from html import escape
import json
from pathlib import Path

import streamlit as st

from motor_lvc_sie.core import Premissas, ValidacaoError, CAMPOS
from interface_backend import (
    DADOS, LABELS, PREMISSAS_META, MODELO_LVC,
    carregar_fonte, rodovias_e_trechos, regra_editada, linhas_regras,
    calcular_trecho, linhas_lvc, linhas_quantitativos, notas_ordenadas,
    arquivos_resultado, zip_resultados,
)

st.set_page_config(
    page_title="APPE | Conservação Rodoviária × LVC",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container {padding-top: 1.8rem; padding-bottom: 3rem; max-width: 1540px;}
  [data-testid="stSidebar"] {background: #edf3f7; border-right: 1px solid #d5e2ea;}
  .appe-eyebrow {font-size:.77rem; font-weight:700; color:#007c91; letter-spacing:.12em; text-transform:uppercase;}
  .appe-title {font-size:2.2rem; font-weight:800; line-height:1.15; color:#153950; margin:.2rem 0 .45rem;}
  .appe-subtitle {color:#536b80; font-size:.95rem; margin-bottom:1.2rem;}
  .appe-ribbon {padding:.76rem 1rem; border:1px solid #ccdee8; border-left:4px solid #008c9a; border-radius:.6rem; background:#fff; margin-bottom:1.1rem;}
  .appe-ribbon b {color:#173950;}
  .appe-chips {display:flex; gap:.48rem; flex-wrap:wrap; margin:.65rem 0 1.1rem;}
  .appe-chip {font-size:.75rem; color:#1b526d; background:#e2f0f4; border:1px solid #c1e0e5; border-radius:99px; padding:.25rem .65rem;}
  div[data-testid="stMetric"] {border:1px solid #dce6ef; background:white; border-radius:14px; padding:13px 18px; min-height:116px;}
  div[data-testid="stMetricLabel"] {font-weight:600; color:#4c6577;}
  div[data-testid="stMetricValue"] {color:#153a55;}
  div[data-testid="stAlert"] {border-radius:10px;}
  div[data-testid="stDownloadButton"] button {font-weight:650; border-radius:8px;}
  .appe-small {color:#597184; font-size:.78rem;}
  .appe-note {padding:.7rem .9rem; background:#eef7f7; border-radius:.6rem; color:#35616b; font-size:.83rem;}
  @media(max-width:850px){.appe-title{font-size:1.65rem;}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False, max_entries=5)
def _cache_fonte(nome: str, conteudo: bytes):
    return carregar_fonte(nome, conteudo)


@st.cache_data(show_spinner=False)
def _padroes():
    return json.loads((DADOS / "premissas_crval.json").read_text(encoding="utf-8"))


def _br(valor: float, casas: int = 2) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _resetar_parametros():
    for chave in list(st.session_state.keys()):
        if chave.startswith("prem_") or chave.startswith("regras_editor_"):
            del st.session_state[chave]
    st.session_state["editar_regras"] = False


st.markdown('<div class="appe-eyebrow">APPE · Engenharia de Transportes · Protótipo v0.2</div>', unsafe_allow_html=True)
st.markdown('<div class="appe-title">Conservação rodoviária × LVC</div>', unsafe_allow_html=True)
st.markdown('<div class="appe-subtitle">Do levantamento visual contínuo à memória de quantitativos — em um único ambiente de cálculo.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🛣️ APPE | LVC")
    st.caption("Base de dados e definição do segmento")
    origem = st.radio(
        "Fonte de dados",
        ["Base CRVAL (65 trechos)", "Piloto SC-108 (26 registros)", "Enviar planilha ou CSV"],
        key="origem_dados",
    )
    if origem == "Base CRVAL (65 trechos)":
        nome = "lvc_base_crval_65_trechos.csv"
        conteudo = (DADOS / nome).read_bytes()
        st.caption("Base de demonstração extraída do LVC fornecido pela APPE: 697 registros.")
    elif origem == "Piloto SC-108 (26 registros)":
        nome = "lvc_sc108_piloto.csv"
        conteudo = (DADOS / nome).read_bytes()
        st.caption("Conjunto de validação: SC-108 / São João Batista – Major Gercino.")
    else:
        enviado = st.file_uploader(
            "Carregar LVC (XLS, XLSX ou CSV)",
            type=["xls", "xlsx", "csv"],
            help="Arquivos de Excel no layout CRVAL: aba 'LVC - dados 2026'; CSV com rodovia, referencia, extensao_km e nota. Limite: 25 MB.",
        )
        if enviado is None:
            st.info("Selecione um arquivo acima. Você também pode experimentar a base CRVAL incluída.")
            st.download_button("↓ Modelo CSV de LVC", data=("\ufeff" + MODELO_LVC).encode("utf-8"),
                               file_name="modelo_importacao_lvc.csv", mime="text/csv", use_container_width=True)
            st.stop()
        nome, conteudo = enviado.name, enviado.getvalue()

    try:
        fonte = _cache_fonte(nome, conteudo)
        estrutura = rodovias_e_trechos(fonte.registros)
    except (Exception,) as erro:
        st.error(f"Não foi possível ler o LVC: {erro}")
        st.caption("Confirme o layout e os campos esperados. Para importar arquivos Excel, utilize a aba 'LVC - dados 2026'.")
        st.stop()

    chave_fonte = sha256(conteudo).hexdigest()[:12]
    rodovias = list(estrutura)
    indice_rodovia = rodovias.index("SC-108") if "SC-108" in rodovias else 0
    rodovia = st.selectbox("Rodovia / acesso", rodovias, index=indice_rodovia,
                           key=f"rodovia_{chave_fonte}")
    trechos = estrutura[rodovia]
    trecho_padrao = "SÃO JOÃO BATISTA - MAJOR GERCINO (ENTR. SC-408)"
    indice_trecho = trechos.index(trecho_padrao) if trecho_padrao in trechos else 0
    trecho = st.selectbox("Trecho", trechos, index=indice_trecho,
                          key=f"trecho_{chave_fonte}_{rodovia}")

    st.divider()
    st.markdown("#### Método de consolidação")
    escolha = st.radio("Média dos percentuais", ["Original (média simples)", "Ponderada pela extensão"],
                        key="modo_media")
    modo = "original" if escolha.startswith("Original") else "ponderado"
    if modo == "ponderado":
        st.warning("Método alternativo: pode modificar os quantitativos da planilha original.")
    st.divider()
    st.caption(f"{len(fonte.registros)} registros • {len(estrutura)} rodovias/acessos • {sum(map(len,estrutura.values()))} trechos")
    st.download_button(
        "↓ Modelo de importação CSV",
        data=("\ufeff" + MODELO_LVC).encode("utf-8"),
        file_name="modelo_importacao_lvc.csv", mime="text/csv", use_container_width=True,
    )

st.markdown(
    f'<div class="appe-ribbon"><b>{escape(rodovia)}</b> &nbsp;·&nbsp; {escape(trecho)}'
    f'<div class="appe-small">Origem: {escape(nome)} &nbsp; | &nbsp; Critérios: {escape(fonte.origem_regras)}</div>'
    f'</div>',
    unsafe_allow_html=True,
)

tab_visao, tab_lvc, tab_param, tab_quant, tab_export = st.tabs([
    "Visão geral", "LVC e percentuais", "Premissas e critérios", "Quantitativos", "Memória e exportação",
])

# Entradas avançadas são coletadas antes do processamento; a UI é reativa a toda alteração.
with tab_param:
    st.subheader("Premissas técnicas")
    st.caption("As alterações recalculam todos os quantitativos automaticamente. Os padrões reproduzem a versão CRVAL R02.")
    if st.button("↺ Restaurar premissas e critérios", key="restaurar_padrao"):
        _resetar_parametros()
        st.rerun()
    valores = {}
    defaults = _padroes()
    for grupo in ["Geometria", "Espessuras", "Materiais"]:
        st.markdown(f"**{grupo}**")
        campos = [m for m in PREMISSAS_META if m[3] == grupo]
        cols = st.columns(3)
        for j, (key, label, unidade, _) in enumerate(campos):
            with cols[j % 3]:
                valores[key] = st.number_input(
                    f"{label} ({unidade})", min_value=0.000001,
                    value=float(defaults[key]), step=0.005,
                    format="%.4f" if key != "coef_selagem_por_m2" else "%.5f",
                    key=f"prem_{key}",
                    help="Valor utilizado nos cálculos; deve ser validado tecnicamente para aplicação oficial.",
                )
    st.divider()
    st.subheader("Regras de intervenção por nota")
    st.caption("Os percentuais representam tratamentos que podem se sobrepor. Não devem ser somados como áreas exclusivas.")
    edicao = st.checkbox("Habilitar edição das regras (%)", key="editar_regras")
    linhas_base = linhas_regras(fonte.regras)
    if edicao:
        st.warning("Cenário de critérios alterados: requer validação do responsável técnico; a comparação original será desativada.")
        editor = st.data_editor(
            linhas_base,
            key=f"regras_editor_{chave_fonte}",
            num_rows="fixed", hide_index=True, width="stretch",
            disabled=["Nota"],
            column_config={
                name: st.column_config.NumberColumn(name, min_value=0., max_value=100.,
                                                    step=1., format="%.2f")
                for name in LABELS.values()
            },
        )
        linhas_edit = editor.to_dict(orient="records") if hasattr(editor, "to_dict") else editor
        try:
            regras = regra_editada(linhas_edit, fonte.regras)
        except (ValueError, TypeError, ValidacaoError) as erro:
            st.error(f"Corrija os critérios: {erro}")
            st.stop()
    else:
        st.dataframe(linhas_base, width="stretch", hide_index=True)
        regras = fonte.regras
    st.info("Para comparar diretamente com o Memorial Pavimentação, use média original, premissas padrão e critérios não alterados.")

try:
    premissas = Premissas(**valores)
    resultado = calcular_trecho(fonte, rodovia, trecho, modo=modo, premissas=premissas, regras=regras)
except (ValidacaoError, ValueError, KeyError) as erro:
    st.error(f"Erro no processamento: {erro}")
    st.stop()

con = resultado["consolidado"]
itens = resultado["itens"]
relatorio = resultado["relatorio"]
comparacao = resultado["comparacao"]

with tab_visao:
    st.markdown("#### Indicadores do segmento")
    a,b,c,d = st.columns(4)
    a.metric("Extensão avaliada", f"{_br(con.extensao_km,3)} km")
    b.metric("Registros do LVC", f"{con.quantidade_registros}")
    c.metric("Área da pista", f"{_br(relatorio['area_pista_m2'],0)} m²")
    d.metric("Tratamentos monitorados", f"{len(CAMPOS)}")
    st.markdown('<div class="appe-chips"><span class="appe-chip">Cálculo atualizado automaticamente</span>'
                '<span class="appe-chip">Modelo reproduzido do CRVAL R02</span>'
                '<span class="appe-chip">Análise técnica preliminar</span></div>', unsafe_allow_html=True)
    st.markdown("#### Serviços em destaque")
    e,f,g,h = st.columns(4)
    e.metric("Reciclagem", f"{_br(itens['reciclagem_m3'].valor)} m³")
    f.metric("Fresagem descontínua", f"{_br(itens['fresagem_descontinua_m3'].valor)} m³")
    g.metric("Fresagem contínua", f"{_br(itens['fresagem_continua_m3'].valor)} m³")
    h.metric("Microrrevestimento", f"{_br(itens['microrrevestimento_m2'].valor)} m²")
    st.divider()
    col_esq,col_dir = st.columns([1, 1.4], gap="large")
    with col_esq:
        st.markdown("#### Distribuição das notas LVC")
        freq = notas_ordenadas(resultado["registros"])
        st.bar_chart(freq, x="Nota", y="Registros", height=280, color="#2485aa")
        st.caption("Contagem de registros, não percentual de extensão por condição.")
    with col_dir:
        st.markdown("#### Percentuais consolidados de intervenção")
        percentuais = sorted(
            [{"Tratamento": LABELS[k], "Percentual (%)": 100*v} for k,v in con.percentuais.items()],
            key=lambda row: -row["Percentual (%)"],
        )
        st.bar_chart(percentuais, x="Tratamento", y="Percentual (%)", height=280, color="#0a8b83")
        st.caption("Os percentuais não são exclusivos entre si; cada serviço segue sua própria regra.")
    if resultado["divergencias"]:
        st.warning(f"Foram encontradas {len(resultado['divergencias'])} diferenças entre percentuais armazenados no LVC e regras em uso. Confira na aba 'LVC e percentuais'.")
    if comparacao:
        if comparacao["quantidade_divergente"] == 0 and comparacao["quantidade_ok"] == comparacao["quantidade_comparada"]:
            st.success(f"Conferência numérica: {comparacao['quantidade_ok']}/{comparacao['quantidade_comparada']} campos coincidentes com o memorial de referência.")
        else:
            st.warning(f"Conferência: {comparacao['quantidade_ok']} OK; {comparacao['quantidade_divergente']} divergentes. Consulte a aba Memória.")

with tab_lvc:
    st.subheader("Registros do LVC")
    st.caption(f"{con.quantidade_registros} observações do trecho selecionado; extensão total de {_br(con.extensao_km,3)} km.")
    st.dataframe(linhas_lvc(resultado["pares"]), hide_index=True, width="stretch", height=330)
    st.divider()
    st.markdown("#### Consolidação das intervenções")
    percentuais_linhas = [
        {"Tratamento": LABELS[k], "Percentual (%)": round(100 * v, 4)}
        for k, v in con.percentuais.items()
    ]
    st.dataframe(percentuais_linhas, hide_index=True, width="stretch")
    with st.expander("Entenda a média simples e a ponderada"):
        st.markdown(
            "**Original:** cada registro recebe o mesmo peso, independentemente de sua extensão.  "
            "**Ponderada:** cada registro recebe peso proporcional à extensão em quilômetros. "
            "A alternativa ponderada é uma análise de sensibilidade e não substitui automaticamente o critério adotado pela APPE."
        )
    if resultado["divergencias"]:
        with st.expander(f"Divergências nos percentuais de origem ({len(resultado['divergencias'])})", expanded=False):
            st.dataframe(resultado["divergencias"], hide_index=True, width="stretch")

with tab_quant:
    st.subheader("Memória de quantitativos")
    st.caption("30 resultados associados às colunas F:AI do Memorial Pavimentação; equações e referências preservadas.")
    filtro = st.selectbox("Filtrar por unidade", ["Todas", "m³", "m²", "m²*", "t", "fração", "unidade a confirmar"],
                          key="filtro_unidades")
    tabela = linhas_quantitativos(itens, filtro)
    st.dataframe(tabela, hide_index=True, width="stretch", height=570,
                 column_config={
                     "Quantidade": st.column_config.NumberColumn("Quantidade", format="%.4f"),
                     "Equação": st.column_config.TextColumn("Equação", width="large"),
                 })
    st.caption("Os itens em fração são exibidos em percentual (%). Campos com unidade a confirmar permanecem explicitamente sinalizados.")
    st.markdown("#### Como são calculados?")
    st.code("Área (m²) = Extensão (km) × 1.000 × Largura (m)\n"
            "Volume (m³) = Área (m²) × Percentual do tratamento × Espessura (m)\n"
            "Massa CAUQ (t) = Volume (m³) × Densidade (t/m³)", language="text")
    st.warning("A soma das áreas de tratamentos diferentes não equivale à área total de pista, pois as intervenções podem ocorrer sobre as mesmas superfícies.")

with tab_export:
    st.subheader("Documentação e exportação")
    st.caption("Baixe os resultados calculados sem utilizar o terminal. A memória inclui premissas, critérios, fórmulas e avisos técnicos.")
    arquivos = arquivos_resultado(resultado)
    pacote = zip_resultados(arquivos)
    a,b,c = st.columns(3)
    with a:
        st.download_button("↓ Quantitativos CSV", data=arquivos["quantitativos.csv"],
                           file_name=f"quantitativos_{rodovia.replace('-', '_')}.csv", mime="text/csv", width="stretch")
    with b:
        st.download_button("↓ Memória JSON", data=arquivos["memoria_calculo.json"],
                           file_name=f"memoria_{rodovia.replace('-', '_')}.json", mime="application/json", width="stretch")
    with c:
        st.download_button("↓ Pacote completo ZIP", data=pacote,
                           file_name=f"APPE_LVC_{rodovia.replace('-', '_')}_resultados.zip",
                           mime="application/zip", width="stretch", type="primary")
    st.markdown("#### Arquivos incluídos no ZIP")
    st.dataframe([{"Arquivo": x, "Tamanho (KB)": round(len(content)/1024, 2)} for x,content in arquivos.items()],
                 hide_index=True, width="stretch")
    st.divider()
    st.markdown("#### Comparação com os valores da planilha de referência")
    if comparacao:
        col1,col2,col3 = st.columns(3)
        col1.metric("Campos comparados", comparacao["quantidade_comparada"])
        col2.metric("Conformes", comparacao["quantidade_ok"])
        col3.metric("Divergentes", comparacao["quantidade_divergente"])
        st.dataframe(comparacao["itens"], hide_index=True, width="stretch", height=280)
    else:
        st.info("Sem comparação disponível para a configuração atual. A validação de referência exige modo original e premissas/regras não modificadas, além de um memorial de referência compatível.")
    with st.expander("Advertências e limites técnicos", expanded=False):
        for aviso in relatorio["avisos"]:
            st.markdown(f"- {aviso}")
    st.markdown('<div class="appe-note">O aplicativo calcula quantitativos conforme as regras da planilha CRVAL; não substitui a homologação de critérios, unidades, levantamentos ou projetos por profissional responsável.</div>', unsafe_allow_html=True)

st.caption("APPE • Conservação Rodoviária × LVC • v0.2 • Aplicativo local, sem banco de dados nem persistência de uploads • Cálculos do motor Python v0.1")
