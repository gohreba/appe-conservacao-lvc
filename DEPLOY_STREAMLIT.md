# Publicação do aplicativo APPE LVC no GitHub + Streamlit Community Cloud

Esta pasta já contém **todos os arquivos necessários** para rodar o aplicativo em hospedagem Streamlit. Usuários finais só precisam do link final; não precisam instalar Python nem Streamlit.

## 1. Antes de publicar: decidir a privacidade

O pacote completo contém registros LVC e resultados de referência de um estudo fornecido à APPE, incluindo 65 trechos. **Não disponibilize um repositório público com esses dados sem autorização do titular.**

- **Uso interno da APPE:** prefira repositório GitHub privado e aplicativo Streamlit privado, convidando as pessoas autorizadas no painel de compartilhamento.
- **Link aberto a qualquer pessoa:** é possível configurar um aplicativo público, inclusive com repositório privado, mas os dados incluídos e exibidos pelo aplicativo ficarão acessíveis a seus usuários. Avalie se a base de demonstração poderá ser publicada e, se necessário, substitua-a por dados fictícios antes da liberação.
- Dados enviados pelos visitantes são processados na sessão sem persistência intencional em banco de dados; **isso não equivale a uma política de segurança ou privacidade auditada.** Não utilize com dados sensíveis sem controles adicionais.

## 2. Criar repositório no GitHub

1. Entre em https://github.com e clique em **New repository**.
2. Dê um nome, por exemplo: `appe-conservacao-lvc`.
3. Defina **Private** ou **Public** conforme a regra acima.
4. Crie o repositório.
5. **Extraia o ZIP recebido** e envie ao repositório *o conteúdo da pasta extraída*, não o arquivo ZIP. Use **Add file → Upload files** e mantenha a estrutura de subpastas.
6. Confirme os arquivos em `main` com **Commit changes**.

### Estrutura de arquivos necessária

```text
appe-conservacao-lvc/
├── app.py                       # Ponto de entrada do Streamlit
├── interface_backend.py         # Integração dos módulos
├── requirements.txt             # Dependências de instalação
├── .streamlit/config.toml        # Configurações da interface
├── motor_lvc_sie/
│   ├── core.py                   # Cálculos já testados
│   ├── io.py
│   ├── legacy_xls.py
│   ├── dados/                   # Regras e bases de demonstração
│   └── testes/
├── testes_interface/
└── README.md / DEPLOY_STREAMLIT.md
```

> Se você não conseguir incluir a pasta oculta `.streamlit`, o aplicativo ainda abre com o tema padrão. Os arquivos essenciais são `app.py`, `interface_backend.py`, `requirements.txt` e a pasta `motor_lvc_sie` completa.

## 3. Publicar no Streamlit

1. Abra **https://share.streamlit.io/** e entre com sua conta.
2. Conecte a conta do GitHub, autorizando o repositório criado.
3. Clique em **Create app**, depois **Yup, I have an app**.
4. Escolha o repositório `appe-conservacao-lvc`, branch `main` e arquivo principal **`app.py`**.
5. Escolha, se disponível, um subdomínio como `appe-conservacao-lvc`.
6. Se houver opção para versão Python, prefira **Python 3.12**, compatível com os testes de código.
7. Clique em **Deploy** e confira os registros da implantação até o aplicativo abrir corretamente.
8. Configure a visibilidade em **App settings → Sharing** conforme o público desejado.
9. Copie o endereço final fornecido pelo Streamlit e envie aos usuários.

Endereço de exemplo: `https://appe-conservacao-lvc.streamlit.app`. Este URL **não está criado**; o nome depende da disponibilidade e da efetiva implantação.

## 4. Verificação após a publicação

- Abra em uma janela anônima, simulando um usuário sem Python instalado.
- Teste a base de demonstração e selecione **SC-108 → SÃO JOÃO BATISTA - MAJOR GERCINO (ENTR. SC-408)**.
- Confira 26 registros, extensão de 25,478 km e resultados de reciclagem próximos de 4.115,676923 m³.
- Altere a largura da pista e confirme o recálculo.
- Teste upload de um CSV no modelo fornecido.
- Faça download do ZIP de memória e quantitativos.
- Confirme os controles de acesso com um usuário autorizado e outro não autorizado.

## 5. Atualizações de código

Modifique ou substitua os arquivos no GitHub e salve o commit na branch vinculada. O Streamlit Community Cloud acompanha alterações do repositório e atualiza o aplicativo.

## 6. Como o app funciona na nuvem

- **Sem instalação pelo usuário final:** o navegador abre o aplicativo no domínio `streamlit.app`.
- **Sem banco de dados:** cada sessão trabalha com as entradas e premissas selecionadas; modificações não representam um cadastro compartilhado e permanente.
- **Sem usuários/senhas próprios:** autenticação e autorização dependem da configuração de compartilhamento no Streamlit, ou de uma futura camada institucional.
- **Sem cálculo financeiro nem sinalização:** mantêm-se fora do escopo da versão 0.2.

## 7. Diagnóstico rápido de erros

- `ModuleNotFoundError`: confira os nomes e estrutura de `motor_lvc_sie` e `interface_backend.py`.
- `FileNotFoundError`: confira os arquivos no diretório `motor_lvc_sie/dados`.
- Dependência ausente: confira `requirements.txt` na raiz.
- Apps privados: usuários não convidados não terão acesso até receberem permissão.

## Documentação oficial

- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
