# APPE — Conservação Rodoviária × LVC (versão web)

**Aplicativo Streamlit preparado para publicação no GitHub e Streamlit Community Cloud.**

Para disponibilizar o aplicativo por link, consulte primeiro **[DEPLOY_STREAMLIT.md](DEPLOY_STREAMLIT.md)**.

> O aplicativo ainda não foi publicado. O download contém o código pronto para implantação, não um URL já ativo.

---

# APPE — Conservação Rodoviária × LVC

**Versão 0.2 • Interface Streamlit • Motor de cálculo Python v0.1**

Aplicativo web local para converter registros de **Levantamento Visual Contínuo (LVC)** em percentuais de tratamentos e quantitativos de conservação rodoviária. A lógica das intervenções e das 30 colunas do Memorial Pavimentação reproduz o arquivo **Memória e Quantidades — CRVAL Lotes 1, 2 e 3 R02** encaminhado pela APPE.

> **Situação:** protótipo técnico funcional para avaliação; os critérios, unidades e premissas dependem de homologação do responsável técnico. Não é um sistema multiusuário, não contém banco de dados e não cobre ainda os memoriais de sinalização e a gestão contratual.

## 1. Abrir no Windows sem usar terminal

1. Instale **Python 3.10 ou superior**, se ainda não estiver instalado. Durante a instalação pelo Windows, habilite a opção **Add Python to PATH**.
2. Descompacte todo o ZIP em uma pasta de sua escolha.
3. Execute `INICIAR_WINDOWS.bat` com duplo clique. Na primeira execução, o script instala o Streamlit (requer conexão à internet).
4. O navegador normalmente abre em **http://localhost:8501**. Deixe a janela de execução aberta enquanto utilizar o sistema.
5. Para encerrar, feche a janela de execução ou pressione `Ctrl+C` nela.

Em Linux/macOS, execute `./INICIAR_LINUX_MAC.sh` (Python 3.10+ e pip requeridos).

**Execução manual opcional** (na pasta da aplicação):

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 2. O que existe na interface

| Área | O que faz |
|---|---|
| **Menu lateral** | Seleciona fonte de dados, rodovia, trecho e média simples/ponderada |
| **Visão geral** | Indicadores de extensão e área; volumes principais; gráficos de notas e percentuais |
| **LVC e percentuais** | Exibe os registros, as notas, tratamentos e percentuais consolidados |
| **Premissas e critérios** | Altera largura, espessuras, densidade, coeficiente de selagem e, opcionalmente, percentuais das regras por nota |
| **Quantitativos** | Exibe 30 itens do memorial, sua unidade, equação e coluna de origem |
| **Memória e exportação** | Exporta CSV/JSON/ZIP e, quando aplicável, compara valores com o Excel de referência |

**Atualização automática:** qualquer mudança de rodovia, trecho, método, premissa ou critério dispara um novo cálculo no aplicativo Streamlit.

### Bases incluídas

- **Base CRVAL (65 trechos)**: 697 observações LVC de 22 rodovias/acessos, extraídas da planilha fornecida. Serve para navegar por vários segmentos sem enviar o `.xls` inteiro.
- **Piloto SC-108 (26 registros)**: São João Batista–Major Gercino (Entr. SC-408), extensão 25,478 km.
- **Exemplo `.xlsx`**: contém as abas reduzidas necessárias ao teste do fluxo de importação de planilhas.
- **Arquivos JSON**: regras originais por nota e premissas do memorial.

## 3. Importar seus próprios dados

No menu lateral selecione **Enviar planilha ou CSV** e carregue:

- **CSV** (UTF-8, separado por ponto e vírgula): colunas obrigatórias `rodovia`, `referencia`, `extensao_km`, `nota`; demais colunas de percentuais são opcionais. Baixe o **Modelo de importação CSV** na própria tela. Os valores de extensão estão em km e os percentuais, se fornecidos, em fração de 0 a 1.
- **XLS/XLSX**: no layout CRVAL, com a aba `LVC - dados 2026` e cabeçalhos reconhecidos pelo motor. O app lê as regras da tabela `Q4:Z10`; se existir `Memorial Pavimentação`, pode realizar uma comparação dos valores salvos.

O leitor de planilhas utiliza **valores armazenados**: não executa macros, não recalcula fórmulas e não abre vínculos externos. Se o arquivo estiver com valores de fórmula desatualizados, salve-o após o recálculo no Excel ou exporte um CSV de entrada atualizado. O limite de importação é **25 MB**.

