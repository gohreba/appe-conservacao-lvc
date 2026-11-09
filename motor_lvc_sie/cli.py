"""Uso: python -m motor_lvc_sie --ajuda / --arquivo origem.xls."""
from __future__ import annotations
from argparse import ArgumentParser
from pathlib import Path
from dataclasses import asdict
import json
from .core import (Premissas,carregar_regras,aplicar_regras,consolidar,calcular,resumo,
                   selecionar,exportar,comparar_memorial,comparar_referencia,ValidacaoError)
from .io import (ler_planilha,carregar_lvc_planilha,carregar_regras_planilha,carregar_lvc_csv)

ROOT=Path(__file__).resolve().parent
RODOVIA_PADRAO='SC-108'
TRECHO_PADRAO='SÃO JOÃO BATISTA - MAJOR GERCINO (ENTR. SC-408)'

def run(argv=None):
    parser=ArgumentParser(description='Motor LVC -> quantitativos CRVAL / piloto SC-108')
    parser.add_argument('--arquivo',type=Path,default=ROOT/'dados'/'lvc_sc108_piloto.csv',help='CSV padronizado, XLS ou XLSX')
    parser.add_argument('--regras',type=Path,default=None,help='JSON de regras de notas (por padrão, utiliza Q4:Z10 no Excel ou dados/regras_lvc_2026.json no CSV)')
    parser.add_argument('--premissas',type=Path,default=ROOT/'dados'/'premissas_crval.json',help='Parâmetros de cálculo JSON')
    parser.add_argument('--rodovia',default=RODOVIA_PADRAO)
    parser.add_argument('--trecho',default=TRECHO_PADRAO)
    parser.add_argument('--modo',choices=['original','ponderado'],default='original')
    parser.add_argument('--saida',type=Path,default=Path('saidas_sc108'))
    parser.add_argument('--tolerancia',type=float,default=1e-5)
    parser.add_argument('--referencia',type=Path,default=None,help='JSON opcional para comparação com memória de referência')
    parser.add_argument('--sem-comparacao',action='store_true',help='Não comparar com a aba Memorial Pavimentação')
    args=parser.parse_args(argv)

    is_csv=args.arquivo.suffix.lower()=='.csv'
    sheets=None
    if is_csv:
        registros=carregar_lvc_csv(args.arquivo)
    else:
        sheets=ler_planilha(args.arquivo)
        registros=carregar_lvc_planilha(sheets)
    if args.regras:
        regras=carregar_regras(args.regras)
    elif sheets is not None:
        regras=carregar_regras_planilha(sheets)
    else:
        regras=carregar_regras(ROOT/'dados'/'regras_lvc_2026.json')
    premissas=Premissas(**json.loads(args.premissas.read_text(encoding='utf-8')))
    selecionados=selecionar(registros,args.rodovia,args.trecho)
    pares,divergencias=aplicar_regras(selecionados,regras)
    c=consolidar(pares,args.modo);items=calcular(c,premissas)
    validacao=None
    if not args.sem_comparacao and args.modo=='original':
        if sheets is not None:
            validacao=comparar_memorial(sheets['Memorial Pavimentação'],args.trecho,args.rodovia,items,args.tolerancia)
        elif args.referencia:
            validacao=comparar_referencia(items,args.referencia,args.tolerancia)
        elif args.arquivo.resolve()==(ROOT/'dados'/'lvc_sc108_piloto.csv').resolve():
            validacao=comparar_referencia(items,ROOT/'dados'/'referencia_memorial_sc108.json',args.tolerancia)
    result=resumo(c,items,premissas,avisos=[f'{len(divergencias)} divergências de percentuais no LVC de origem (verificar regras)' if divergencias else 'Percentuais da fonte compatíveis com a tabela de critérios do LVC.'],validacao=validacao)
    out=exportar(result,args.saida)
    print(f'Rodovia: {c.rodovia} | Trecho: {c.referencia}')
    print(f'LVC: {c.quantidade_registros} registros | Extensão {c.extensao_km:.3f} km | Modo: {args.modo}')
    print('Quantidades selecionadas:')
    for k in ['reciclagem_m3','fresagem_descontinua_m3','fresagem_continua_m3',
              'microrrevestimento_m2','remocao_granular_m3','macadame_m3','bgs_m3']:
        q=items[k];print(f'  {q.descricao:<45} {q.valor:>12,.2f} {q.unidade}')
    if validacao:
        print(f'Comparação com memorial Excel: {validacao["quantidade_ok"]}/{validacao["quantidade_comparada"]} OK; divergentes: {validacao["quantidade_divergente"]}')
    print(f'Arquivos gerados em: {out.resolve()}')
    if divergencias:print('ATENÇÃO: divergências detectadas entre notas e percentuais salvos no LVC')
    if validacao and validacao['quantidade_divergente']:
        raise SystemExit('ATENÇÃO: resultados divergentes do memorial; confira comparacao_excel.csv')
    return result

if __name__=='__main__':run()
