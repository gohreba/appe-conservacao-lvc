"""Orquestração sem Streamlit para dados, memória, comparações e exportação.

A interface web utiliza este adaptador; os cálculos permanecem em
motor_lvc_sie.core, o mesmo motor validado na versão 0.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO, BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
from collections import Counter
from dataclasses import asdict
import csv
import json
import math

from motor_lvc_sie.core import (
    CAMPOS, Premissas, RegistroLVC, ValidacaoError,
    aplicar_regras, consolidar, calcular, selecionar,
    carregar_regras, comparar_memorial, comparar_referencia, resumo,
)
from motor_lvc_sie.io import (
    ler_planilha, carregar_lvc_planilha, carregar_lvc_csv,
    carregar_regras_planilha,
)

ROOT = Path(__file__).resolve().parent
DADOS = ROOT / "motor_lvc_sie" / "dados"
EXTENSOES = {".xls", ".xlsx", ".csv"}
LIMITE_BYTES = 25 * 1024 * 1024
MODELO_LVC = "rodovia;referencia;extensao_km;nota\nSC-999;TRECHO 01;1,000;Bom(8)\nSC-999;TRECHO 01;0,500;Regular(6)\n"
LABELS = {
    "fresagem_descontinua": "Fresagem descontínua",
    "fresagem_continua": "Fresagem contínua",
    "remendo_profundo": "Remendo profundo",
    "reciclagem": "Reciclagem",
    "microrrevestimento": "Microrrevestimento",
    "reforco": "Reforço",
    "correcao_defeitos": "Correção de defeitos",
    "microap": "MicroAP",
    "selagem_trincas": "Selagem de trincas",
}
PREMISSAS_META = [
    ("largura_m", "Largura da pista", "m", "Geometria"),
    ("espessura_reciclagem_m", "Reciclagem", "m", "Espessuras"),
    ("espessura_fresagem_m", "Fresagem", "m", "Espessuras"),
    ("espessura_recomposicao_m", "Recomposição", "m", "Espessuras"),
    ("espessura_correcao_m", "Correção de defeitos", "m", "Espessuras"),
    ("espessura_remocao_granular_m", "Remoção granular", "m", "Espessuras"),
    ("espessura_remocao_revestimento_m", "Remoção do revestimento", "m", "Espessuras"),
    ("espessura_macadame_m", "Macadame seco", "m", "Espessuras"),
    ("espessura_bgs_m", "Brita graduada (BGS)", "m", "Espessuras"),
    ("espessura_cauq_remendo_m", "CAUQ — remendo", "m", "Espessuras"),
    ("espessura_cauq_reciclagem_m", "CAUQ — reciclagem", "m", "Espessuras"),
    ("densidade_cauq_t_m3", "Densidade do CAUQ", "t/m³", "Materiais"),
    ("coef_selagem_por_m2", "Coeficiente de sela-trinca", "a confirmar", "Materiais"),
]


@dataclass
class Fonte:
    nome: str
    registros: list[RegistroLVC]
    regras: dict[str, dict[str, float]]
    memorial: object | None
    origem_regras: str


def carregar_fonte(nome: str, conteudo: bytes) -> Fonte:
    """Aceita bytes de uploads: apenas valores salvos; nunca executa macros ou fórmulas."""
    ext = Path(nome).suffix.lower()
    if ext not in EXTENSOES:
        raise ValidacaoError("Formato incompatível. Envie um arquivo .xls, .xlsx ou .csv.")
    if not conteudo or len(conteudo) > LIMITE_BYTES:
        raise ValidacaoError("Arquivo vazio ou maior que 25 MB.")
    with TemporaryDirectory(prefix="appe_lvc_") as pasta:
        p = Path(pasta) / ("arquivo" + ext)
        p.write_bytes(conteudo)
        if ext == ".csv":
            reg = carregar_lvc_csv(p)
            regras = carregar_regras(DADOS / "regras_lvc_2026.json")
            mem = None
            origem = "Tabela de critérios CRVAL R02 disponibilizada no aplicativo"
        else:
            sheets = ler_planilha(p)
            reg = carregar_lvc_planilha(sheets)
            regras = carregar_regras_planilha(sheets)
            mem = sheets.get("Memorial Pavimentação")
            origem = "Tabela Q4:Z10 da aba LVC - dados 2026 do arquivo enviado"
    if not reg:
        raise ValidacaoError("O arquivo não contém registros LVC válidos.")
    return Fonte(nome, reg, regras, mem, origem)


def rodovias_e_trechos(registros: list[RegistroLVC]) -> dict[str, list[str]]:
    por_rodovia: dict[str, set[str]] = {}
    for r in registros:
        por_rodovia.setdefault(r.rodovia, set()).add(r.referencia)
    return {k: sorted(v, key=str.casefold) for k, v in sorted(por_rodovia.items(), key=lambda kv: kv[0].casefold())}


def validar_regras(regras: dict[str, dict[str, float]]) -> None:
    if not regras:
        raise ValidacaoError("A tabela de critérios não pode ficar vazia.")
    for nota, campos in regras.items():
        for cod in CAMPOS:
            valor = campos.get(cod)
            if valor is None or not isinstance(valor, (float, int)) or not math.isfinite(valor) or not 0 <= valor <= 1:
                raise ValidacaoError(f"Regra inválida na nota {nota}, tratamento {cod}. Informe percentuais entre 0 e 100.")


def regra_editada(linhas: list[dict], regras_base: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Converte percentual visual (0-100) para fração de cálculo (0-1)."""
    novas = {}
    for row in linhas:
        nota = str(row.get("Nota", "")).strip()
        if nota not in regras_base or nota in novas:
            raise ValidacaoError("Notas alteradas, duplicadas ou não reconhecidas na tabela de critérios.")
        novas[nota] = {}
        for cod, label in LABELS.items():
            raw = row.get(label)
            if isinstance(raw, bool) or not isinstance(raw, (float, int)):
                raise ValidacaoError(f"Percentual não numérico: {nota} / {label}")
            val = float(raw)
            if not math.isfinite(val) or not 0 <= val <= 100:
                raise ValidacaoError(f"Percentual fora do intervalo 0-100: {nota} / {label}")
            novas[nota][cod] = val / 100
    if set(novas) != set(regras_base):
        raise ValidacaoError("A tabela deve conter todas as notas originais.")
    validar_regras(novas)
    return novas


