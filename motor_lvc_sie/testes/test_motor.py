"""Testes determinísticos: execute python -m unittest discover -s motor_lvc_sie/testes -v."""
import json
import math
import tempfile
import unittest
from pathlib import Path
from motor_lvc_sie.core import (RegistroLVC,ValidacaoError,Premissas,
                                carregar_regras,aplicar_regras,consolidar,calcular,
                                selecionar,comparar_referencia,exportar,resumo)
from motor_lvc_sie.io import carregar_lvc_csv,exportar_lvc_csv

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'dados'
ROD='SC-108'
REF='SÃO JOÃO BATISTA - MAJOR GERCINO (ENTR. SC-408)'

class TesteMotor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=carregar_lvc_csv(P/'lvc_sc108_piloto.csv')
        cls.regras=carregar_regras(P/'regras_lvc_2026.json')
        cls.par=Premissas(**json.loads((P/'premissas_crval.json').read_text(encoding='utf-8')))
        cls.pares,cls.div=aplicar_regras(cls.reg,cls.regras)
        cls.c=consolidar(cls.pares)
        cls.items=calcular(cls.c,cls.par)

    def test_01_importa_26_lvc_e_extensao(self):
        self.assertEqual(len(self.reg),26)
        self.assertAlmostEqual(sum(r.extensao_km for r in self.reg),25.478,places=9)
        self.assertEqual(self.c.notas,{'Bom(8)':20,'Regular(5)':1,'Regular(6)':2,'Ruim(4)':3})

    def test_02_regras_originais_por_nota(self):
        self.assertAlmostEqual(self.regras['Ruim(4)']['reciclagem'],1.0)
        self.assertAlmostEqual(self.regras['Regular(6)']['fresagem_continua'],.15)
        self.assertAlmostEqual(self.regras['Bom(8)']['selagem_trincas'],1.0)
        self.assertEqual(self.div,[])

    def test_03_medias_aritmeticas(self):
        self.assertEqual(self.c.modo,'original')
        self.assertAlmostEqual(self.c.percentuais['reciclagem'],3/26,places=12)
        self.assertAlmostEqual(self.c.percentuais['fresagem_continua'],1.4/26,places=12)
        self.assertAlmostEqual(self.c.percentuais['remendo_profundo'],.26/26,places=12)

    def test_04_valida_30_colunas_do_memorial(self):
        comp=comparar_referencia(self.items,P/'referencia_memorial_sc108.json',1e-5)
        self.assertEqual(comp['quantidade_comparada'],30)
        self.assertEqual(comp['quantidade_ok'],30)
        self.assertEqual(comp['quantidade_divergente'],0)

    def test_05_numeros_piloto(self):
        self.assertAlmostEqual(self.items['reciclagem_m3'].valor,4115.676923076923,places=7)
        self.assertAlmostEqual(self.items['fresagem_descontinua_m3'].valor,445.865,places=6)
        self.assertAlmostEqual(self.items['fresagem_continua_m3'].valor,480.1623076923077,places=6)
        self.assertAlmostEqual(self.items['microrrevestimento_m2'].valor,20578.384615384617,places=6)
        self.assertAlmostEqual(self.items['remocao_granular_m3'].valor,624.211,places=6)
        self.assertAlmostEqual(self.items['selagem_trincas_unid_planilha'].valor,548.756923076923,places=6)

    def test_06_modo_ponderado_por_extensao(self):
        c=consolidar(self.pares,'ponderado')
        self.assertAlmostEqual(c.percentuais['reciclagem'],2.478/25.478,places=12)
        q=calcular(c,self.par)
        self.assertAlmostEqual(q['reciclagem_m3'].valor,3469.2,places=5)
        self.assertLess(q['reciclagem_m3'].valor,self.items['reciclagem_m3'].valor)

    def test_07_rejeita_nota_sem_regra(self):
        reg=RegistroLVC(ROD,REF,1.0,'Inexistente(1)')
        with self.assertRaises(ValidacaoError):aplicar_regras([reg],self.regras)

    def test_08_rejeita_extensao_invalida(self):
        with self.assertRaises(ValidacaoError):RegistroLVC(ROD,REF,-1.0,'Bom(8)')
        with self.assertRaises(ValidacaoError):RegistroLVC(ROD,REF,0.0,'Bom(8)')

    def test_09_rejeita_segmentos_distintos(self):
        reg1=RegistroLVC(ROD,REF,1,'Bom(8)')
        reg2=RegistroLVC(ROD,'TRECHO DIFERENTE',1,'Bom(8)')
        pairs,_=aplicar_regras([reg1,reg2],self.regras)
        with self.assertRaises(ValidacaoError):consolidar(pairs)

    def test_10_csv_ida_e_volta(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reexportado.csv'
            exportar_lvc_csv(self.reg,p)
            back=carregar_lvc_csv(p)
            self.assertEqual(len(back),26)
            self.assertEqual(back[0].nota,self.reg[0].nota)
            self.assertAlmostEqual(back[-1].extensao_km,.478)

    def test_11_relatorio_json_e_csv(self):
        with tempfile.TemporaryDirectory() as d:
            report=resumo(self.c,self.items,self.par)
            out=exportar(report,d)
            self.assertTrue((out/'memoria_calculo.json').exists())
            self.assertTrue((out/'quantitativos.csv').exists())
            self.assertEqual(len(json.loads((out/'memoria_calculo.json').read_text(encoding='utf-8'))['quantitativos']),30)

if __name__=='__main__':unittest.main()
