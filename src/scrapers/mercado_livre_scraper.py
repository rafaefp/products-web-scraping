from typing import List, Optional
import urllib.parse
import re
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from ..models import ProductInfo, SiteConfig


class MercadoLivreScraper(BaseScraper):
    """Scraper específico para Mercado Livre"""

    def __init__(self):
        config = SiteConfig(
            name="Mercado Livre",
            base_url="https://www.mercadolivre.com.br",
            search_url_pattern="https://lista.mercadolivre.com.br/{query}",
            selectors={
                "product_container": ".ui-search-result, .andes-card, .shops__item",
                "title": ".ui-search-item__title, .shops__item-title, .andes-card__title",
                "price": ".andes-money-amount__fraction, .price-tag, .andes-money-amount",
                "original_price": ".andes-money-amount--previous .andes-money-amount__fraction",
                "link": ".ui-search-item__group__element a, .shops__item-link, .andes-card__link",
                "image": ".ui-search-result-image__element, .shops__item-image, .andes-card__image",
                "rating": ".ui-search-reviews__rating-number",
                "reviews": ".ui-search-reviews__amount",
            },
            rate_limit_delay=1.5,
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """Constrói URL de busca do Mercado Livre"""
        # Usa formato padrão de busca do ML
        encoded_query = urllib.parse.quote_plus(product_name)
        return f"https://lista.mercadolivre.com.br/{encoded_query}"

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos do HTML do Mercado Livre"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Usando seletores baseados na estrutura HTML real
        product_containers = soup.select(".ui-search-result__wrapper")
        logger.info(f"Encontrados {len(product_containers)} produtos no Mercado Livre")

        for container in product_containers:
            try:
                # Título - primeiro tenta pela imagem title, depois por outros seletores
                title = None
                img_elem = container.select_one("img[title]")
                if img_elem and img_elem.get("title"):
                    title = img_elem["title"]

                # Fallback para outros seletores
                if not title:
                    title_elem = container.select_one(".ui-search-item__title")
                    if title_elem:
                        title = title_elem.get_text(strip=True)

                if not title:
                    continue

                # Link - múltiplas tentativas
                product_url = None
                for link_selector in [
                    "a[href*='/MLB']",
                    ".ui-search-item__group__element a",
                    ".shops__item-link",
                    ".andes-card__link",
                    "a[href]",
                ]:
                    link_elem = container.select_one(link_selector)
                    if link_elem and link_elem.get("href"):
                        product_url = link_elem["href"]
                        break

                if not product_url:
                    continue

                # Preço - usando seletores baseados na estrutura real
                price = None
                for price_selector in [
                    ".poly-price__current .andes-money-amount__fraction",
                    ".poly-component__price .poly-price__current .andes-money-amount__fraction",
                    ".andes-money-amount__fraction",
                    ".price-tag-fraction",
                    ".ui-search-price__second-line .price-tag-fraction",
                    ".price-tag",
                    ".andes-money-amount",
                    ".price",
                ]:
                    price_elem = container.select_one(price_selector)
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        price = self._extract_price(price_text)
                        if price:
                            break

                # Se não encontrou preço, pula
                if not price:
                    continue

                # Preço original (com melhor seletor)
                original_price = None
                for original_price_selector in [
                    ".andes-money-amount--previous .andes-money-amount__fraction",
                    "s .andes-money-amount__fraction",
                    ".poly-component__price s .andes-money-amount__fraction",
                ]:
                    original_price_elem = container.select_one(original_price_selector)
                    if original_price_elem:
                        original_price = self._extract_price(
                            original_price_elem.get_text(strip=True)
                        )
                        break

                # Imagem
                image_url = None
                for img_selector in [
                    "img[src*='mlstatic.com']",
                    ".ui-search-result-image__element",
                    ".poly-component__picture",
                    "img[data-src]",
                    "img",
                ]:
                    img_elem = container.select_one(img_selector)
                    if img_elem and img_elem.get("src"):
                        image_url = img_elem["src"]
                        break

                # Avaliação
                rating = None
                for rating_selector in [
                    ".poly-reviews__rating",
                    ".ui-search-reviews__rating-number",
                    ".rating",
                ]:
                    rating_elem = container.select_one(rating_selector)
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r"(\d+[,.]?\d*)", rating_text)
                        if rating_match:
                            rating = float(rating_match.group(1).replace(",", "."))
                            break

                # Reviews count
                reviews_count = None
                for reviews_selector in [
                    ".poly-reviews__total",
                    ".ui-search-reviews__amount",
                    ".reviews-count",
                ]:
                    reviews_elem = container.select_one(reviews_selector)
                    if reviews_elem:
                        reviews_text = reviews_elem.get_text(strip=True)
                        reviews_match = re.search(
                            r"(\d+)", reviews_text.replace(".", "")
                        )
                        if reviews_match:
                            reviews_count = int(reviews_match.group(1))
                            break

                # Calcular desconto
                discount_percentage = None
                if original_price and price and original_price > price:
                    discount_percentage = (
                        (original_price - price) / original_price
                    ) * 100

                product_info = ProductInfo(
                    name=title,
                    price=price,
                    original_price=original_price,
                    discount_percentage=discount_percentage,
                    availability="available",
                    url=product_url,
                    site=self.config.name,
                    image_url=image_url,
                    rating=rating,
                    reviews_count=reviews_count,
                )

                products.append(product_info)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Mercado Livre: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos do Mercado Livre")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço"""
        if not price_text:
            return None

        # Remove caracteres não numéricos exceto vírgulas e pontos
        cleaned = re.sub(r"[^\d,.]", "", price_text)

        # Converte vírgula para ponto (padrão brasileiro)
        if "," in cleaned and "." in cleaned:
            # Formato: 1.234,56 -> remove pontos de milhar, converte vírgula para ponto
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            # Formato: 1234,56 -> converte vírgula para ponto
            cleaned = cleaned.replace(",", ".")
        # Se só tem ponto, pode ser separador decimal ou milhar
        elif "." in cleaned:
            # Se tem mais de 3 dígitos após o ponto, é separador de milhar
            parts = cleaned.split(".")
            if len(parts) == 2 and len(parts[1]) > 2:
                # É separador de milhar, remove o ponto
                cleaned = cleaned.replace(".", "")
            # Senão, assume que é separador decimal

        try:
            return float(cleaned)
        except ValueError:
            return None
