"""Motor de quantitativos LVC -> critérios -> consolidação -> memória.

As hipóteses de cálculo são parametrizadas e reproduzem a memória CRVAL R02
para o trecho piloto. NÃO constitui projeto ou dimensionamento homologado.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from collections import Counter
import csv
import json
import math
from typing import Literal

CAMPOS = (
    'fresagem_descontinua', 'fresagem_continua', 'remendo_profundo',
    'reciclagem', 'microrrevestimento', 'reforco', 'correcao_defeitos',
    'microap', 'selagem_trincas',
)

class ValidacaoError(ValueError):
    """Informação inválida ou inconsistente com as premissas do motor."""

@dataclass(frozen=True)
class RegistroLVC:
    rodovia: str
    referencia: str
    extensao_km: float
    nota: str
    linha_origem: int|None=None
    origem: str=''
    percentuais_fonte: dict[str,float]|None=None

    def __post_init__(self):
        if not self.rodovia or not self.referencia or not self.nota:
            raise ValidacaoError('Rodovia, referência e nota são obrigatórios')
        if not math.isfinite(self.extensao_km) or self.extensao_km<=0:
            raise ValidacaoError(f'Extensão inválida na linha {self.linha_origem}: {self.extensao_km}')

@dataclass(frozen=True)
class Premissas:
    largura_m: float=7.0
    espessura_reciclagem_m: float=.20
    espessura_fresagem_m: float=.05
    espessura_recomposicao_m: float=.05
    espessura_correcao_m: float=.05
    espessura_remocao_granular_m: float=.35
    espessura_remocao_revestimento_m: float=.05
    espessura_macadame_m: float=.20
    espessura_bgs_m: float=.15
    espessura_cauq_remendo_m: float=.05
    espessura_cauq_reciclagem_m: float=.05
    densidade_cauq_t_m3: float=2.40
    coef_selagem_por_m2: float=.004

    def __post_init__(self):
        for campo,v in asdict(self).items():
            if not math.isfinite(v) or v<=0:
                raise ValidacaoError(f'Premissa inválida: {campo}={v}')

@dataclass(frozen=True)
class Consolidado:
    rodovia: str
    referencia: str
    quantidade_registros: int
    extensao_km: float
    notas: dict[str,int]
    modo: str
    percentuais: dict[str,float]
    linhas_origem: list[int]

@dataclass(frozen=True)
class Item:
    codigo: str
    descricao: str
    unidade: str
    valor: float
    equacao: str
    coluna_excel: str

# Valores tal como constam nas linhas 4 a 10, Q:Z, da aba LVC - dados 2026.
# A validação é estrita: notas não cadastradas não são interpoladas.
def carregar_regras(path:str|Path)->dict[str,dict[str,float]]:
    raw=json.loads(Path(path).read_text(encoding='utf-8'))
    regras=raw['regras'] if 'regras' in raw else raw
    out={}
    for nota,d in regras.items():
        if not isinstance(d,dict):raise ValidacaoError(f'Regra {nota} inválida')
        if not set(d).issubset(set(CAMPOS)):
            raise ValidacaoError(f'Campos desconhecidos na regra {nota}: {set(d)-set(CAMPOS)}')
        normal={}
        for k in CAMPOS:
            v=float(d.get(k,0))
            if not math.isfinite(v) or not 0<=v<=1:raise ValidacaoError(f'Percentual inválido em {nota}/{k}')
            normal[k]=v
        out[nota.strip()]=normal
    if not out:raise ValidacaoError('Tabela de regras vazia')
    return out

def aplicar_regras(registros:list[RegistroLVC],regras:dict[str,dict[str,float]], *,conferir_fonte:bool=True,tol:float=1e-7):
    """Retorna pares (registro, regra) e diferenças em percentuais de fonte.

    O percentual deve ser fração de 0 a 1, e cada regra é aplicada POR NOTA.
    Dados históricos já calculados são apenas evidência de validação.
    """
    saida=[];divergencias=[]
    for r in registros:
        if r.nota not in regras:
            raise ValidacaoError(f'Nota não cadastrada na tabela de critérios: {r.nota!r} (linha {r.linha_origem})')
        regra=regras[r.nota]
        if conferir_fonte and r.percentuais_fonte:
            for campo,original in r.percentuais_fonte.items():
                if campo not in CAMPOS:continue
                if not math.isclose(regra[campo],original,rel_tol=0,abs_tol=tol):
                    divergencias.append({'linha':r.linha_origem,'campo':campo,'nota':r.nota,
                                         'fonte':original,'regra':regra[campo]})
        saida.append((r,regra))
    return saida,divergencias

def consolidar(pares:list[tuple[RegistroLVC,dict]], modo:Literal['original','ponderado']='original')->Consolidado:
    """'original' = média aritmética por registro do Excel CRVAL.
    'ponderado' = ponderação por comprimento, alternativa para análise.
    """
    if modo not in ('original','ponderado'):raise ValidacaoError('Modo deve ser original ou ponderado')
    if not pares:raise ValidacaoError('Nenhum registro LVC para consolidar')
    ref={(r.rodovia,r.referencia) for r,_ in pares}
    if len(ref)>1:raise ValidacaoError('Consolidação deve conter uma única rodovia e referência')
    length=sum(r.extensao_km for r,_ in pares)
    pesos=[r.extensao_km/length if modo=='ponderado' else 1/len(pares) for r,_ in pares]
    pc={k:sum(w*regra[k] for (_,regra),w in zip(pares,pesos)) for k in CAMPOS}
    first=pares[0][0]
    return Consolidado(first.rodovia,first.referencia,len(pares),length,
                       dict(sorted(Counter(r.nota for r,_ in pares).items())),modo,pc,
                       [r.linha_origem for r,_ in pares if r.linha_origem is not None])

def calcular(c:Consolidado, p:Premissas=Premissas())->dict[str,Item]:
    """Cálculos derivados da estrutura de colunas F:AI da aba Memorial Pavimentação.

    Cada item preserva coluna Excel, expressão e unidade interpretada.
    Alguns cabeçalhos do arquivo original são inconsistentes com a dimensão
    matemática. Esses itens ficam sinalizados na documentação e na saída.
    """
    a=c.extensao_km*1000*p.largura_m
    s=c.percentuais
    items={}
    def put(cod,desc,unit,val,expr,col):
        if not math.isfinite(val) or val<0:raise ValidacaoError(f'Quantidade inválida: {cod}')
        items[cod]=Item(cod,desc,unit,float(val),expr,col)
    def pct(cod,field,col,label):
        put(cod,label,'fração',s[field],f'Média {c.modo}: {field}',col)
    pct('pct_reciclagem','reciclagem','F','Reciclagem (%)')
    put('reciclagem_m3','Reciclagem de base','m³',a*s['reciclagem']*p.espessura_reciclagem_m,'área × % reciclagem × espessura reciclagem','G')
    put('tss_area_equivalente_m2','Tratamento superficial simples — área equivalente','m²*',a*s['reciclagem'],'área × % reciclagem','H')
    put('pintura_reciclagem_area_equivalente_m2','Pintura de ligação na reciclagem — área equivalente','m²*',a*s['reciclagem'],'área × % reciclagem','I')
    put('cauq_reciclagem_t','CAUQ borracha contínuo na reciclagem','t',a*s['reciclagem']*p.espessura_cauq_reciclagem_m*p.densidade_cauq_t_m3,'área × % reciclagem × esp. CAUQ × densidade','J')
    pct('pct_fresagem_descontinua','fresagem_descontinua','K','Recomposição descontínua (%)')
    pct('pct_fresagem_continua','fresagem_continua','L','Recomposição contínua (%)')
    fd=a*s['fresagem_descontinua']*p.espessura_fresagem_m
    fc=a*s['fresagem_continua']*p.espessura_fresagem_m
    put('fresagem_descontinua_m3','Fresagem descontínua','m³',fd,'área × % fresco descontínuo × esp. fresagem','M')
    put('fresagem_continua_m3','Fresagem contínua','m³',fc,'área × % fresagem contínua × esp. fresagem','N')
    put('pintura_recomposicao_m2','Pintura de ligação da recomposição','m²',a*(s['fresagem_descontinua']+s['fresagem_continua']),'área × (% descontínua + % contínua)','O')
    put('cauq_descontinuo_t','CAUQ borracha descontínuo','t',a*s['fresagem_descontinua']*p.espessura_recomposicao_m*p.densidade_cauq_t_m3,'área × % descontínua × esp. CAUQ × densidade','P')
    put('cauq_continuo_t','CAUQ borracha contínuo','t',a*s['fresagem_continua']*p.espessura_recomposicao_m*p.densidade_cauq_t_m3,'área × % contínua × esp. CAUQ × densidade','Q')
    pct('pct_correcao_defeitos','correcao_defeitos','R','Correção de defeitos (%)')
    vc=a*s['correcao_defeitos']*p.espessura_correcao_m
    put('fresagem_correcao_defeitos_m3','Fresagem por minicarregadeira para correção','m³',vc,'área × % correção × esp. correção','S')
    put('pintura_correcao_defeitos_m2','Pintura de ligação na correção','m²',a*s['correcao_defeitos'],'área × % correção','T')
    put('correcao_defeitos_m3','Correção de defeitos','m³',vc,'área × % correção × esp. correção','U')
    pct('pct_microrrevestimento','microrrevestimento','V','Aplicação de microrrevestimento (%)')
    put('microrrevestimento_m2','Aplicação de microrrevestimento','m²',a*s['microrrevestimento'],'área × % microrrevestimento','W')
    pct('pct_microap','microap','X','Aplicação de MicroAP (%)')
    put('microap_m2','Aplicação de MicroAP','m²',a*s['microap'],'área × % MicroAP','Y')
    pct('pct_remendo_profundo','remendo_profundo','Z','Remendo profundo (%)')
    rp=s['remendo_profundo']
    put('remocao_granular_m3','Remoção de camada granular','m³',a*rp*p.espessura_remocao_granular_m,'área × % remendo × esp. remoção granular','AA')
    put('remocao_revestimento_m3','Remoção mecanizada de revestimento asfáltico','m³',a*rp*p.espessura_remocao_revestimento_m,'área × % remendo × esp. revestimento','AB')
    put('macadame_m3','Macadame seco','m³',a*rp*p.espessura_macadame_m,'área × % remendo × esp. macadame','AC')
    put('bgs_m3','Brita graduada simples (BGS)','m³',a*rp*p.espessura_bgs_m,'área × % remendo × esp. BGS','AD')
    put('imprimacao_m2','Imprimação','m²',a*rp,'área × % remendo','AE')
    put('pintura_remendo_m2','Pintura de ligação do remendo','m²',a*rp,'área × % remendo','AF')
    put('cauq_remendo_t','CAUQ borracha descontínuo do remendo','t',a*rp*p.espessura_cauq_remendo_m*p.densidade_cauq_t_m3,'área × % remendo × esp. CAUQ × densidade','AG')
    pct('pct_selagem_trincas','selagem_trincas','AH','Aplicação de sela-trinca (%)')
    put('selagem_trincas_unid_planilha','Selagem de trincas','unidade a confirmar',a*s['selagem_trincas']*p.coef_selagem_por_m2,'área × % selagem × coeficiente 0,004 (unidade a confirmar)','AI')
    return items

def resumo(c:Consolidado,itens:dict[str,Item],premissas:Premissas,avisos:list|None=None,validacao:dict|None=None)->dict:
    advertencias=[
        'Uso preliminar: critérios e premissas da planilha CRVAL R02 sujeitos a homologação pela engenharia.',
        'Colunas H e I do memorial original exibem m³, mas a equação reproduz área (m²). Conferir unidade contratual.',
        'Unidade e interpretação física do coeficiente 0,004 de selagem de trincas precisam de confirmação.',
        'O método original é média aritmética dos registros; o modo ponderado é alternativo e muda quantitativos.',
        'Reciclagem, fresagem, remendos e correção podem se sobrepor; não somar áreas como se fossem exclusivas.'
    ]
    return {'aplicacao':'Motor LVC x Quantitativos - APPE / piloto SC-108',
            'origem_modelo':'CRVAL Lotes 1 2 e 3 R02 - LVC dados 2026 / Memorial Pavimentação',
            'consolidacao':asdict(c),'premissas':asdict(premissas),
            'area_pista_m2':c.extensao_km*1000*premissas.largura_m,
            'quantitativos':{k:asdict(v) for k,v in itens.items()},
            'avisos':advertencias+(avisos or []),'validacao':validacao}

def comparar_referencia(itens:dict[str,Item], referencia_path:str|Path, tolerancia=1e-5)->dict:
    """Confere os valores piloto registrados do Excel, sem precisar do .xls."""
    ref=json.loads(Path(referencia_path).read_text(encoding='utf-8'))
    vals=ref['quantidades']
    checks=[]
    for code,item in itens.items():
        expected=vals.get(code)
        if not expected:continue
        original=expected['valor_excel']
        if not isinstance(original,(int,float)):
            status='INDETERMINADO';diferenca=None
        else:
            diferenca=item.valor-original
            status='OK' if abs(diferenca)<=tolerancia else 'DIVERGENTE'
        checks.append({'codigo':code,'coluna_excel':item.coluna_excel,'calculado':item.valor,
                       'excel':original,'diferenca':diferenca,'status':status})
    return {'linha_memorial':ref['linha_memorial'],'tolerancia_absoluta':tolerancia,
            'quantidade_comparada':len(checks),'quantidade_ok':sum(c['status']=='OK' for c in checks),
            'quantidade_divergente':sum(c['status']=='DIVERGENTE' for c in checks),
            'itens':checks,'origem':'referência extraída do memorial original'}

def selecionar(registros:list[RegistroLVC],rodovia:str,trecho:str)->list[RegistroLVC]:
    filtrados=[r for r in registros if r.rodovia.strip().casefold()==rodovia.strip().casefold()
               and r.referencia.strip().casefold()==trecho.strip().casefold()]
    if not filtrados:raise ValidacaoError(f'Trecho não encontrado: {rodovia} / {trecho}')
    return filtrados

def exportar(result:dict,saida:str|Path):
    saida=Path(saida);saida.mkdir(exist_ok=True,parents=True)
    (saida/'memoria_calculo.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (saida/'quantitativos.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        w=csv.writer(fh,delimiter=';')
        w.writerow(['codigo','descricao','unidade','valor','coluna_memorial_excel','equacao'])
        for v in result['quantitativos'].values():
            w.writerow([v['codigo'],v['descricao'],v['unidade'],f"{v['valor']:.8f}".replace('.',','),v['coluna_excel'],v['equacao']])
    if result.get('validacao'):
        with (saida/'comparacao_excel.csv').open('w',newline='',encoding='utf-8-sig') as fh:
            w=csv.writer(fh,delimiter=';');w.writerow(['codigo','coluna_excel','calculado','excel','diferenca','status'])
            for v in result['validacao'].get('itens',[]):
                w.writerow([v['codigo'],v['coluna_excel'],v['calculado'],v['excel'],v['diferenca'],v['status']])
    return saida

def comparar_memorial(memorial_sheet,trecho:str,rodovia:str,itens:dict[str,Item],tolerancia=1e-5)->dict:
    encontrados=[r for r,cols in memorial_sheet.nonempty_rows() if str(cols.get(2,'')).strip().casefold()==rodovia.strip().casefold()
                and str(cols.get(3,'')).strip().casefold()==trecho.strip().casefold()]
    if len(encontrados)!=1:
        raise ValidacaoError(f'Referência ao memorial não unívoca: {len(encontrados)} linhas para {rodovia} / {trecho}')
    lin=encontrados[0];checks=[]
    for k,item in itens.items():
        from .io import indice_coluna
        original=memorial_sheet.cell(lin,indice_coluna(item.coluna_excel))
        if not isinstance(original,(float,int)) or not math.isfinite(original):
            checks.append({'codigo':k,'coluna_excel':item.coluna_excel,'calculado':item.valor,'excel':original,'diferenca':None,'status':'INDETERMINADO'})
            continue
        dif=item.valor-original
        checks.append({'codigo':k,'coluna_excel':item.coluna_excel,'calculado':item.valor,'excel':original,'diferenca':dif,
                       'status':'OK' if abs(dif)<=tolerancia else 'DIVERGENTE'})
    return {'linha_memorial':lin,'tolerancia_absoluta':tolerancia,
            'quantidade_comparada':len(checks),'quantidade_ok':sum(c['status']=='OK' for c in checks),
            'quantidade_divergente':sum(c['status']=='DIVERGENTE' for c in checks),
            'itens':checks}
