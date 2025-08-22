from typing import List, Optional
import urllib.parse
import re
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from ..models import ProductInfo, SiteConfig


class AmazonBRScraper(BaseScraper):

    def __init__(self):
        config = SiteConfig(
            name="Amazon BR",
            base_url="https://www.amazon.com.br",
            search_url_pattern="https://www.amazon.com.br/s?k={query}&ref=nb_sb_noss",
            selectors={
                "product_container": "[data-component-type='s-search-result'], .s-result-item",
                "title": "h2 a span, .a-size-mini span, .a-size-base-plus",
                "price": ".a-price-whole, .a-price .a-offscreen, .a-price-range",
                "original_price": ".a-price.a-text-price .a-offscreen",
                "link": "h2 a, .a-link-normal",
                "image": ".s-image, .a-dynamic-image",
                "rating": ".a-icon-alt, .a-star-4-5",
                "reviews": ".a-size-base, .a-link-normal",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
            rate_limit_delay=2.0,
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """Constrói URL de busca da Amazon BR"""
        encoded_query = urllib.parse.quote_plus(product_name)
        return self.config.search_url_pattern.format(query=encoded_query)

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos do HTML da Amazon"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Tenta vários seletores possíveis
        product_containers = soup.select(self.config.selectors["product_container"])
        if not product_containers:
            # Seletores alternativos
            product_containers = soup.select(".s-result-item")
            if not product_containers:
                product_containers = soup.select(".s-search-result")

        logger.info(f"Encontrados {len(product_containers)} produtos na Amazon")

        for container in product_containers:
            try:
                # Título - múltiplas tentativas
                title = None
                for title_selector in [
                    "h2 a span",
                    ".a-size-mini span",
                    ".a-size-base-plus",
                    "h2 span",
                    ".s-size-mini",
                ]:
                    title_element = container.select_one(title_selector)
                    if title_element and title_element.get_text(strip=True):
                        title = title_element.get_text(strip=True)
                        break

                if not title:
                    continue

                # Link - múltiplas tentativas
                product_url = None
                for link_selector in ["h2 a", ".a-link-normal", "a[href*='/dp/']"]:
                    link_element = container.select_one(link_selector)
                    if link_element and link_element.get("href"):
                        product_url = link_element["href"]
                        break

                if not product_url:
                    continue

                if product_url.startswith("/"):
                    product_url = f"https://www.amazon.com.br{product_url}"

                # Preço - múltiplas tentativas
                price = None
                for price_selector in [
                    ".a-price-whole",
                    ".a-price .a-offscreen",
                    ".a-price-range",
                    ".a-price",
                ]:
                    price_element = container.select_one(price_selector)
                    if price_element:
                        price_text = price_element.get_text(strip=True)
                        price = self._extract_price(price_text)
                        if price:
                            break

                # Se não encontrou preço, pula
                if not price:
                    continue

                # Preço original (se houver desconto)
                original_price = None
                original_price_elem = container.select_one(
                    self.config.selectors["original_price"]
                )
                if original_price_elem:
                    original_price = self._extract_price(
                        original_price_elem.get_text(strip=True)
                    )

                # Imagem
                image_url = None
                image_elem = container.select_one(self.config.selectors["image"])
                if image_elem and image_elem.get("src"):
                    image_url = image_elem["src"]

                # Avaliação
                rating = None
                rating_elem = container.select_one(self.config.selectors["rating"])
                if rating_elem:
                    rating_text = rating_elem.get("alt") or rating_elem.get_text(
                        strip=True
                    )
                    if rating_text:
                        # Extrai número da avaliação
                        rating_match = re.search(r"(\d+[,.]?\d*)", rating_text)
                        if rating_match:
                            rating = float(rating_match.group(1).replace(",", "."))

                # Informações de entrega
                delivery_info = self._extract_delivery_info(container)

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
                    delivery_info=delivery_info,
                )

                products.append(product_info)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Amazon: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos da Amazon")
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

    def _extract_delivery_info(self, container) -> Optional[str]:
        """Extrai informações de prazo de entrega do container do produto"""
        delivery_selectors = [
            # Seletores comuns para informações de entrega na Amazon
            "[aria-label*='Entrega']",
            "[aria-label*='Receba']",
            ".a-text-bold:contains('Receba')",
            ".a-size-base:contains('Receba')",
            ".a-size-small:contains('Receba')",
            "[data-cy*='delivery']",
            ".s-shipping-message",
            ".a-row .a-size-base:contains('Entrega')",
            ".a-row .a-size-base:contains('Prime')",
            "[class*='delivery']",
            "[class*='shipping']",
        ]

        for selector in delivery_selectors:
            try:
                # Para seletores com :contains, usa uma abordagem diferente
                if ":contains(" in selector:
                    base_selector = selector.split(":contains(")[0]
                    search_text = selector.split("':contains('")[1].rstrip("')")
                    elements = container.select(base_selector)
                    for elem in elements:
                        text = elem.get_text(strip=True)
                        if search_text.lower() in text.lower():
                            delivery_text = self._clean_delivery_text(text)
                            if delivery_text:
                                return delivery_text
                else:
                    elem = container.select_one(selector)
                    if elem:
                        delivery_text = self._clean_delivery_text(
                            elem.get_text(strip=True)
                        )
                        if delivery_text:
                            return delivery_text
            except Exception:
                continue

        # Fallback: procura por texto que contenha palavras-chave de entrega
        all_text_elements = container.find_all(text=True)
        for text in all_text_elements:
            text_str = str(text).strip()
            if any(
                keyword in text_str.lower()
                for keyword in ["receba", "entrega", "prime", "grátis", "frete"]
            ):
                if (
                    len(text_str) > 5 and len(text_str) < 100
                ):  # Filtrar textos muito curtos ou longos
                    delivery_text = self._clean_delivery_text(text_str)
                    if delivery_text:
                        return delivery_text

        return None

    def _clean_delivery_text(self, text: str) -> Optional[str]:
        """Limpa e normaliza o texto de informações de entrega"""
        if not text or len(text.strip()) < 5:
            return None

        text = text.strip()

        # Padrões de texto de entrega válidos
        delivery_patterns = [
            r"receba.*?(segunda|terça|quarta|quinta|sexta|sábado|domingo)",
            r"receba.*?\d{1,2}\s+de\s+\w+",
            r"entrega.*?(grátis|gratuita)",
            r"prime.*?(grátis|gratuita|amanhã)",
            r"frete.*?(grátis|gratuito)",
            r"entrega.*?\d+.*?dias?",
            r"receba.*?até.*?\d+",
        ]

        text_lower = text.lower()
        for pattern in delivery_patterns:
            if re.search(pattern, text_lower):
                # Limita o tamanho do texto retornado
                if len(text) <= 80:
                    return text
                else:
                    # Se for muito longo, tenta extrair apenas a parte relevante
                    match = re.search(pattern, text_lower)
                    if match:
                        start_pos = max(0, match.start() - 10)
                        end_pos = min(len(text), match.end() + 10)
                        return text[start_pos:end_pos].strip()

        return None
