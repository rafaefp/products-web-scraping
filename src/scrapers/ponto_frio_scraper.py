import re
import urllib.parse
from typing import List, Optional
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from ..models import ProductInfo, SiteConfig


class PontoFrioScraper(BaseScraper):
    """Scraper específico para Ponto Frio"""

    def __init__(self):
        config = SiteConfig(
            name="Ponto Frio",
            base_url="https://www.pontofrio.com.br",
            search_url_pattern="https://www.pontofrio.com.br/busca/{query}",
            selectors={
                "product_container": "[data-testid='product-card'], .product-card, .showcase-item, .product-item",
                "product_name": "h2, h3, .product-title, [data-testid='product-title']",
                "product_price": ".price-current, .sales-price, .price, [data-testid='price-value']",
                "product_url": "a",
                "product_image": "img",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8,en-US;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Referer": "https://www.pontofrio.com.br/",  # Muito importante para parecer navegação natural
                "Origin": "https://www.pontofrio.com.br",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
            rate_limit_delay=3.0,  # Delay maior para ser mais cauteloso
            max_retries=3,
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """Constrói URL de busca para Ponto Frio"""
        encoded_query = urllib.parse.quote_plus(product_name)
        return f"https://www.pontofrio.com.br/busca?q={encoded_query}"

    def extract_product_info(
        self, html_content: str, base_url: str, max_results: int = 10
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos do HTML do Ponto Frio"""
        products = []
        seen_urls = set()

        soup = BeautifulSoup(html_content, "html.parser")

        # Ponto Frio usa estrutura similar ao Magazine Luiza e Casas Bahia
        product_containers = []

        # Tentativa 1: Seletores específicos do Ponto Frio
        selectors_to_try = [
            "[data-testid='product-card']",  # Produtos com data-testid
            "div[data-testid*='product']",
            "article[data-testid*='product']",
            ".product-card",  # Classes com product
            ".showcase-item",
            ".product-item",
            "div[class*='product']",
            "li[class*='product']",
            ".item",  # Fallback genérico
            "article",
        ]

        for selector in selectors_to_try:
            containers = soup.select(selector)
            if containers:
                logger.info(
                    f"Ponto Frio: Usando seletor '{selector}' - {len(containers)} containers"
                )
                product_containers = containers[
                    : max_results * 2
                ]  # Limitar para evitar spam
                break

        if not product_containers:
            logger.warning("Ponto Frio: Nenhum container de produto encontrado")
            return products

        logger.info(f"Encontrados {len(product_containers)} produtos no Ponto Frio")

        for container in product_containers[
            : max_results * 2
        ]:  # Processa mais para filtrar
            if len(products) >= max_results:
                break

            try:
                # Nome do produto - múltiplas tentativas
                name_element = None
                name_selectors = [
                    "h2",
                    "h3",
                    "h1",
                    "[data-testid*='title']",
                    "[data-testid*='name']",
                    ".product-title",
                    ".product-name",
                    ".title",
                    ".name",
                    "a[title]",
                ]

                for name_sel in name_selectors:
                    name_element = container.select_one(name_sel)
                    if name_element and name_element.get_text(strip=True):
                        break

                name = ""
                if name_element:
                    name = name_element.get_text(strip=True)
                    # Se não tem texto, tenta o atributo title
                    if not name and name_element.get("title"):
                        name = name_element["title"].strip()

                if not name or len(name) < 3:
                    continue

                # Preço - múltiplas tentativas
                price = None
                price_selectors = [
                    "[data-testid*='price']",
                    ".price-current",
                    ".sales-price",
                    ".price",
                    ".value",
                    ".preco",
                    ".valor",
                    "span[class*='price']",
                    "div[class*='price']",
                    "strong",
                    "b",  # Fallback para elementos em negrito
                ]

                for price_sel in price_selectors:
                    price_elements = container.select(price_sel)
                    for price_elem in price_elements:
                        text = price_elem.get_text(strip=True)
                        if text and (
                            "R$" in text
                            or "," in text
                            or text.replace(".", "").isdigit()
                        ):
                            price = self._extract_price(text)
                            if price:
                                break
                    if price:
                        break

                if not price:
                    continue

                # URL do produto
                url = ""
                link_element = container.select_one("a[href]")
                if link_element:
                    url = link_element["href"]
                    if url.startswith("/"):
                        url = f"https://www.pontofrio.com.br{url}"
                    elif not url.startswith("http"):
                        url = f"https://www.pontofrio.com.br/{url}"

                # Evitar duplicatas por URL
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

                # URL fallback
                if not url:
                    url = base_url

                # Imagem do produto
                image_url = ""
                img_element = container.select_one("img[src], img[data-src]")
                if img_element:
                    image_url = img_element.get("src") or img_element.get(
                        "data-src", ""
                    )
                    if image_url and not image_url.startswith("http"):
                        if image_url.startswith("//"):
                            image_url = f"https:{image_url}"
                        elif image_url.startswith("/"):
                            image_url = f"https://www.pontofrio.com.br{image_url}"

                # Preço original
                original_price = None
                original_price_selectors = [
                    "[data-testid='old-price']",
                    ".old-price",
                    ".list-price",
                    ".crossed-out-price",
                    "s",
                    ".strike",
                ]

                for orig_sel in original_price_selectors:
                    orig_elem = container.select_one(orig_sel)
                    if orig_elem:
                        orig_text = orig_elem.get_text(strip=True)
                        if orig_text:
                            orig_price = self._extract_price(orig_text)
                            if orig_price and orig_price > price:
                                original_price = orig_price
                                break

                # Calcular desconto
                discount_percentage = None
                if original_price and price and original_price > price:
                    discount_percentage = (
                        (original_price - price) / original_price
                    ) * 100

                # Validação final
                if name and price and len(name) >= 3:
                    product = ProductInfo(
                        name=name,
                        price=price,
                        original_price=original_price,
                        discount_percentage=discount_percentage,
                        availability="available",
                        url=url,
                        site=self.config.name,
                        image_url=image_url,
                    )
                    products.append(product)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Ponto Frio: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos do Ponto Frio")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço"""
        if not price_text:
            return None

        try:
            # Remove "R$" e outros caracteres não numéricos, mantendo vírgulas e pontos
            price_clean = re.sub(r"[^\d,.]", "", price_text)

            if not price_clean:
                return None

            # Trata diferentes formatos brasileiros
            if "," in price_clean and "." in price_clean:
                # Formato: 1.234,56 (ponto como separador de milhares, vírgula como decimal)
                # Verifica se o ponto está antes da vírgula
                dot_pos = price_clean.rfind(".")
                comma_pos = price_clean.rfind(",")

                if dot_pos < comma_pos:
                    # 1.234,56 -> remove pontos de milhares, troca vírgula por ponto
                    price_clean = price_clean.replace(".", "").replace(",", ".")
                else:
                    # 1,234.56 -> remove vírgula de milhares (formato US em contexto BR)
                    price_clean = price_clean.replace(",", "")

            elif "," in price_clean:
                # Formato: 1234,56 ou 1,56
                price_clean = price_clean.replace(",", ".")

            # Converte para float
            price = float(price_clean)

            # Valida se é um preço razoável
            if 0 < price < 1000000:
                return price

        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Erro ao extrair preço '{price_text}': {str(e)}")

        return None