Os arquivos enviados ficam em memória ou em diretório temporário durante o processamento; a interface **não** cria cadastro permanente de arquivos, usuários ou projetos.

## 4. Cálculos e parâmetros

O motor de cálculo é importado de `motor_lvc_sie`, sem duplicação de fórmulas na interface.

- Média **original**: a porcentagem é a média aritmética por registro, como no memorial CRVAL.
- Média **ponderada**: a porcentagem considera o peso da extensão de cada registro; serve para análise e não representa substituição automática da metodologia.
- Para cada item do memorial, a saída identifica o código, a unidade, a equação textual e a coluna de origem.

Exemplo para o piloto SC-108 em modo original e premissas padrão:

| Resultado | Quantidade |
|---|---:|
| Registros / extensão | 26 / 25,478 km |
| Reciclagem | 4.115,676923 m³ |
| Fresagem descontínua | 445,865 m³ |
| Fresagem contínua | 480,162308 m³ |
| Microrrevestimento | 20.578,384615 m² |
| Remoção granular | 624,211 m³ |

Com as premissas e regras padrão no modo original, o app exibe a comparação de **30/30** itens com os valores de referência da SC-108. Quando você altera parâmetros, regras ou método, o app **desativa essa comparação** para evitar classificar cenários intencionais como erros do motor.

## 5. Exportações

Na aba **Memória e exportação** você pode baixar:

- `quantitativos.csv`: serviços, quantidades e fórmulas, compatível com Excel;
- `memoria_calculo.json`: resultado detalhado, premissas, critérios, avisos e identificadores;
- pacote **ZIP** completo, incluindo registros, percentuais consolidados, premissas, regras e, quando aplicável, comparação com o memorial.

O CSV vem em UTF-8 BOM, com separador `;` e vírgula decimal para facilitar abertura no Excel configurado para o Brasil.

## 6. Validação e testes

Os cálculos principais são os mesmos do motor 0.1, anteriormente conferido para os 65 trechos e 30 colunas do memorial (1.950 confrontações sem divergência absoluta maior que `1e-5` na configuração original). Essa conferência é de *reprodução numérica*, não de homologação de engenharia.

Testes automatizados (opcional):

```bash
python -m unittest discover -s motor_lvc_sie/testes -v
python -m unittest discover -s testes_interface -v
```

> A versão do Streamlit deve ser instalada no computador onde você executará a interface. Não é necessário instalar Excel no computador do servidor.

## 7. Limites e cuidados técnicos

1. As intervenções podem **se sobrepor** e os percentuais não representam parcelas mutuamente exclusivas da pista.
2. As colunas H e I do Memorial Pavimentação mostram m³ em cabeçalhos, mas as fórmulas correspondem a m²; o app mantém a anotação `m²*` até validação.
3. A unidade física do coeficiente de selagem de trincas `0,004` exige confirmação, portanto não foi arbitrada.
4. A largura-padrão é **7 m** na base CRVAL, mas outros trechos podem exigir largura específica: altere a premissa no aplicativo.
5. A comparação de referência vale para os dados e parâmetros da planilha original; a edição de cenários não representa erro de cálculo.
6. O protótipo não possui autenticação, integração com sistemas institucionais ou banco de dados; não publique este aplicativo com documentos sensíveis sem essas camadas.

## 8. Estrutura dos arquivos

```text
APPE_Conservacao_LVC_Streamlit_v0_2/
├── app.py                  # Interface web
├── interface_backend.py    # Orquestração: upload, seleção, relatórios e ZIP
├── motor_lvc_sie/
│   ├── core.py             # O mesmo motor numérico validado na v0.1
│   ├── io.py               # CSV/XLS/XLSX
│   ├── legacy_xls.py       # Leitor do Excel 97-2003
│   ├── dados/              # Exemplos e parâmetros
│   └── testes/             # Testes do motor
├── testes_interface/       # Testes dos fluxos de entrada/saída
├── requirements.txt        # Dependência Streamlit
├── .streamlit/config.toml  # Tema e limite de upload
├── INICIAR_WINDOWS.bat     # Duplo clique no Windows
└── INICIAR_LINUX_MAC.sh
```

## 9. Próximo escopo

Nesta versão, a geração de quantitativos compreende **Memorial Pavimentação** e não inclui **Memorial Sinalização L1/L2/L3**, relatórios por lote ou consumo contratual. Esses módulos poderão ser adicionados mantendo o motor atual independente da interface.
