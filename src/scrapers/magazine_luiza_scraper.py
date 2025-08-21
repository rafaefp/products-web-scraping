from typing import List, Optional
import urllib.parse
import re
import time
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from ..models import ProductInfo, SiteConfig


class MagazineLuizaScraper(BaseScraper):
    """Scraper específico para Magazine Luiza"""

    def __init__(self):
        config = SiteConfig(
            name="Magazine Luiza",
            base_url="https://www.magazineluiza.com.br",
            search_url_pattern="https://www.magazineluiza.com.br/busca/{query}/",
            selectors={
                "product_container": "[data-testid='product-card'], .sc-kpDqfm, .product-card, .product-item",
                "title": "[data-testid='product-title'], .sc-dcJsrY h2, .product-title, h2 a, h3 a",
                "price": "[data-testid='price-value'], .sc-kgTSHT, .price-template, .price, .sales-price",
                "original_price": "[data-testid='old-price'], .sc-jrAGrp, .old-price, .list-price, .price-line-through",
                "link": "a[href*='/p/'], .product-link, a[data-testid='product-link']",
                "image": "[data-testid='product-image'] img, .sc-dkrFOg img, .product-image img, .product-card img",
                "rating": "[data-testid='rating'], .rating, .stars, .review-stars",
                "reviews": "[data-testid='reviews-count'], .reviews-count, .reviews, .review-count",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            },
            rate_limit_delay=2.5,
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """Constrói URL de busca do Magazine Luiza"""
        # Remove caracteres especiais e substitui espaços por +
        encoded_query = urllib.parse.quote_plus(product_name)
        return f"https://www.magazineluiza.com.br/busca/{encoded_query}/"

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos do HTML do Magazine Luiza"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Magazine Luiza usa renderização JavaScript - precisamos aguardar elementos carregarem
        # Vamos usar seletores mais robustos baseados na estrutura atual
        product_containers = []

        # Tentativa 1: Seletores específicos do Magazine Luiza
        selectors_to_try = [
            "li[data-testid*='product']",  # Produtos com data-testid
            "div[data-testid*='product']",
            "article[data-testid*='product']",
            "[data-testid*='card']",
            "li[class*='product']",  # Classes com product
            "div[class*='product']",
            "article[class*='product']",
            "li[class*='card']",  # Classes com card
            "div[class*='card']",
            "article[class*='card']",
            ".sc-kpDqfm",  # Classes do styled-components encontradas
            ".sc-dcJsrY",
            ".sc-fqkvVR",
            "li",  # Elementos genéricos como fallback
            "article",
            "div[class*='sc-']",  # Styled components genéricos
        ]

        for selector in selectors_to_try:
            containers = soup.select(selector)
            if containers:
                # Filtra apenas containers que parecem ter produtos (com texto relevante)
                filtered_containers = []
                for container in containers:
                    text_content = container.get_text().lower()
                    # Verifica se o container tem indicadores de produto
                    if (
                        any(
                            indicator in text_content
                            for indicator in [
                                "r$",
                                "preço",
                                "produto",
                                "comprar",
                                "adicionar",
                            ]
                        )
                        and len(text_content) > 10
                    ):
                        filtered_containers.append(container)

                if filtered_containers:
                    product_containers = filtered_containers[
                        :50
                    ]  # Limita para performance
                    logger.info(
                        f"Magazine Luiza: Usando seletor '{selector}' - {len(product_containers)} containers filtrados"
                    )
                    break

        logger.info(f"Encontrados {len(product_containers)} produtos no Magazine Luiza")

        # Para evitar duplicatas
        seen_urls = set()

        for container in product_containers:
            try:
                # Nome do produto - múltiplas tentativas
                name = None
                name_selectors = [
                    "h2",
                    "h3",
                    "h4",
                    "[data-testid*='title']",
                    "[data-testid*='name']",
                    ".product-title",
                    ".product-name",
                    "a[title]",
                    "[title]",
                ]

                for name_selector in name_selectors:
                    name_elem = container.select_one(name_selector)
                    if name_elem:
                        if name_elem.get("title"):
                            name = name_elem["title"]
                        elif name_elem.get_text(strip=True):
                            name = name_elem.get_text(strip=True)

                        if name and len(name) > 5:
                            break

                if not name or len(name) < 3:
                    continue

                # Preço - múltiplas tentativas
                price = None
                price_selectors = [
                    "[data-testid*='price']",
                    ".price",
                    ".valor",
                    "[class*='price']",
                    "span:contains('R$')",
                    "[class*='sc-k'] span",  # Styled components
                    "strong",
                    "b",
                ]

                for price_selector in price_selectors:
                    price_elements = container.select(price_selector)
                    for price_elem in price_elements:
                        price_text = price_elem.get_text(strip=True)
                        if "R$" in price_text or (
                            "," in price_text and any(c.isdigit() for c in price_text)
                        ):
                            price = self._extract_price(price_text)
                            if price and price > 0:
                                break
                    if price:
                        break

                if not price:
                    continue

                # URL do produto
                product_url = None
                link_selectors = [
                    "a[href*='/p/']",
                    "a[href*='produto']",
                    "a[href]",
                ]

                for link_selector in link_selectors:
                    link_elem = container.select_one(link_selector)
                    if link_elem and link_elem.get("href"):
                        href = link_elem["href"]
                        if "/p/" in href or "produto" in href:
                            product_url = href
                            break

                # Se não encontrou URL específica, usa qualquer link válido
                if not product_url:
                    link_elem = container.select_one("a[href]")
                    if link_elem:
                        product_url = link_elem["href"]

                if product_url and not product_url.startswith("http"):
                    if product_url.startswith("/"):
                        product_url = f"https://www.magazineluiza.com.br{product_url}"

                # Evitar duplicatas por URL
                if product_url and product_url in seen_urls:
                    continue
                if product_url:
                    seen_urls.add(product_url)

                # Imagem
                image_url = None
                img_elem = container.select_one("img[src], img[data-src]")
                if img_elem:
                    image_url = img_elem.get("src") or img_elem.get("data-src")

                # Se tem nome, preço e pelo menos 3 caracteres no nome
                if name and price and len(name) >= 3:
                    product = ProductInfo(
                        name=name,
                        price=price,
                        url=product_url or base_url,
                        image_url=image_url,
                        site=self.config.name,
                        availability="Disponível",
                    )
                    products.append(product)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Magazine Luiza: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos do Magazine Luiza")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço"""
        if not price_text:
            return None

        # Remove caracteres não numéricos exceto vírgulas e pontos
        cleaned = re.sub(r"[^\d,.]", "", price_text)

        # Trata diferentes formatos de preço brasileiros
        if "," in cleaned and "." in cleaned:
            # Formato: 1.234,56
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            # Formato: 1234,56
            cleaned = cleaned.replace(",", ".")

        try:
            return float(cleaned)
        except ValueError:
            return None
