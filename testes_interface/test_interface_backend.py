"""Testes da camada de orquestração da interface; independentes do Streamlit."""
import json
import math
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from interface_backend import (
    DADOS, LABELS, carregar_fonte, rodovias_e_trechos, calcular_trecho,
    regra_editada, linhas_regras, linhas_lvc, linhas_quantitativos,
    arquivos_resultado, zip_resultados, ValidacaoError,
)
from motor_lvc_sie.core import Premissas

ROD = 'SC-108'
TRECHO = 'SÃO JOÃO BATISTA - MAJOR GERCINO (ENTR. SC-408)'


class TestesInterfaceBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados = (DADOS / 'lvc_base_crval_65_trechos.csv').read_bytes()
        cls.base = carregar_fonte('base.csv', cls.dados)
        cls.p = Premissas(**json.loads((DADOS / 'premissas_crval.json').read_text(encoding='utf-8')))

    def _calculo(self, modo='original', premissas=None, regras=None):
        return calcular_trecho(self.base, ROD, TRECHO, modo=modo,
                              premissas=premissas or self.p,
                              regras=regras or self.base.regras)

    def test_01_base_65_trechos(self):
        self.assertEqual(len(self.base.registros), 697)
        redes = rodovias_e_trechos(self.base.registros)
        self.assertEqual(sum(len(x) for x in redes.values()),65)
        self.assertEqual(len(redes),22)
        self.assertIn(TRECHO, redes[ROD])

    def test_02_piloto_e_referencia(self):
        x = self._calculo()
        self.assertEqual(len(x['registros']), 26)
        self.assertAlmostEqual(x['consolidado'].extensao_km,25.478,places=7)
        self.assertEqual(len(x['itens']),30)
        self.assertEqual(x['comparacao']['quantidade_ok'],30)
        self.assertEqual(x['comparacao']['quantidade_divergente'],0)

    def test_03_ponderacao(self):
        x = self._calculo('ponderado')
        self.assertAlmostEqual(x['itens']['reciclagem_m3'].valor,3469.2,places=5)
        self.assertIsNone(x['comparacao'])

    def test_04_edit_premissas(self):
        novo = Premissas(**{**self.p.__dict__, 'largura_m':8.0})
        x = self._calculo(premissas=novo)
        self.assertAlmostEqual(x['itens']['reciclagem_m3'].valor,4115.676923076923*(8/7),places=6)
        self.assertIsNone(x['comparacao'])

    def test_05_edicao_criterios(self):
        tabela = linhas_regras(self.base.regras)
        self.assertEqual(len(tabela),7)
        for linha in tabela:
            if linha['Nota']=='Ruim(4)':linha[LABELS['reciclagem']]=50.0
        novas=regra_editada(tabela,self.base.regras)
        self.assertEqual(novas['Ruim(4)']['reciclagem'],.5)
        x=self._calculo(regras=novas)
        self.assertLess(x['itens']['reciclagem_m3'].valor,4115.7)
        self.assertTrue(x['divergencias'])
        self.assertIsNone(x['comparacao'])

    def test_06_rejeita_regra_fora_do_limite(self):
        tabela=linhas_regras(self.base.regras)
        tabela[0][LABELS['reciclagem']]=110.0
        with self.assertRaises(ValidacaoError):regra_editada(tabela,self.base.regras)

    def test_07_exportacoes_zip(self):
        x=self._calculo()
        arquivos=arquivos_resultado(x)
        self.assertIn('memoria_calculo.json',arquivos)
        self.assertIn('quantitativos.csv',arquivos)
        self.assertIn('percentuais_consolidados.csv',arquivos)
        self.assertIn('comparacao_memorial.csv',arquivos)
        self.assertEqual(len(linhas_quantitativos(x['itens'])),30)
        self.assertEqual(len(linhas_lvc(x['pares'])),26)
        memoria=json.loads(arquivos['memoria_calculo.json'])
        self.assertEqual(memoria['consolidacao']['quantidade_registros'],26)
        with ZipFile(BytesIO(zip_resultados(arquivos))) as z:
            self.assertEqual(set(z.namelist()),set(arquivos))
            self.assertEqual(z.read('memoria_calculo.json'),arquivos['memoria_calculo.json'])

    def test_08_upload_xlsx_de_exemplo(self):
        p=DADOS/'exemplo_sc108_layout_crval.xlsx'
        fonte=carregar_fonte(p.name,p.read_bytes())
        self.assertEqual(len(fonte.registros),26)
        self.assertIsNotNone(fonte.memorial)
        x=calcular_trecho(fonte,ROD,TRECHO,modo='original',premissas=self.p,regras=fonte.regras)
        self.assertEqual(x['comparacao']['quantidade_ok'],30)

    def test_09_upload_csv_exemplo(self):
        p=DADOS/'lvc_sc108_piloto.csv'
        fonte=carregar_fonte(p.name,p.read_bytes())
        self.assertEqual(len(fonte.registros),26)

    def test_10_rejeita_arquivos_invalidos(self):
        with self.assertRaises(ValidacaoError):carregar_fonte('dados.exe',b'aaaaaaaa')
        with self.assertRaises(ValidacaoError):carregar_fonte('dados.csv',b'')
        with self.assertRaises(ValidacaoError):carregar_fonte('dados.csv',b'x'*(25*1024*1024+1))

    def test_11_csv_criado_e_reimportado(self):
        x=self._calculo()
        regcsv=arquivos_resultado(x)['registros_lvc.csv']
        # Este relatório de auditoria usa colunas em português, não é o modelo de entrada.
        self.assertTrue(regcsv.startswith(b'\xef\xbb\xbf'))
        self.assertIn('Fresagem descontínua'.encode('utf-8'),regcsv)

if __name__=='__main__': unittest.main()
