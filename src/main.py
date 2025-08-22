#!/usr/bin/env python3
"""
E-commerce Price Scraper POC
==============================

POC para testar agentes que buscam produtos e preços em sites de e-commerce brasileiros
usando Python, LangGraph e Selenium.

Sites suportados:
- Amazon BR
- Mercado Livre
- Carrefour
- Magazine Luiza
- Samsung
- LG
- Casas Bahia
- Ponto Frio

Uso:
    python main.py "iPhone 16 Pro Max" "amazon"
    python main.py "iPhone 16 Pro Max" "mercadolivre"
    python main.py "iPhone 16 Pro Max" "casas_bahia"
    python main.py "iPhone 16 Pro Max" "ponto_frio"
    python main.py "iPhone 16 Pro Max" "carrefour"
    python main.py "iPhone 16 Pro Max" "all"
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Adiciona o diretório pai ao path para imports
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

from src.models import ScrapingRequest, ScrapingResult
from src.agents import ScrapingOrchestrator
from src.utils import DataStorage, ConfigManager, Logger


def setup_environment():
    """Configura o ambiente da aplicação"""
    # Carrega configurações
    config = ConfigManager()

    # Configura logging
    log_level = "DEBUG" if config.get_bool("DEBUG") else "INFO"
    Logger.setup_logging(level=log_level, log_file="data/logs/scraper.log")

    return config


def print_results(result: ScrapingResult):
    """Exibe os resultados do scraping de forma formatada"""
    print("\n" + "=" * 80)
    print(f"RESULTADOS DO SCRAPING - {result.request.product_name.upper()}")
    print("=" * 80)

    print(f"📊 Resumo:")
    print(f"   • Total de produtos encontrados: {result.total_found}")
    print(f"   • Sites pesquisados: {', '.join(result.request.target_sites)}")
    print(f"   • Tempo de execução: {result.execution_time:.2f}s")
    print(f"   • Erros: {len(result.errors)}")

    if result.errors:
        print(f"\n❌ Erros encontrados:")
        for error in result.errors:
            print(f"   • {error}")

    if result.products:
        print(f"\n🛍️ Produtos encontrados:")
        print("-" * 80)

        for i, product in enumerate(result.products, 1):
            print(f"\n{i}. {product.name}")
            print(
                f"   💰 Preço: R$ {product.price:.2f}"
                if product.price
                else "   💰 Preço: Não disponível"
            )

            if product.original_price and product.original_price > product.price:
                print(f"   🏷️  Preço original: R$ {product.original_price:.2f}")
                if product.discount_percentage:
                    print(f"   🔥 Desconto: {product.discount_percentage:.1f}%")

            print(f"   🏪 Site: {product.site}")
            print(f"   🔗 URL: {product.url}")

            if product.rating:
                print(f"   ⭐ Avaliação: {product.rating}/5")

            if product.reviews_count:
                print(f"   📝 Avaliações: {product.reviews_count}")

            if product.delivery_info:
                print(f"   🚚 Entrega: {product.delivery_info}")

            print(
                f"   📅 Coletado em: {product.scraped_at.strftime('%d/%m/%Y %H:%M:%S')}"
            )
    else:
        print(f"\n❌ Nenhum produto encontrado.")

    print("\n" + "=" * 80)


def print_price_comparison(result: ScrapingResult):
    """Exibe comparação de preços entre sites"""
    if len(result.products) < 2:
        return

    print(f"\n💰 COMPARAÇÃO DE PREÇOS")
    print("-" * 50)

    # Agrupa por site
    sites_prices = {}
    for product in result.products:
        if product.price:
            site = product.site
            if site not in sites_prices:
                sites_prices[site] = []
            sites_prices[site].append(product.price)

    # Calcula preço médio por site
    for site, prices in sites_prices.items():
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)

        print(f"{site}:")
        print(f"  • Menor preço: R$ {min_price:.2f}")
        print(f"  • Maior preço: R$ {max_price:.2f}")
        print(f"  • Preço médio: R$ {avg_price:.2f}")
        print()


async def main():
    """Função principal"""
    parser = argparse.ArgumentParser(
        description="POC de scraping de preços em e-commerces brasileiros",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python main.py "iPhone 16 Pro Max" amazon
  python main.py "Samsung Galaxy S24" mercadolivre  
  python main.py "Samsung Galaxy S24" samsung
  python main.py "Notebook Dell" all
  python main.py "Smart TV 55" amazon mercadolivre

Sites suportados: amazon, mercadolivre, magazine_luiza, carrefour, samsung, lg, casas_bahia, ponto_frio, all

Nota: O parâmetro 'all' inclui apenas os sites de e-commerce gerais: amazon, mercadolivre, carrefour, magazine_luiza.
      Os sites de marca (samsung, lg) e específicos (casas_bahia, ponto_frio) devem ser especificados individualmente.
        """,
    )

    parser.add_argument("product_name", help="Nome do produto a ser buscado")

    parser.add_argument(
        "sites",
        nargs="+",
        help="Sites onde buscar (amazon, mercadolivre, magazine_luiza, carrefour, samsung, lg, casas_bahia, ponto_frio, all)",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Máximo de resultados por site (padrão: 5)",
    )

    parser.add_argument(
        "--save", action="store_true", help="Salvar resultados em arquivo"
    )

    args = parser.parse_args()

    # Configura ambiente
    config = setup_environment()

    # Processa sites de destino
    target_sites = []
    for site in args.sites:
        site_lower = site.lower()
        if site_lower == "all":
            target_sites = [
                "amazon",
                "mercadolivre",
                "carrefour",
                "magazine_luiza",
            ]
            break
        else:
            target_sites.append(site_lower)

    # Cria requisição
    request = ScrapingRequest(
        product_name=args.product_name,
        target_sites=target_sites,
        max_results_per_site=args.max_results,
    )

    print(f"🔍 Buscando '{args.product_name}' em: {', '.join(target_sites)}")
    print(f"📊 Máximo de {args.max_results} resultados por site")
    print("⏳ Iniciando scraping...\n")

    # Executa scraping
    orchestrator = ScrapingOrchestrator()

    try:
        # Executa o scraping
        result = await orchestrator.scrape(request)

        # Exibe resultados
        print_results(result)
        print_price_comparison(result)

        # Salva resultados se solicitado
        if args.save:
            storage = DataStorage()
            json_file = storage.save_scraping_result(result)
            print(f"💾 Resultados salvos em: {json_file}")

            if result.products:
                csv_file = storage.save_products_csv(result.products)
                print(f"📊 CSV salvo em: {csv_file}")

        # Retorna código de saída baseado no sucesso
        return 0 if result.products else 1

    except KeyboardInterrupt:
        print("\n⏹️  Scraping interrompido pelo usuário")
        return 1
    except Exception as e:
        print(f"\n❌ Erro inesperado: {str(e)}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Programa interrompido")
        sys.exit(1)
