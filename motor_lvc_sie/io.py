"""Adapters de dados: CSV padronizado, planilha XLS legada e XLSX.

Utiliza somente a biblioteca padrão do Python; arquivos Excel são lidos
como *valores salvos* e nunca têm fórmulas executadas nem links acessados.
"""
from __future__ import annotations
from pathlib import Path
import csv
import math
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from .legacy_xls import Sheet, load_xls, XlsReadError
from .core import RegistroLVC, CAMPOS, ValidacaoError

PERCENT_COLS={k:col for col,k in enumerate(CAMPOS,start=7)}

def indice_coluna(letters:str)->int:
    n=0
    for c in letters.upper():
        if not 'A'<=c<='Z':raise ValueError(f'Coluna inválida: {letters}')
        n=n*26+(ord(c)-64)
    return n

def _numero(v)->float:
    if isinstance(v,(int,float)):
        x=float(v)
    elif v is None or not str(v).strip():
        raise ValidacaoError('Valor numérico ausente')
    else:
        txt=str(v).strip().replace(' ','')
        # CSV padrão Brasil: 1.234,56; se só vírgula, decimal.
        if ',' in txt:txt=txt.replace('.','').replace(',','.')
        x=float(txt)
    if not math.isfinite(x):raise ValidacaoError(f'Número não finito: {v}')
    return x

def ler_xlsx(path:str|Path)->dict[str,Sheet]:
    """Leitor de valores salvos em XLSX (sem avaliar fórmulas)."""
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'p':'http://schemas.openxmlformats.org/package/2006/relationships'}
    out={}
    with ZipFile(path) as z:
        names=set(z.namelist())
        strings=[]
        if 'xl/sharedStrings.xml' in names:
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall('m:si',ns):
                strings.append(''.join(t.text or '' for t in si.findall('.//m:t',ns)))
        book=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        relmap={r.attrib['Id']:r.attrib['Target'] for r in rels}
        for ws in book.findall('m:sheets/m:sheet',ns):
            name=ws.attrib['name'];rid=ws.attrib['{%s}id'%ns['r']]
            target=relmap[rid]
            if target.startswith('/'): target=target.lstrip('/')
            elif not target.startswith('xl/'): target='xl/'+target
            # Collapse xl/worksheets/../worksheets references if present
            from posixpath import normpath
            target=normpath(target)
            x=ET.fromstring(z.read(target))
            cells={}
            for cell in x.findall('.//m:sheetData/m:row/m:c',ns):
                cr=cell.attrib.get('r')
                if not cr:continue
                match=re.fullmatch(r'([A-Z]+)(\d+)',cr)
                if not match:continue
                c=indice_coluna(match.group(1));r=int(match.group(2))
                kind=cell.attrib.get('t','n')
                v=cell.find('m:v',ns)
                if kind=='inlineStr':
                    inline=cell.find('m:is',ns)
                    if inline is not None:cells[r,c]=''.join(t.text or '' for t in inline.findall('.//m:t',ns))
                elif v is not None and v.text is not None:
                    if kind=='s':cells[r,c]=strings[int(v.text)]
                    elif kind in ('str','e'):cells[r,c]=v.text
                    elif kind=='b':cells[r,c]=(v.text=='1')
                    else:
                        try:cells[r,c]=float(v.text)
                        except ValueError:cells[r,c]=v.text
            out[name]=Sheet(name,cells)
    return out

def ler_planilha(path:str|Path)->dict[str,Sheet]:
    p=Path(path)
    if not p.is_file():raise FileNotFoundError(p)
    if p.suffix.lower()=='.xls':return load_xls(p)
    if p.suffix.lower()=='.xlsx':return ler_xlsx(p)
    raise ValidacaoError('Esperado .xls ou .xlsx')

def carregar_lvc_planilha(sheets:dict[str,Sheet], *,aba='LVC - dados 2026')->list[RegistroLVC]:
    if aba not in sheets:raise ValidacaoError(f'Aba ausente: {aba}')
    sh=sheets[aba]
    if str(sh.cell(2,2)).strip()!='Rodovia' or str(sh.cell(2,6)).strip()!='Nota':
        raise ValidacaoError(f'Layout inesperado em {aba}, linha 2')
    regs=[]
    for r,values in sh.nonempty_rows():
        if r<3:continue
        rod=values.get(2);ref=values.get(4);length=values.get(5);nota=values.get(6)
        if not rod and not ref and not length and not nota:continue
        if not (rod and ref and length is not None and nota):
            raise ValidacaoError(f'Registro incompleto no LVC: linha {r}')
        pct={}
        for key,c in PERCENT_COLS.items():
            v=values.get(c)
            if v is not None and str(v).strip()!='':pct[key]=_numero(v)
        regs.append(RegistroLVC(str(rod).strip(),str(ref).strip(),_numero(length),str(nota).strip(),
                                r,aba,pct))
    return regs

def carregar_regras_planilha(sheets:dict[str,Sheet], *,aba='LVC - dados 2026')->dict[str,dict[str,float]]:
    sh=sheets[aba]
    # Q4:Z10: nota + 9 percentuais; células vazias são zero por convenção da planilha.
    regras={}
    for row in range(4,11):
        nota=sh.cell(row,17)
        if nota is None:continue
        valores={k:_numero(sh.cell(row,col)) if sh.cell(row,col) is not None else 0.0
                for col,k in zip(range(18,27),CAMPOS)}
        for k,v in valores.items():
            if not 0<=v<=1:raise ValidacaoError(f'Percentual {nota}/{k} fora do intervalo [0,1]')
        regras[str(nota).strip()]=valores
    if not regras:raise ValidacaoError('Tabela Q4:Z10 não encontrada na planilha')
    return regras

def carregar_lvc_csv(path:str|Path)->list[RegistroLVC]:
    p=Path(path)
    with p.open(encoding='utf-8-sig',newline='') as fh:
        sample=fh.read(1024);fh.seek(0)
        # O cabeçalho define o separador, sem confundir a vírgula decimal brasileira.
        first=sample.splitlines()[0] if sample else ''
        dialect=csv.excel()
        dialect.delimiter=';' if first.count(';')>=first.count(',') else ','
        leitor=csv.DictReader(fh,dialect=dialect)
        obrig={'rodovia','referencia','extensao_km','nota'}
        if not leitor.fieldnames or not obrig.issubset(leitor.fieldnames):
            raise ValidacaoError(f'CSV precisa das colunas: {", ".join(sorted(obrig))}')
        regs=[]
        for line,row in enumerate(leitor,2):
            linha=row.get('linha_origem')
            pct={k:_numero(row[k]) for k in CAMPOS if row.get(k) not in (None,'')}
            regs.append(RegistroLVC(row['rodovia'].strip(),row['referencia'].strip(),
                                    _numero(row['extensao_km']),row['nota'].strip(),
                                    int(linha) if linha else line,p.name,pct))
        return regs

def exportar_lvc_csv(registros:list[RegistroLVC],path:str|Path):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as fh:
        w=csv.writer(fh,delimiter=';');w.writerow(['rodovia','referencia','extensao_km','nota','linha_origem',*CAMPOS])
        for r in registros:
            w.writerow([r.rodovia,r.referencia,f'{r.extensao_km:.6f}'.replace('.',','),r.nota,r.linha_origem or '',
                        *(f"{r.percentuais_fonte[k]:.8f}".replace('.',',') if r.percentuais_fonte and k in r.percentuais_fonte else '' for k in CAMPOS)])
