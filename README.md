# E-commerce Price Scraper POC

## Visão Geral
POC para testar agentes que buscam produtos e preços em sites de e-commerce brasileiros usando Python, LangGraph e Selenium com estratégias anti-detecção.

## Stack Tecnológica
- **Python 3.11+**: Linguagem principal
- **LangGraph**: Orquestração multi-agente e workflow
- **Selenium WebDriver**: Web scraping principal com evasão de anti-bot
- **BeautifulSoup4**: Parsing e extração de dados HTML
- **Requests**: Fallback HTTP para sites simples
- **Pydantic**: Validação e estruturação de dados

## Sites Suportados
- **Amazon BR**: Produtos e preços
- **Mercado Livre**: Produtos e preços 
- **Carrefour**: Produtos e preços 
- **Magazine Luiza**: Produtos e preços
- **Americanas**: Produtos e preços
- **Casas Bahia**: Produtos e preços (⚠️ *Bloqueado por anti-bot avançado*)
- **Ponto Frio**: Produtos e preços (⚠️ *Bloqueado por anti-bot avançado*)

## Como Usar

### Instalação
```bash
# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente virtual (Windows)
.venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

### Configuração
```bash
# Configurar variáveis de ambiente (opcional)
cp .env.example .env
# Editar .env com configurações específicas se necessário
```

### Execução
```bash
# Buscar produto em site específico
python src/main.py "iPhone 16 Pro Max" amazon

# Buscar em múltiplos sites
python src/main.py "iPhone 16 Pro Max" all

# Buscar com mais resultados por site
python src/main.py "iPhone 16 Pro Max" amazon --max-results 10

# Salvar resultados em arquivo
python src/main.py "iPhone 16 Pro Max" all --save
```

## Estrutura do Projeto
```
src/
├── main.py                           # Ponto de entrada principal
├── agents/
│   └── scraping_orchestrator.py      # Orquestrador LangGraph multi-agente
├── scrapers/
│   ├── base_scraper.py              # Classe base para scrapers
│   └── ecommerce_scrapers.py        # Implementações específicas por site
├── models/
│   └── __init__.py                  # Modelos Pydantic (Product, ScrapingRequest, etc.)
└── utils/
    └── data_storage.py              # Utilitários para persistência de dados

data/
├── products/                        # Dados extraídos salvos
├── results/                         # Resultados formatados
└── logs/                           # Logs de execução
```

## Arquitetura

### Pipeline de Scraping
1. **Entrada**: Produto + sites alvo → `ScrapingRequest`
2. **Orquestração**: LangGraph coordena agentes por site
3. **Scraping**: Selenium → requests fallback por site
4. **Validação**: Pydantic valida dados extraídos  
5. **Saída**: `ScrapingResult` consolidado

### Estratégias Anti-Detecção
- **User agents** rotativos e realistas
- **Headers HTTP** customizados por site
- **Delays** aleatórios entre requisições
- **Selenium** com configurações anti-detecção
- **Fallback** para requests em caso de bloqueio

## Exemplo de Resultado
```json
{
  "request": {
    "product_name": "iPhone 16 Pro Max",
    "target_sites": ["amazon", "mercadolivre"]
  },
  "products": [
    {
      "name": "iPhone 16 Pro Max 256GB",
      "price": "R$ 8.999,00",
      "site": "amazon",
      "url": "https://...",
      "availability": "Em estoque"
    }
  ],
  "summary": {
    "total_products": 6,
    "sites_searched": 2,
    "execution_time": "45.2s"
  }
}
```