def calcular_trecho(fonte: Fonte, rodovia: str, trecho: str, *, modo: str,
                    premissas: Premissas, regras: dict[str, dict[str, float]]):
    validar_regras(regras)
    regs = selecionar(fonte.registros, rodovia, trecho)
    pares, divergencias = aplicar_regras(regs, regras)
    cons = consolidar(pares, modo)
    items = calcular(cons, premissas)
    atualizou_regras = regras != fonte.regras
    original = Premissas(**json.loads((DADOS / "premissas_crval.json").read_text(encoding="utf-8")))
    comparacao = None
    mensagem_comparacao = ""
    # Não tratar divergências de cenários como erros da implementação.
    if modo == "original" and premissas == original and not atualizou_regras:
        if fonte.memorial is not None:
            try:
                comparacao = comparar_memorial(fonte.memorial, trecho, rodovia, items)
            except (ValidacaoError, KeyError) as e:
                mensagem_comparacao = f"Comparação com o memorial não disponível: {e}"
        elif (rodovia == "SC-108" and trecho == "SÃO JOÃO BATISTA - MAJOR GERCINO (ENTR. SC-408)"
              and len(regs) == 26 and math.isclose(cons.extensao_km, 25.478, abs_tol=1e-7)):
            comparacao = comparar_referencia(items, DADOS / "referencia_memorial_sc108.json")
    else:
        mensagem_comparacao = "Comparação numérica de referência desativada: houve alteração de critério, premissa ou método de média."
    avisos = []
    if divergencias:
        avisos.append(f"{len(divergencias)} divergências entre percentuais salvos no LVC e critérios atualmente utilizados.")
    if atualizou_regras:
        avisos.append("Critérios de intervenção editados nesta sessão. Exigem validação técnica.")
    if mensagem_comparacao:
        avisos.append(mensagem_comparacao)
    rel = resumo(cons, items, premissas, avisos=avisos, validacao=comparacao)
    rel["aplicacao"] = "APPE — Conservação Rodoviária × LVC / Streamlit v0.2"
    rel["arquivo_origem"] = fonte.nome
    rel["origem_regras"] = fonte.origem_regras
    rel["regras_utilizadas"] = regras
    rel["divergencias_origem"] = divergencias
    return {"registros": regs, "pares": pares, "consolidado": cons,
            "itens": items, "relatorio": rel, "comparacao": comparacao,
            "divergencias": divergencias}


def linhas_lvc(pares: list[tuple[RegistroLVC, dict]]) -> list[dict]:
    linhas = []
    for r, regra in pares:
        linhas.append({"Linha": r.linha_origem, "Rodovia": r.rodovia,
                       "Trecho": r.referencia, "Extensão (km)": r.extensao_km,
                       "Nota": r.nota,
                       **{LABELS[c]: round(100 * regra[c], 6) for c in CAMPOS}})
    return linhas


def linhas_regras(regras: dict[str, dict[str, float]]) -> list[dict]:
    return [{"Nota": nota, **{LABELS[k]: round(v * 100, 6) for k, v in campos.items()}}
            for nota, campos in regras.items()]


def linhas_quantitativos(items: dict, unidade: str = "Todas") -> list[dict]:
    out = []
    for item in items.values():
        if unidade != "Todas" and item.unidade != unidade:
            continue
        is_pct = item.unidade == "fração"
        out.append({"Serviço": item.descricao, "Quantidade": item.valor * 100 if is_pct else item.valor,
                    "Unidade": "%" if is_pct else item.unidade,
                    "Coluna original": item.coluna_excel, "Equação": item.equacao,
                    "Código": item.codigo})
    return out


def _csv(rows: list[dict], headers: list[str]) -> bytes:
    text = StringIO(newline="")
    w = csv.DictWriter(text, fieldnames=headers, delimiter=";", extrasaction="ignore")
    w.writeheader()
    for row in rows:
        clean = {k: (str(v).replace(".", ",") if isinstance(v, float) else v) for k, v in row.items()}
        w.writerow(clean)
    return ("\ufeff" + text.getvalue()).encode("utf-8")


def arquivos_resultado(calculado: dict) -> dict[str, bytes]:
    c = calculado["consolidado"]
    arquivo_base = f"{c.rodovia.replace('-', '_')}_LVC"
    rel = calculado["relatorio"]
    quant = linhas_quantitativos(calculado["itens"])
    pcts = [{"Tratamento": LABELS[k], "Percentual (%)": round(v * 100, 8)} for k, v in c.percentuais.items()]
    arquivos = {
        "memoria_calculo.json": json.dumps(rel, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"),
        "quantitativos.csv": _csv(quant, ["Serviço", "Quantidade", "Unidade", "Coluna original", "Equação", "Código"]),
        "percentuais_consolidados.csv": _csv(pcts, ["Tratamento", "Percentual (%)"]),
        "registros_lvc.csv": _csv(linhas_lvc(calculado["pares"]), ["Linha", "Rodovia", "Trecho", "Extensão (km)", "Nota", *LABELS.values()]),
        "premissas.json": json.dumps(rel["premissas"], ensure_ascii=False, indent=2).encode("utf-8"),
        "regras_utilizadas.json": json.dumps(rel["regras_utilizadas"], ensure_ascii=False, indent=2).encode("utf-8"),
    }
    if calculado["comparacao"]:
        arquivos["comparacao_memorial.csv"] = _csv(
            calculado["comparacao"]["itens"], ["codigo", "coluna_excel", "calculado", "excel", "diferenca", "status"])
    readme = (
        f"APPE — Conservação Rodoviária x LVC (v0.2)\n"
        f"Rodovia: {c.rodovia}\nTrecho: {c.referencia}\n"
        f"Extensão LVC: {c.extensao_km:.6f} km\nModo: {c.modo}\n"
        "Aviso: reprodução numérica da planilha, sujeita à homologação de engenharia.\n"
        "Intervenções podem se sobrepor, não representam áreas mutuamente exclusivas.\n"
        "Não se deve comparar cenário com premissas alteradas como erro de cálculo.\n"
    )
    arquivos["LEIA_ME.txt"] = readme.encode("utf-8")
    return arquivos


def zip_resultados(arquivos: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return buf.getvalue()


def notas_ordenadas(registros: list[RegistroLVC]):
    ordem = ["Ótimo(10)", "Bom(8)", "Regular(6)", "Regular(5)", "Ruim(4)", "Ruim(3)", "Péssimo(2)"]
    cont = Counter(r.nota for r in registros)
    return [{"Nota": n, "Registros": cont[n]} for n in ordem if n in cont] + [
        {"Nota": n, "Registros": v} for n, v in sorted(cont.items()) if n not in ordem
    ]
