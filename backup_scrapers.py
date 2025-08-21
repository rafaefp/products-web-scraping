import re
import urllib.parse
import requests
from typing import List, Optional
from bs4 import BeautifulSoup
from loguru import logger
from selenium import webdriver

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
        """ConstrÃ³i URL de busca da Amazon BR"""
        encoded_query = urllib.parse.quote_plus(product_name)
        return self.config.search_url_pattern.format(query=encoded_query)

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informaÃ§Ãµes dos produtos do HTML da Amazon"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Tenta vÃ¡rios seletores possÃ­veis
        product_containers = soup.select(self.config.selectors["product_container"])
        if not product_containers:
            # Seletores alternativos
            product_containers = soup.select(".s-result-item")
            if not product_containers:
                product_containers = soup.select(".s-search-result")

        logger.info(f"Encontrados {len(product_containers)} produtos na Amazon")

        for container in product_containers:
            try:
                # TÃ­tulo - mÃºltiplas tentativas
                title = None
                for title_selector in [
                    "h2 a span",
                    ".a-size-mini span",
                    ".a-size-base-plus",
                    "h2 span",
                    ".s-size-mini",
                ]:
                    title_elem = container.select_one(title_selector)
                    if title_elem and title_elem.get_text(strip=True):
                        title = title_elem.get_text(strip=True)
                        break

                if not title:
                    continue

                # Link - mÃºltiplas tentativas
                product_url = None
                for link_selector in ["h2 a", ".a-link-normal", "a[href*='/dp/']"]:
                    link_elem = container.select_one(link_selector)
                    if link_elem and link_elem.get("href"):
                        product_url = link_elem["href"]
                        break

                if not product_url:
                    continue

                if product_url.startswith("/"):
                    product_url = self.config.base_url + product_url

                # PreÃ§o - mÃºltiplas tentativas
                price = None
                for price_selector in [
                    ".a-price-whole",
                    ".a-price .a-offscreen",
                    ".a-price-range",
                    ".a-price",
                ]:
                    price_elem = container.select_one(price_selector)
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        price = self._extract_price(price_text)
                        if price:
                            break

                # Se nÃ£o encontrou preÃ§o, pula
                if not price:
                    continue

                # PreÃ§o original (se houver desconto)
                original_price = None
                original_price_elem = container.select_one(
                    self.config.selectors["original_price"]
                )
                if original_price_elem:
                    original_price_text = original_price_elem.get_text(strip=True)
                    original_price = self._extract_price(original_price_text)

                # Imagem
                image_url = None
                image_elem = container.select_one(self.config.selectors["image"])
                if image_elem and image_elem.get("src"):
                    image_url = image_elem["src"]

                # AvaliaÃ§Ã£o
                rating = None
                rating_elem = container.select_one(self.config.selectors["rating"])
                if rating_elem:
                    rating_text = rating_elem.get_text(strip=True)
                    rating_match = re.search(r"(\d+,\d+|\d+)", rating_text)
                    if rating_match:
                        rating = float(rating_match.group(1).replace(",", "."))

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
                )

                products.append(product_info)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Amazon: {str(e)}")
                continue

        logger.info(f"ExtraÃ­dos {len(products)} produtos vÃ¡lidos da Amazon")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numÃ©rico do texto de preÃ§o"""
        if not price_text:
            return None

        # Remove caracteres nÃ£o numÃ©ricos exceto vÃ­rgulas e pontos
        cleaned = re.sub(r"[^\d,.]", "", price_text)

        # Converte vÃ­rgula para ponto (padrÃ£o brasileiro)
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


class MercadoLivreScraper(BaseScraper):
    """Scraper especÃ­fico para Mercado Livre"""

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
        """ConstrÃ³i URL de busca do Mercado Livre"""
        # Usa formato padrÃ£o de busca do ML
        encoded_query = urllib.parse.quote_plus(product_name)
        return f"https://lista.mercadolivre.com.br/{encoded_query}"

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informaÃ§Ãµes dos produtos do HTML do Mercado Livre"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Usando seletores baseados na estrutura HTML real
        product_containers = soup.select(".ui-search-result__wrapper")
        logger.info(f"Encontrados {len(product_containers)} produtos no Mercado Livre")

        for container in product_containers:
            try:
                # TÃ­tulo - primeiro tenta pela imagem title, depois por outros seletores
                title = None
                img_elem = container.select_one("img[title]")
                if img_elem and img_elem.get("title"):
                    title = img_elem.get("title").strip()

                # Fallback para outros seletores
                if not title:
                    for title_selector in [
                        "h2.ui-search-item__title",
                        ".ui-search-item__title",
                        "h2.poly-component__title",
                        ".poly-component__title",
                        "h2[data-testid='item-title']",
                        "[data-testid='item-title']",
                        "h2",
                        ".item-title",
                    ]:
                        title_elem = container.select_one(title_selector)
                        if title_elem and title_elem.get_text(strip=True):
                            title = title_elem.get_text(strip=True)
                            break

                if not title:
                    continue

                # Link - mÃºltiplas tentativas
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
                        if not product_url.startswith("http"):
                            product_url = (
                                f"https://www.mercadolivre.com.br{product_url}"
                            )
                        break

                if not product_url:
                    continue

                # PreÃ§o - usando seletores baseados na estrutura real
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
                        # Melhor processamento do preÃ§o baseado na estrutura do ML
                        try:
                            # Remove pontos de milhares e converte vÃ­rgula para ponto decimal
                            # Ex: "1.799" -> "1799", "192,35" -> "192.35"
                            price_clean = price_text.replace(
                                ".", ""
                            )  # Remove pontos de milhares
                            if "," in price_clean:
                                price_clean = price_clean.replace(
                                    ",", "."
                                )  # Converte vÃ­rgula para ponto
                            price = float(price_clean)
                            break
                        except ValueError:
                            # Tenta extrair apenas nÃºmeros
                            numbers = re.findall(r"\d+", price_text)
                            if numbers:
                                price_clean = "".join(numbers)
                                try:
                                    price = float(price_clean)
                                    # Se for um nÃºmero muito grande, assume que sÃ£o centavos
                                    if price > 100000:
                                        price = price / 100
                                    break
                                except ValueError:
                                    continue

                # Se nÃ£o encontrou preÃ§o, pula
                if not price:
                    continue

                # PreÃ§o original (com melhor seletor)
                original_price = None
                for original_price_selector in [
                    ".andes-money-amount--previous .andes-money-amount__fraction",
                    "s .andes-money-amount__fraction",
                    ".poly-component__price s .andes-money-amount__fraction",
                ]:
                    original_price_elem = container.select_one(original_price_selector)
                    if original_price_elem:
                        original_price_text = original_price_elem.get_text(strip=True)
                        try:
                            original_price_clean = original_price_text.replace(".", "")
                            if "," in original_price_clean:
                                original_price_clean = original_price_clean.replace(
                                    ",", "."
                                )
                            original_price = float(original_price_clean)
                            break
                        except ValueError:
                            pass

                # Imagem
                image_url = None
                for img_selector in [
                    "img[src*='mlstatic.com']",
                    ".ui-search-result-image__element",
                    ".poly-component__picture",
                    "img[data-src]",
                    "img",
                ]:
                    image_elem = container.select_one(img_selector)
                    if image_elem and (
                        image_elem.get("src") or image_elem.get("data-src")
                    ):
                        img_url = image_elem.get("src") or image_elem.get("data-src")
                        # Filtra apenas URLs vÃ¡lidas (nÃ£o data:image)
                        if (
                            img_url
                            and (img_url.startswith("http") or img_url.startswith("//"))
                            and "data:image" not in img_url
                        ):
                            image_url = img_url
                            break

                # AvaliaÃ§Ã£o
                rating = None
                for rating_selector in [
                    ".poly-reviews__rating",
                    ".ui-search-reviews__rating-number",
                    ".rating",
                ]:
                    rating_elem = container.select_one(rating_selector)
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        try:
                            rating = float(rating_text.replace(",", "."))
                            break
                        except ValueError:
                            pass

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
                        # Extrai nÃºmeros entre parÃªnteses ou diretamente
                        reviews_match = re.search(
                            r"\((\d+)\)|(\d+)", reviews_text.replace(".", "")
                        )
                        if reviews_match:
                            reviews_count = int(
                                reviews_match.group(1) or reviews_match.group(2)
                            )
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

        logger.info(f"ExtraÃ­dos {len(products)} produtos vÃ¡lidos do Mercado Livre")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numÃ©rico do texto de preÃ§o"""
        if not price_text:
            return None

        # Remove caracteres nÃ£o numÃ©ricos exceto vÃ­rgulas e pontos
        cleaned = re.sub(r"[^\d,.]", "", price_text)

        # Converte vÃ­rgula para ponto (padrÃ£o brasileiro)
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


class AmericanasScraper(BaseScraper):
    """Scraper especÃ­fico para Americanas.com"""

    def __init__(self):
        config = SiteConfig(
            name="Americanas",
            base_url="https://www.americanas.com.br",
            search_url_pattern="https://www.americanas.com.br/busca/{query}",
            selectors={
                "product_container": "[data-testid='product-card'], .product-card, .product-item, .search-product-card, article",
                "title": "[data-testid='product-name'], .product-name, .product-title, h2 a, h3 a",
                "price": "[data-testid='price-value'], .price-value, .price, .sales-price, .current-price",
                "original_price": "[data-testid='old-price'], .old-price, .list-price, .crossed-out-price",
                "link": "a[href*='/produto/'], .product-link, a[data-testid='product-card-link']",
                "image": "[data-testid='product-image'] img, .product-image img, .product-card img",
                "rating": "[data-testid='rating'], .rating, .stars",
                "reviews": "[data-testid='reviews-count'], .reviews-count, .reviews",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
            rate_limit_delay=3.0,  # Increased delay for Americanas
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """ConstrÃ³i URL de busca do Americanas"""
        # Usa formato padrÃ£o de busca do Americanas
        encoded_query = urllib.parse.quote_plus(product_name)
        return f"https://www.americanas.com.br/busca/{encoded_query}"

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informaÃ§Ãµes dos produtos do HTML do Americanas"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Usando seletores baseados na estrutura do Americanas
        product_containers = soup.select(self.config.selectors["product_container"])

        # Fallbacks para diferentes layouts
        if not product_containers:
            product_containers = soup.select("article, .card, .item")

        if not product_containers:
            # Tenta seletores mais genÃ©ricos
            product_containers = soup.select(
                "[data-testid*='product'], [class*='product']"
            )

        logger.info(f"Encontrados {len(product_containers)} produtos no Americanas")

        for container in product_containers:
            try:
                # TÃ­tulo - mÃºltiplas tentativas
                title = None
                for title_selector in [
                    "[data-testid='product-name']",
                    ".product-name",
                    ".product-title",
                    "h2 a",
                    "h3 a",
                    "h2",
                    "h3",
                    ".title",
                    "a[title]",
                ]:
                    title_elem = container.select_one(title_selector)
                    if title_elem:
                        title_text = (
                            title_elem.get_text(strip=True)
                            or title_elem.get("title", "").strip()
                        )
                        if title_text:
                            title = title_text
                            break

                if not title:
                    continue

                # Link - mÃºltiplas tentativas
                product_url = None
                for link_selector in [
                    "a[href*='/produto/']",
                    "[data-testid='product-card-link']",
                    ".product-link",
                    "a[href*='americanas.com.br']",
                    "a[href]",
                ]:
                    link_elem = container.select_one(link_selector)
                    if link_elem and link_elem.get("href"):
                        href = link_elem["href"]
                        if href.startswith("/"):
                            product_url = f"https://www.americanas.com.br{href}"
                        elif href.startswith("http"):
                            product_url = href
                        if product_url:
                            break

                if not product_url:
                    continue

                # PreÃ§o - mÃºltiplas tentativas
                price = None
                for price_selector in [
                    "[data-testid='price-value']",
                    ".price-value",
                    ".sales-price",
                    ".current-price",
                    ".price",
                    "[class*='price']",
                ]:
                    price_elem = container.select_one(price_selector)
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        # Melhor processamento do preÃ§o brasileiro
                        try:
                            # Remove "R$" e outros caracteres
                            price_clean = re.sub(r"[^\d,.]", "", price_text)
                            if "," in price_clean and "." in price_clean:
                                # Formato: R$ 1.234,56
                                price_clean = price_clean.replace(".", "").replace(
                                    ",", "."
                                )
                            elif "," in price_clean:
                                # Formato: R$ 1234,56
                                price_clean = price_clean.replace(",", ".")

                            price = float(price_clean)
                            if price > 0:
                                break
                        except (ValueError, TypeError):
                            pass

                # Se nÃ£o encontrou preÃ§o, pula
                if not price:
                    continue

                # PreÃ§o original
                original_price = None
                for original_price_selector in [
                    "[data-testid='old-price']",
                    ".old-price",
                    ".list-price",
                    ".crossed-out-price",
                    "s",
                    ".strike",
                ]:
                    original_price_elem = container.select_one(original_price_selector)
                    if original_price_elem:
                        original_price_text = original_price_elem.get_text(strip=True)
                        try:
                            original_price_clean = re.sub(
                                r"[^\d,.]", "", original_price_text
                            )
                            if (
                                "," in original_price_clean
                                and "." in original_price_clean
                            ):
                                original_price_clean = original_price_clean.replace(
                                    ".", ""
                                ).replace(",", ".")
                            elif "," in original_price_clean:
                                original_price_clean = original_price_clean.replace(
                                    ",", "."
                                )

                            original_price = float(original_price_clean)
                            if original_price > 0:
                                break
                        except (ValueError, TypeError):
                            pass

                # Imagem
                image_url = None
                for img_selector in [
                    "[data-testid='product-image'] img",
                    ".product-image img",
                    ".product-card img",
                    "img[src*='americanas']",
                    "img[data-src]",
                    "img",
                ]:
                    image_elem = container.select_one(img_selector)
                    if image_elem:
                        img_url = image_elem.get("src") or image_elem.get("data-src")
                        # Filtra apenas URLs vÃ¡lidas
                        if (
                            img_url
                            and (img_url.startswith("http") or img_url.startswith("//"))
                            and "data:image" not in img_url
                        ):
                            if img_url.startswith("//"):
                                img_url = f"https:{img_url}"
                            image_url = img_url
                            break

                # AvaliaÃ§Ã£o
                rating = None
                for rating_selector in [
                    "[data-testid='rating']",
                    ".rating",
                    ".stars",
                    ".star-rating",
                ]:
                    rating_elem = container.select_one(rating_selector)
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r"(\d+[,.]\d+|\d+)", rating_text)
                        if rating_match:
                            try:
                                rating = float(rating_match.group(1).replace(",", "."))
                                break
                            except (ValueError, TypeError):
                                pass

                # Reviews count
                reviews_count = None
                for reviews_selector in [
                    "[data-testid='reviews-count']",
                    ".reviews-count",
                    ".reviews",
                    "[class*='review']",
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
                logger.warning(f"Erro ao processar produto Americanas: {str(e)}")
                continue

        logger.info(f"ExtraÃ­dos {len(products)} produtos vÃ¡lidos do Americanas")
        return products


class MagazineLuizaScraper(BaseScraper):
    """Scraper especÃ­fico para Magazine Luiza"""

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
        """ConstrÃ³i URL de busca do Magazine Luiza"""
        # Remove caracteres especiais e substitui espaÃ§os por +
        encoded_query = urllib.parse.quote_plus(product_name)
        return f"https://www.magazineluiza.com.br/busca/{encoded_query}/"

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informaÃ§Ãµes dos produtos do HTML do Magazine Luiza"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Magazine Luiza usa renderizaÃ§Ã£o JavaScript - precisamos aguardar elementos carregarem
        # Vamos usar seletores mais robustos baseados na estrutura atual
        product_containers = []

        # Tentativa 1: Seletores especÃ­ficos do Magazine Luiza
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
            "li",  # Elementos genÃ©ricos como fallback
            "article",
            "div[class*='sc-']",  # Styled components genÃ©ricos
        ]

        for selector in selectors_to_try:
            containers = soup.select(selector)
            if containers:
                # Filtra apenas containers que parecem ter produtos
                for container in containers:
                    # Verifica se tem indicadores de produto (preÃ§o, tÃ­tulo, link)
                    has_price = bool(
                        container.select(
                            '[class*="price"], [class*="valor"], [data-testid*="price"]'
                        )
                    )
                    has_title = bool(
                        container.select(
                            'h1, h2, h3, h4, h5, h6, [class*="title"], [class*="nome"]'
                        )
                    )
                    has_link = bool(container.select("a[href]"))

                    if has_price or (has_title and has_link):
                        product_containers.append(container)

                if product_containers:
                    logger.info(f"Encontrados produtos com seletor: {selector}")
                    break

        logger.info(f"Encontrados {len(product_containers)} produtos no Magazine Luiza")

        # Para evitar duplicatas
        seen_urls = set()

        for container in product_containers:
            try:
                # TÃ­tulo - mÃºltiplas tentativas com estratÃ©gia mais ampla
                title = None
                title_selectors = [
                    "[data-testid*='title']",
                    "[data-testid*='nome']",
                    "[data-testid*='product']",
                    "h1, h2, h3, h4, h5, h6",
                    "a[title]",
                    "[class*='title']",
                    "[class*='nome']",
                    "[class*='product-name']",
                    "a[href*='/p/']",
                    "a[href*='produto']",
                    "a",  # Link genÃ©rico como Ãºltimo recurso
                ]

                for title_selector in title_selectors:
                    title_elems = container.select(title_selector)
                    for title_elem in title_elems:
                        title_text = (
                            title_elem.get_text(strip=True)
                            or title_elem.get("title", "").strip()
                        )
                        # Valida se parece um tÃ­tulo de produto - critÃ©rios mais flexÃ­veis
                        if (
                            title_text
                            and len(title_text) > 5  # Reduzido de 10 para 5
                            and not any(
                                skip_word in title_text.lower()
                                for skip_word in [
                                    "ver mais",
                                    "comprar",
                                    "adicionar",
                                    "buscar",
                                    "menu",
                                    "filtro",
                                ]
                            )
                        ):
                            title = title_text
                            break
                    if title:
                        break

                if not title or len(title.strip()) < 3:  # Reduzido de 5 para 3
                    logger.info(
                        f"Produto pulado: tÃ­tulo muito curto ou vazio. TÃ­tulo: '{title}'"
                    )
                    continue

                # Link - estratÃ©gia mais ampla e flexÃ­vel
                product_url = None
                link_selectors = [
                    "a[href*='/p/']",  # Links especÃ­ficos de produto
                    "a[href*='produto']",
                    "a[href*='magazineluiza.com.br']",
                    "a[href^='/']",  # Links relativos
                    "a[href^='http']",  # Links absolutos
                    "a[href]",  # Qualquer link
                    "a",  # Qualquer Ã¢ncora (mesmo sem href visÃ­vel)
                ]

                for link_selector in link_selectors:
                    link_elem = container.select_one(link_selector)
                    if link_elem:
                        # Tenta mÃºltiplos atributos onde pode estar a URL
                        href = (
                            link_elem.get("href")
                            or link_elem.get("data-href")
                            or link_elem.get("data-url")
                            or link_elem.get("data-link")
                        )

                        if href:
                            # Normaliza a URL
                            if href.startswith("/"):
                                product_url = f"https://www.magazineluiza.com.br{href}"
                            elif href.startswith("http"):
                                product_url = href
                            else:
                                # Tenta como URL relativa mesmo sem /
                                product_url = f"https://www.magazineluiza.com.br/{href}"

                            # ValidaÃ§Ã£o mais permissiva - aceita qualquer URL do Magazine Luiza
                            if product_url and (
                                "magazineluiza.com.br" in product_url
                                or "/p/" in product_url
                                or "produto" in product_url
                                or len(href) > 5  # Muito mais permissivo
                            ):
                                break

                    # Se nÃ£o encontrou href, mas tem link, tenta construir URL baseada no tÃ­tulo
                    if not product_url and link_elem:
                        # Como Ãºltimo recurso, constrÃ³i URL de busca baseada no tÃ­tulo
                        if title and len(title) > 10:
                            import urllib.parse

                            encoded_title = urllib.parse.quote_plus(
                                title[:50]
                            )  # Limita tamanho
                            product_url = f"https://www.magazineluiza.com.br/busca/{encoded_title}/"
                            break

                # Se nÃ£o encontrou URL vÃ¡lida ou jÃ¡ foi vista, pula
                if not product_url:
                    # logger.info(f"Produto pulado: URL nÃ£o encontrada. TÃ­tulo: {title[:50] if title else 'N/A'}")
                    continue

                if product_url in seen_urls:
                    # logger.info(f"Produto pulado: URL duplicada. TÃ­tulo: {title[:50] if title else 'N/A'}")
                    continue

                # Adiciona URL ao conjunto de URLs vistas
                seen_urls.add(product_url)

                # PreÃ§o - estratÃ©gia mais ampla com regex
                price = None
                price_selectors = [
                    "[data-testid*='price']",
                    "[data-testid*='valor']",
                    "[class*='price']",
                    "[class*='valor']",
                    "[class*='preco']",
                    "span",
                    "div",
                    "p",  # Elementos genÃ©ricos
                ]

                for price_selector in price_selectors:
                    price_elems = container.select(price_selector)
                    for price_elem in price_elems:
                        price_text = price_elem.get_text(strip=True)
                        # Procura padrÃ£o de preÃ§o brasileiro com regex
                        import re

                        price_patterns = [
                            r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)",  # R$ 1.234,56
                            r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)",  # 1.234,56
                            r"(\d+,\d{2})",  # 1234,56
                            r"(\d+\.\d{2})",  # 1234.56
                        ]

                        for pattern in price_patterns:
                            match = re.search(pattern, price_text)
                            if match:
                                try:
                                    price_str = match.group(1)
                                    # Converte formato brasileiro para float
                                    if "," in price_str and "." in price_str:
                                        # Formato: 1.234,56
                                        price_clean = price_str.replace(
                                            ".", ""
                                        ).replace(",", ".")
                                    elif "," in price_str:
                                        # Formato: 1234,56
                                        price_clean = price_str.replace(",", ".")
                                    else:
                                        # Formato: 1234.56
                                        price_clean = price_str

                                    price = float(price_clean)
                                    if price > 1:  # PreÃ§o mÃ­nimo razoÃ¡vel
                                        break
                                except (ValueError, TypeError):
                                    continue
                        if price:
                            break
                    if price:
                        break

                # Se nÃ£o encontrou preÃ§o vÃ¡lido, pula
                if (
                    not price or price < 0.01
                ):  # Mais flexÃ­vel: permite preÃ§os a partir de R$ 0,01
                    logger.info(
                        f"Produto pulado: preÃ§o invÃ¡lido ({price}). TÃ­tulo: {title[:50] if title else 'N/A'}"
                    )
                    continue

                # Debug: log do produto vÃ¡lido encontrado
                logger.info(
                    f"âœ… Produto vÃ¡lido encontrado: {title[:50]}... - R$ {price}"
                )

                # PreÃ§o original (riscado)
                original_price = None
                for original_price_selector in [
                    "[data-testid='old-price']",
                    ".sc-jrAGrp",
                    ".old-price",
                    ".list-price",
                    ".price-line-through",
                    "s",
                    ".strike",
                ]:
                    original_price_elem = container.select_one(original_price_selector)
                    if original_price_elem:
                        original_price_text = original_price_elem.get_text(strip=True)
                        try:
                            original_price_clean = re.sub(
                                r"[^\d,.]", "", original_price_text
                            )
                            if (
                                "," in original_price_clean
                                and "." in original_price_clean
                            ):
                                original_price_clean = original_price_clean.replace(
                                    ".", ""
                                ).replace(",", ".")
                            elif "," in original_price_clean:
                                original_price_clean = original_price_clean.replace(
                                    ",", "."
                                )

                            original_price = float(original_price_clean)
                            if (
                                original_price > price
                            ):  # SÃ³ aceita se for maior que preÃ§o atual
                                break
                        except (ValueError, TypeError):
                            pass

                # Imagem do produto
                image_url = None
                for img_selector in [
                    "[data-testid='product-image'] img",
                    ".sc-dkrFOg img",
                    ".product-image img",
                    ".product-card img",
                    "img",
                ]:
                    img_elem = container.select_one(img_selector)
                    if img_elem:
                        img_src = img_elem.get("src") or img_elem.get("data-src")
                        if img_src:
                            if img_src.startswith("//"):
                                image_url = f"https:{img_src}"
                            elif img_src.startswith("/"):
                                image_url = f"https://www.magazineluiza.com.br{img_src}"
                            elif img_src.startswith("http"):
                                image_url = img_src
                            if image_url:
                                break

                # Rating (avaliaÃ§Ã£o)
                rating = None
                rating_elem = container.select_one(self.config.selectors["rating"])
                if rating_elem:
                    rating_text = rating_elem.get_text(strip=True)
                    # Procura por padrÃµes como "4.5", "4,5 estrelas", etc.
                    import re

                    rating_match = re.search(r"(\d+[,.]?\d*)", rating_text)
                    if rating_match:
                        try:
                            rating = float(rating_match.group(1).replace(",", "."))
                        except ValueError:
                            pass

                # NÃºmero de avaliaÃ§Ãµes
                reviews_count = None
                reviews_elem = container.select_one(self.config.selectors["reviews"])
                if reviews_elem:
                    reviews_text = reviews_elem.get_text(strip=True)
                    # Procura por nÃºmeros como "(123)", "123 avaliaÃ§Ãµes", etc.
                    import re

                    reviews_match = re.search(r"(\d+)", reviews_text)
                    if reviews_match:
                        try:
                            reviews_count = int(reviews_match.group(1))
                        except ValueError:
                            pass

                # Cria objeto ProductInfo
                product = ProductInfo(
                    name=title,
                    price=price,
                    original_price=original_price,
                    availability="in_stock",  # Magazine Luiza nÃ£o mostra produtos fora de estoque na busca
                    url=product_url,
                    site=self.config.name,
                    image_url=image_url,
                    rating=rating,
                    reviews_count=reviews_count,
                )

                products.append(product)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Magazine Luiza: {str(e)}")
                continue

        logger.info(f"ExtraÃ­dos {len(products)} produtos vÃ¡lidos do Magazine Luiza")
        return products


class CasasBahiaScraper(BaseScraper):
    """Scraper especÃ­fico para Casas Bahia"""

    def __init__(self):
        super().__init__(
            SiteConfig(
                name="Casas Bahia",
                base_url="https://www.casasbahia.com.br",
                search_url_pattern="https://www.casasbahia.com.br/busca?q={query}",
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
                    "Referer": "https://www.casasbahia.com.br/",  # Muito importante para parecer navegaÃ§Ã£o natural
                    "Origin": "https://www.casasbahia.com.br",
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
        )

    def build_search_url(self, product_name: str) -> str:
        """ConstrÃ³i URL de busca para Casas Bahia"""
        encoded_query = urllib.parse.quote_plus(product_name)
        return self.config.search_url_pattern.format(query=encoded_query)

    def extract_product_info(
        self, html_content: str, search_url: str
    ) -> List[ProductInfo]:
        """Extrai informaÃ§Ãµes dos produtos do HTML das Casas Bahia"""
        products = []
        seen_urls = set()

        soup = BeautifulSoup(html_content, "html.parser")

        # Casas Bahia usa estrutura similar ao Magazine Luiza
        # Vamos usar seletores mais robustos baseados na estrutura atual
        product_containers = []

        # Tentativa 1: Seletores especÃ­ficos das Casas Bahia
        selectors_to_try = [
            "[data-testid='product-card']",  # Produtos com data-testid
            "div[data-testid*='product']",
            "article[data-testid*='product']",
            ".product-card",  # Classes com product
            ".showcase-item",
            ".product-item",
            "div[class*='product']",
            "li[class*='product']",
            ".item",  # Fallback genÃ©rico
            "article",
        ]

        for selector in selectors_to_try:
            containers = soup.select(selector)
            if containers:
                logger.info(
                    f"Casas Bahia: Usando seletor '{selector}' - {len(containers)} containers"
                )
                product_containers = containers[:20]  # Limitar para evitar spam
                break

        if not product_containers:
            logger.warning("Casas Bahia: Nenhum container de produto encontrado")
            return products

        logger.info(f"Encontrados {len(product_containers)} produtos nas Casas Bahia")

        for container in product_containers:
            try:
                # Nome do produto - mÃºltiplas tentativas
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
                    # Se nÃ£o tem texto, tenta o atributo title
                    if not name and name_element.get("title"):
                        name = name_element["title"].strip()

                if not name or len(name) < 3:
                    continue

                # PreÃ§o - mÃºltiplas tentativas
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
                        url = f"https://www.casasbahia.com.br{url}"
                    elif not url.startswith("http"):
                        url = f"https://www.casasbahia.com.br/{url}"

                # Evitar duplicatas por URL
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

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
                            image_url = f"https://www.casasbahia.com.br{image_url}"

                # ValidaÃ§Ã£o final
                if name and price and len(name) >= 3:
                    product = ProductInfo(
                        name=name,
                        price=price,
                        url=url if url else search_url,
                        image_url=image_url if image_url else None,
                        site="Casas Bahia",
                        availability="DisponÃ­vel",
                    )
                    products.append(product)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Casas Bahia: {str(e)}")
                continue

        logger.info(f"ExtraÃ­dos {len(products)} produtos vÃ¡lidos das Casas Bahia")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numÃ©rico do texto de preÃ§o"""
        if not price_text:
            return None

        # Remove caracteres nÃ£o numÃ©ricos exceto vÃ­rgulas e pontos
        cleaned = re.sub(r"[^\d,.]", "", price_text)

        # Converte vÃ­rgula para ponto (padrÃ£o brasileiro)
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


class PontoFrioScraper(BaseScraper):
    """Scraper específico para Ponto Frio"""

    def __init__(self):
        super().__init__(
            SiteConfig(
                name="Ponto Frio",
                base_url="https://www.pontofrio.com.br",
                search_url_pattern="https://www.pontofrio.com.br/busca?q={query}",
                selectors={
                    "product_container": "[data-testid='product-card'], .product-card, .showcase-item, .product-item, .item",
                    "product_name": "h2, h3, .product-title, [data-testid='product-title'], .item-title",
                    "product_price": ".price-current, .sales-price, .price, [data-testid='price-value'], .valor",
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
                    "Referer": "https://www.pontofrio.com.br/",
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
                rate_limit_delay=2.5,
                max_retries=3,
            )
        )

    def build_search_url(self, product_name: str) -> str:
        """Constrói URL de busca para Ponto Frio"""
        encoded_query = urllib.parse.quote_plus(product_name)
        return self.config.search_url_pattern.format(query=encoded_query)

    def extract_product_info(
        self, html_content: str, search_url: str
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos do HTML do Ponto Frio"""
        products = []
        seen_urls = set()

        soup = BeautifulSoup(html_content, "html.parser")

        # Primeiro, tenta extrair produtos do JSON embutido
        json_products = self._extract_json_products(soup)
        if json_products:
            logger.info(
                f"Extraídos {len(json_products)} produtos do JSON do Ponto Frio"
            )
            return json_products

        # Se não conseguir extrair do JSON, usa método tradicional com HTML
        product_containers = []

        # Tentativa 1: Seletores específicos do Ponto Frio
        selectors_to_try = [
            "[data-testid='product-card']",  # Produtos com data-testid
            "div[data-testid*='product']",
            "article[data-testid*='product']",
            ".product-card",  # Classes com product
            ".showcase-item",
            ".product-item",
            ".item",
            "div[class*='product']",
            "li[class*='product']",
            "div[class*='item']",
            "li[class*='item']",
            "article",  # Fallback genérico
        ]

        for selector in selectors_to_try:
            containers = soup.select(selector)
            if containers:
                logger.info(
                    f"Ponto Frio: Usando seletor '{selector}' - {len(containers)} containers"
                )
                product_containers = containers[:20]  # Limitar para evitar spam
                break

        if not product_containers:
            logger.warning("Ponto Frio: Nenhum container de produto encontrado")
            return products

        logger.info(f"Encontrados {len(product_containers)} produtos no Ponto Frio")

        for container in product_containers:
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
                    ".item-title",
                    ".item-name",
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

                # Validação final
                if name and price and len(name) >= 3:
                    product = ProductInfo(
                        name=name,
                        price=price,
                        url=url if url else search_url,
                        image_url=image_url if image_url else None,
                        site="Ponto Frio",
                        availability="Disponível",
                    )
                    products.append(product)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Ponto Frio: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos do Ponto Frio")
        return products

    def _extract_json_products(self, soup):
        """Extrai produtos do JSON embutido no HTML do Ponto Frio"""
        try:
            import json
            import re

            # Procura por scripts que contenham dados de produtos
            script_tags = soup.find_all(
                "script", text=lambda text: text and '"products"' in text
            )

            for script in script_tags:
                script_content = script.get_text()

                # Procura por padrões de JSON que contenham produtos
                # O JSON está embutido no script de inicialização da página
                json_matches = re.findall(
                    r'"products":\s*\[(.*?)\]', script_content, re.DOTALL
                )

                for match in json_matches:
                    try:
                        # Reconstrói o array de produtos
                        products_json = "[" + match + "]"
                        products_data = json.loads(products_json)

                        products = []
                        for product in products_data:
                            if isinstance(product, dict) and "title" in product:
                                name = product.get("title", "Nome não encontrado")

                                # Busca preço no produto ou usa placeholder
                                price = None

                                # Procura por campos de preço no objeto JSON
                                price_fields = [
                                    "price",
                                    "preco",
                                    "valor",
                                    "valorFinal",
                                    "oferta",
                                ]
                                for field in price_fields:
                                    if field in product and product[field]:
                                        price = self._extract_price(str(product[field]))
                                        if price:
                                            break

                                if not price:
                                    price = (
                                        0.0  # Placeholder quando não encontrar preço
                                    )

                                # URL do produto
                                url = ""
                                if "href" in product:
                                    url = product["href"]
                                    if url and not url.startswith("http"):
                                        url = f"https://www.pontofrio.com.br{url}"

                                # Imagem do produto
                                image_url = ""
                                if "image" in product:
                                    image_url = product["image"]

                                product_info = ProductInfo(
                                    name=name,
                                    price=price,
                                    url=url or "https://www.pontofrio.com.br",
                                    image_url=image_url or None,
                                    site="Ponto Frio",
                                    availability="Disponível",
                                )
                                products.append(product_info)

                        if products:
                            logger.info(
                                f"Extraídos {len(products)} produtos do JSON estruturado do Ponto Frio"
                            )
                            return products

                    except json.JSONDecodeError as e:
                        logger.debug(f"Erro ao decodificar JSON: {e}")
                        continue

            # Se não encontrar JSON estruturado, procura por dados individuais no HTML
            text_content = str(soup)

            # Regex melhorado para capturar id, título, URL e SKU simultaneamente
            product_pattern = r'"id":"(\d+)","title":"([^"]*iPhone[^"]*)".*?"href":"([^"]*)".*?"idSku":(\d+)'
            matches = re.findall(product_pattern, text_content, re.DOTALL)

            if matches:
                products = []
                for match in matches[:10]:  # Limita a 10 produtos
                    product_id, title, url, sku = match

                    # Tenta buscar preço usando múltiplas estratégias
                    price = self._get_price_from_sku(sku)
                    if not price:
                        # Busca preço no contexto próximo ao produto
                        price = self._extract_price_from_html_context(
                            text_content, product_id, sku
                        )
                    price = price or 0.0

                    # Garante URL completa
                    if url and not url.startswith("http"):
                        url = f"https://www.pontofrio.com.br{url}"

                    product_info = ProductInfo(
                        name=title,
                        price=price,
                        url=url or "https://www.pontofrio.com.br",
                        image_url=None,
                        site="Ponto Frio",
                        availability="Disponível" if price > 0 else "Consulte o site",
                    )
                    products.append(product_info)

                logger.info(
                    f"Extraídos {len(products)} produtos por regex avançado do Ponto Frio"
                )
                return products

            # Fallback: procura apenas por títulos (método antigo)
            title_matches = re.findall(r'"title":"([^"]*iPhone[^"]*)"', text_content)

            if title_matches:
                products = []
                for title in title_matches[:10]:  # Limita a 10 produtos
                    product_info = ProductInfo(
                        name=title,
                        price=0.0,  # Placeholder quando não conseguir extrair preço
                        url="https://www.pontofrio.com.br",
                        image_url=None,
                        site="Ponto Frio",
                        availability="Consulte o site",
                    )
                    products.append(product_info)

                logger.info(
                    f"Extraídos {len(products)} produtos por regex simples do Ponto Frio"
                )
                return products

            return []

        except Exception as e:
            logger.error(f"Erro ao extrair produtos do JSON: {e}")
            return []

    def _get_price_from_sku(self, sku):
        """Tenta buscar o preço do produto usando o SKU via múltiplas estratégias"""
        try:
            # Estratégia 1: API oficial descoberta no HTML
            api_endpoint = "https://api.pontofrio.com.br/merchandising/oferta/v1/Preco"
            api_path = "/Produto/PrecoVenda/"
            api_key = "d081fef8c2c44645bb082712ed32a047"

            # Headers mais completos baseados no que o site usa
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.pontofrio.com.br/",
                "Origin": "https://www.pontofrio.com.br",
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            }

            # Tenta múltiplas URLs da API
            api_urls = [
                f"{api_endpoint}{api_path}{sku}",
                f"{api_endpoint}/Produto/PrecoVenda/{sku}",
                f"https://api.pontofrio.com.br/merchandising/oferta/v1/Preco/Produto/PrecoVenda/{sku}",
            ]

            for api_url in api_urls:
                try:
                    logger.debug(f"Tentando API de preços: {api_url}")
                    response = requests.get(api_url, headers=headers, timeout=10)
                    logger.debug(f"Status da API: {response.status_code}")

                    if response.status_code == 200:
                        try:
                            data = response.json()
                            logger.debug(f"Resposta da API: {data}")

                            # Lista expandida de campos de preço
                            price_fields = [
                                "preco",
                                "valor",
                                "price",
                                "precoVenda",
                                "valorFinal",
                                "sellingPrice",
                                "finalPrice",
                                "originalPrice",
                                "amount",
                                "unitPrice",
                                "salePrice",
                                "listPrice",
                                "precoOferta",
                            ]

                            # Busca direta nos campos
                            if isinstance(data, dict):
                                for field in price_fields:
                                    if field in data and data[field] is not None:
                                        price = self._extract_price(str(data[field]))
                                        if price:
                                            logger.debug(
                                                f"Preço encontrado via API campo '{field}': R$ {price:.2f}"
                                            )
                                            return price

                                # Busca em objetos aninhados
                                for key, value in data.items():
                                    if isinstance(value, dict):
                                        for price_field in price_fields:
                                            if (
                                                price_field in value
                                                and value[price_field] is not None
                                            ):
                                                price = self._extract_price(
                                                    str(value[price_field])
                                                )
                                                if price:
                                                    logger.debug(
                                                        f"Preço encontrado via API aninhado '{key}.{price_field}': R$ {price:.2f}"
                                                    )
                                                    return price

                            # Se data for lista
                            elif isinstance(data, list) and len(data) > 0:
                                for item in data:
                                    if isinstance(item, dict):
                                        for field in price_fields:
                                            if (
                                                field in item
                                                and item[field] is not None
                                            ):
                                                price = self._extract_price(
                                                    str(item[field])
                                                )
                                                if price:
                                                    logger.debug(
                                                        f"Preço encontrado via API lista '{field}': R$ {price:.2f}"
                                                    )
                                                    return price

                        except ValueError as e:
                            logger.debug(f"Erro ao decodificar JSON da API: {e}")
                            continue

                except requests.exceptions.RequestException as e:
                    logger.debug(f"Erro de requisição na API {api_url}: {e}")
                    continue

            # Estratégia 2: Busca direta na página do produto
            try:
                product_url = f"https://www.pontofrio.com.br/produto/{sku}"
                logger.debug(f"Tentando página do produto: {product_url}")

                product_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                }

                product_response = requests.get(
                    product_url, headers=product_headers, timeout=15
                )
                if product_response.status_code == 200:
                    # Procura por dados de preço no JSON embeddado
                    json_patterns = [
                        r'"price":\s*"?([0-9,.]+)"?',
                        r'"preco":\s*"?([0-9,.]+)"?',
                        r'"valor":\s*"?([0-9,.]+)"?',
                        r'"precoVenda":\s*"?([0-9,.]+)"?',
                    ]

                    for pattern in json_patterns:
                        matches = re.findall(pattern, product_response.text)
                        for match in matches:
                            price = self._extract_price(match)
                            if price and price > 0:
                                logger.debug(
                                    f"Preço encontrado na página via regex '{pattern}': R$ {price:.2f}"
                                )
                                return price

            except Exception as e:
                logger.debug(f"Erro ao buscar preço na página do produto: {e}")

            logger.debug(f"Nenhum preço encontrado para SKU {sku}")
            return None

        except Exception as e:
            logger.debug(f"Erro geral ao buscar preço para SKU {sku}: {e}")
            return None

    def _extract_price_from_html_context(self, html_content, product_id, sku):
        """
        Extrai preço usando monitoramento de requisições de rede do navegador
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import time
            import json

            # Configurar Chrome com logging de performance
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=VizDisplayCompositor")
            options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            # Habilitar logging de performance para capturar requisições de rede
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option(
                "perfLoggingPrefs",
                {
                    "enableNetwork": True,
                    "enablePage": False,
                },
            )
            options.add_experimental_option("loggingPrefs", {"performance": "ALL"})

            driver = webdriver.Chrome(options=options)

            try:
                # URLs alternativos para testar
                urls_to_test = [
                    f"https://www.pontofrio.com.br/produto/{sku}",
                    f"https://www.pontofrio.com.br/p/{sku}",
                    f"https://www.pontofrio.com.br/busca?q={sku}",
                    f"https://www.pontofrio.com.br/iphone/b",  # Fallback para página de listagem
                ]

                price = None

                for url in urls_to_test:
                    logger.info(f"🔍 Testando URL: {url}")

                    try:
                        # Limpar logs
                        try:
                            driver.get_log("performance")
                        except:
                            pass

                        # Carregar página
                        driver.get(url)

                        # Aguardar carregamento e possíveis requisições AJAX
                        time.sleep(8)

                        # Tentar capturar logs de rede
                        try:
                            logs = driver.get_log("performance")

                            # Analisar requisições de rede em busca de APIs de preço
                            for log in logs:
                                try:
                                    message = json.loads(log["message"])

                                    if (
                                        message["message"]["method"]
                                        == "Network.responseReceived"
                                    ):
                                        response = message["message"]["params"][
                                            "response"
                                        ]
                                        request_url = response.get("url", "")

                                        # Procurar por APIs de preço do Ponto Frio
                                        if any(
                                            keyword in request_url.lower()
                                            for keyword in [
                                                "preco",
                                                "price",
                                                "nprice",
                                                "valor",
                                                "oferta",
                                                "merchandising",
                                                "api",
                                                "produto",
                                            ]
                                        ):
                                            logger.info(
                                                f"📡 API de preço detectada: {request_url}"
                                            )

                                            # Tentar capturar resposta da API
                                            try:
                                                request_id = message["message"][
                                                    "params"
                                                ]["requestId"]
                                                response_body = driver.execute_cdp_cmd(
                                                    "Network.getResponseBody",
                                                    {"requestId": request_id},
                                                )

                                                if (
                                                    response_body
                                                    and "body" in response_body
                                                ):
                                                    api_data = json.loads(
                                                        response_body["body"]
                                                    )

                                                    # Buscar preços na resposta da API
                                                    price_fields = [
                                                        "preco",
                                                        "price",
                                                        "valor",
                                                        "precoVenda",
                                                        "salePrice",
                                                        "originalPrice",
                                                        "precoFinal",
                                                    ]

                                                    extracted_price = self._extract_price_from_api_response(
                                                        api_data, price_fields
                                                    )
                                                    if extracted_price:
                                                        logger.success(
                                                            f"✅ Preço capturado via monitoramento de rede: R$ {extracted_price:.2f}"
                                                        )
                                                        return extracted_price

                                            except Exception as api_error:
                                                logger.debug(
                                                    f"Erro ao capturar resposta da API: {api_error}"
                                                )

                                except Exception as log_error:
                                    continue

                        except Exception as logs_error:
                            logger.debug(f"Erro ao capturar logs: {logs_error}")

                        # Se não encontrou via rede, tentar buscar no DOM
                        try:
                            price_elements = driver.find_elements(By.CSS_SELECTOR, "*")

                            for element in price_elements[
                                :100
                            ]:  # Limitar para evitar timeout
                                try:
                                    text = element.text.strip()
                                    if (
                                        text
                                        and ("R$" in text or "," in text)
                                        and any(char.isdigit() for char in text)
                                    ):
                                        cleaned_price = self._clean_price_value(text)
                                        if (
                                            cleaned_price and cleaned_price > 100
                                        ):  # Preços mínimos realistas
                                            logger.info(
                                                f"✅ Preço encontrado no DOM: R$ {cleaned_price:.2f}"
                                            )
                                            return cleaned_price
                                except:
                                    continue

                        except Exception as dom_error:
                            logger.debug(f"Erro ao buscar no DOM: {dom_error}")

                        # Se encontrou algo válido, continuar; senão, tentar próxima URL
                        if price:
                            break

                    except Exception as url_error:
                        logger.debug(f"Erro ao testar URL {url}: {url_error}")
                        continue

                logger.warning(
                    f"⚠️ Nenhum preço encontrado para SKU {sku} após testar todas as URLs"
                )
                return None

            finally:
                driver.quit()

        except Exception as e:
            logger.error(
                f"❌ Erro ao extrair preço com monitoramento de rede para SKU {sku}: {e}"
            )

            # Fallback final para método anterior
            try:
                return self._fetch_price_from_nprice_api(sku or product_id)
            except:
                return None

    def _extract_price_from_api_response(self, api_data, price_fields):
        """
        Extrai preço de resposta de API JSON
        """
        try:
            if isinstance(api_data, dict):
                # Busca direta nos campos principais
                for field in price_fields:
                    if field in api_data and api_data[field]:
                        price_value = self._clean_price_value(str(api_data[field]))
                        if price_value and price_value > 0:
                            return price_value

                # Busca em objetos aninhados
                for key, value in api_data.items():
                    if isinstance(value, dict):
                        for field in price_fields:
                            if field in value and value[field]:
                                price_value = self._clean_price_value(str(value[field]))
                                if price_value and price_value > 0:
                                    return price_value
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                for field in price_fields:
                                    if field in item and item[field]:
                                        price_value = self._clean_price_value(
                                            str(item[field])
                                        )
                                        if price_value and price_value > 0:
                                            return price_value

            return None

        except Exception as e:
            logger.debug(f"Erro ao extrair preço da API: {e}")
            return None

    def _fetch_price_from_nprice_api(self, product_id):
        """
        Busca o preço usando a API NPRICE do Ponto Frio - SOLUÇÃO DEFINITIVA
        Configurações extraídas do debug do site real do Ponto Frio
        """
        try:
            # Configurações da API NPRICE encontradas no HTML do site
            api_endpoint = "https://api.pontofrio.com.br/merchandising/oferta/v1/Preco"
            api_path = "/Produto/PrecoVenda/"
            api_key = "d081fef8c2c44645bb082712ed32a047"

            # URL completa para buscar o preço
            price_url = f"{api_endpoint}{api_path}{product_id}"

            # Headers baseados na configuração real do Ponto Frio
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "X-API-Key": api_key,
                "Referer": "https://www.pontofrio.com.br/",
                "Origin": "https://www.pontofrio.com.br",
            }

            logger.info(f"🔍 Consultando API NPRICE - Produto: {product_id}")
            logger.debug(f"URL: {price_url}")

            response = self.session.get(price_url, headers=headers, timeout=15)

            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.debug(f"Resposta API NPRICE: {data}")

                    # Busca preço nos campos esperados da API
                    price_fields = [
                        "precoVenda",
                        "preco",
                        "price",
                        "valor",
                        "salePrice",
                        "originalPrice",
                        "precoFinal",
                        "precoAtual",
                    ]

                    # Busca direta nos campos principais
                    for field in price_fields:
                        if field in data and data[field]:
                            price_value = self._clean_price_value(str(data[field]))
                            if price_value and price_value > 0:
                                logger.info(
                                    f"✅ Preço encontrado via API NPRICE ({field}): R$ {price_value:.2f}"
                                )
                                return price_value

                    # Busca em objetos aninhados
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if isinstance(value, dict):
                                for field in price_fields:
                                    if field in value and value[field]:
                                        price_value = self._clean_price_value(
                                            str(value[field])
                                        )
                                        if price_value and price_value > 0:
                                            logger.info(
                                                f"✅ Preço encontrado via API NPRICE ({key}.{field}): R$ {price_value:.2f}"
                                            )
                                            return price_value

                    logger.warning(
                        f"⚠️ API NPRICE retornou dados mas nenhum campo de preço válido encontrado"
                    )

                except ValueError as e:
                    logger.error(f"❌ Erro ao parsear JSON da API NPRICE: {e}")
                    logger.debug(f"Conteúdo da resposta: {response.text[:500]}")

            elif response.status_code == 404:
                logger.warning(f"⚠️ Produto {product_id} não encontrado na API NPRICE")
            else:
                logger.warning(f"⚠️ API NPRICE retornou status {response.status_code}")
                logger.debug(f"Resposta: {response.text[:200]}")

            return None

        except Exception as e:
            logger.error(
                f"❌ Erro ao consultar API NPRICE para produto {product_id}: {e}"
            )
            return None

    def _clean_price_value(self, price_str):
        """
        Limpa e converte string de preço para float
        """
        try:
            if not price_str or price_str.lower() in ["null", "none", ""]:
                return None

            # Remove caracteres não numéricos exceto vírgula e ponto
            price_clean = re.sub(r"[^\d,.]", "", str(price_str))

            if not price_clean:
                return None

            # Trata diferentes formatos brasileiros
            if "," in price_clean and "." in price_clean:
                # Formato: 1.234,56 -> 1234.56
                price_clean = price_clean.replace(".", "").replace(",", ".")
            elif "," in price_clean:
                # Se só tem vírgula, pode ser separador decimal (123,45)
                if len(price_clean.split(",")[-1]) <= 2:
                    price_clean = price_clean.replace(",", ".")

            price_float = float(price_clean)
            return price_float if price_float > 0 else None

        except (ValueError, AttributeError) as e:
            logger.debug(f"Erro ao limpar preço '{price_str}': {e}")
            return None

    def _is_realistic_iphone_price_range(self, price: float) -> bool:
        """
        Verifica se o preço está dentro de uma faixa realista para iPhones no Brasil
        """
        try:
            # iPhones no Brasil custam entre R$ 1.500 e R$ 15.000 (aproximadamente)
            # Exclui valores como IDs de categoria (326) ou outros números pequenos
            return 1500.0 <= price <= 15000.0
        except (TypeError, ValueError):
            return False

    def _get_product_context(self, html_content, product_id, sku, window_size=2000):
        """
        Extrai uma janela de contexto ao redor das menções do produto
        """
        try:
            # Busca posições das menções do produto
            positions = []

            # Busca por ID e SKU
            for search_term in [f'"id":"{product_id}"', f'"idSku":{sku}']:
                start = 0
                while True:
                    pos = html_content.find(search_term, start)
                    if pos == -1:
                        break
                    positions.append(pos)
                    start = pos + 1

            if not positions:
                return None

            # Pega o contexto ao redor da primeira ocorrência
            pos = positions[0]
            start = max(0, pos - window_size)
            end = min(len(html_content), pos + window_size)

            return html_content[start:end]

        except Exception as e:
            logger.debug(f"Erro ao extrair contexto do produto: {e}")
            return None

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço"""
        if not price_text:
            return None

        # Remove caracteres não numéricos exceto vírgulas e pontos
        cleaned = re.sub(r"[^\d,.]", "", price_text)

        # Converte vírgula para ponto (padrão brasileiro)
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


class CarrefourScraper(BaseScraper):
    """Scraper específico para Carrefour"""

    def __init__(self):
        config = SiteConfig(
            name="Carrefour",
            base_url="https://www.carrefour.com.br",
            search_url_pattern="https://www.carrefour.com.br/busca/{query}",
            selectors={
                "product_container": "a[data-testid='search-product-card'], [data-testid*='product-card'], [data-testid*='product']",
                "title": "h2, h3, [data-testid*='name'], [data-testid*='title']",
                "price": "span:contains('R$'), [data-testid*='price']",
                "original_price": "[data-testid*='old-price'], .line-through, [class*='old']",
                "link": "",  # O container já é um link
                "image": "img[src], img[data-src]",
                "rating": "[data-testid*='rating'], [class*='rating']",
                "reviews": "[data-testid*='reviews'], [class*='reviews']",
                "discount": "[data-testid*='discount'], [class*='discount']",
                "availability": "[data-testid*='availability'], [class*='stock']",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://www.carrefour.com.br/",
            },
            rate_limit_delay=2.5,  # Delay moderado para Carrefour
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """Constrói URL de busca do Carrefour - usa %20 para espaços em vez de +"""
        # Carrefour funciona melhor com %20 para espaços em vez de +
        encoded_query = urllib.parse.quote(product_name, safe="")
        return self.config.search_url_pattern.format(query=encoded_query)

    async def scrape(
        self, product_name: str, max_results: int = 10
    ) -> List[ProductInfo]:
        """Override do método scrape para aguardar carregamento dinâmico do Carrefour"""
        logger.info(f"Iniciando scraping {self.config.name} para: {product_name}")

        search_url = self.build_search_url(product_name)

        # Primeiro tenta com Selenium (melhor para carregamento dinâmico)
        products = await self.scrape_with_selenium_wait(search_url, max_results)

        if products:
            logger.info(f"Scraping {self.config.name} concluído via Selenium")
        else:
            # Fallback para requests se Selenium falhar
            products = await self.scrape_with_requests(search_url, max_results)
            logger.info(f"Scraping {self.config.name} concluído via requests")

        return products[:max_results]

    async def scrape_with_selenium_wait(
        self, url: str, max_results: int
    ) -> List[ProductInfo]:
        """Scraping com Selenium aguardando carregamento dinâmico"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time

        logger.info(f"Iniciando scraping com Selenium (wait): {url}")

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"--user-agent={self.config.headers['User-Agent']}")

        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)

            # Aguarda carregamento inicial
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            # Aguarda mais tempo para carregamento dinâmico
            logger.info("Aguardando carregamento dinâmico dos produtos...")
            time.sleep(8)

            # Tenta aguardar por elementos que podem indicar produtos carregados
            possible_selectors = [
                "[data-testid*='product']",
                "[class*='product']",
                "[class*='card']",
                "article",
                "[data-component*='product']",
            ]

            products_found = False
            for selector in possible_selectors:
                try:
                    elements = WebDriverWait(driver, 3).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                    )
                    if elements:
                        logger.info(f"Encontrados elementos com seletor: {selector}")
                        products_found = True
                        break
                except:
                    continue

            if not products_found:
                logger.info("Aguardando mais tempo para carregamento...")
                time.sleep(5)

            # Extrai HTML e processa
            html_content = driver.page_source
            products = self.extract_product_info(html_content, url)

            logger.success(
                f"Scraping Selenium concluído: {len(products)} produtos encontrados em {self.config.name}"
            )
            return products

        except Exception as e:
            logger.error(f"Erro no scraping Selenium para {self.config.name}: {str(e)}")
            return []
        finally:
            if driver:
                driver.quit()

    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos do HTML do Carrefour"""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Seleciona containers de produtos
        product_containers = soup.select(self.config.selectors["product_container"])

        # Fallbacks para diferentes layouts do Carrefour
        if not product_containers:
            fallback_selectors = [
                ".vtex-search-result-3-x-galleryItem",
                ".vtex-product-summary-2-x-container",
                "[data-testid='product-summary-container']",
                ".shelf-item",
                ".product",
            ]
            for selector in fallback_selectors:
                product_containers = soup.select(selector)
                if product_containers:
                    break

        logger.info(f"Encontrados {len(product_containers)} produtos no Carrefour")

        for container in product_containers:
            try:
                # Para Carrefour, o container é um link
                product_url = None
                if container.name == "a" and container.get("href"):
                    product_url = container["href"]

                # Se não é link direto, procura link dentro
                if not product_url:
                    link_elem = container.select_one("a[href]")
                    if link_elem:
                        product_url = link_elem["href"]

                if not product_url:
                    continue

                # Normaliza URL
                if product_url.startswith("/"):
                    product_url = self.config.base_url + product_url
                elif not product_url.startswith("http"):
                    product_url = self.config.base_url + "/" + product_url

                # Título - busca h2 primeiro (específico do Carrefour)
                title = None
                title_elem = container.select_one("h2")
                if title_elem:
                    title = title_elem.get_text(strip=True)

                # Se não encontrou h2, tenta outros seletores
                if not title:
                    for title_selector in ["h3", "h1", "[data-testid*='name']"]:
                        title_elem = container.select_one(title_selector)
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            if title:
                                break

                if not title:
                    continue

                # Preço - busca span com R$ primeiro
                price = None
                price_elements = container.select("span")
                for price_elem in price_elements:
                    price_text = price_elem.get_text(strip=True)
                    if "R$" in price_text:
                        price = self._extract_price(price_text)
                        if price:
                            break

                if not price:
                    continue

                # Imagem
                image_url = None
                image_elem = container.select_one("img[src], img[data-src]")
                if image_elem:
                    image_url = image_elem.get("src") or image_elem.get("data-src")
                    if image_url and not image_url.startswith("http"):
                        if image_url.startswith("//"):
                            image_url = "https:" + image_url
                        elif image_url.startswith("/"):
                            image_url = self.config.base_url + image_url

                # Cria objeto ProductInfo
                product_info = ProductInfo(
                    name=title,
                    price=price,
                    original_price=None,  # Carrefour não mostra preço original na listagem
                    discount_percentage=None,
                    availability="available",  # Assume disponível se está na listagem
                    url=product_url,
                    site=self.config.name,
                    image_url=image_url,
                    rating=None,  # Não há ratings na listagem
                )

                products.append(product_info)

            except Exception as e:
                logger.warning(f"Erro ao processar produto Carrefour: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos do Carrefour")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço do Carrefour"""
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
            logger.debug(f"Não foi possível extrair preço de: {price_text}")
            return None


class SamsungScraper(BaseScraper):
    """Scraper específico para Samsung Brasil"""

    def __init__(self):
        config = SiteConfig(
            name="Samsung",
            base_url="https://shop.samsung.com.br",
            search_url_pattern="https://shop.samsung.com.br/{query}",
            selectors={
                "product_container": ".pdp-product-card, .product-item, .product-card, .search-result-item",
                "title": ".pdp-product-card__name, .product-title, .product-name, h3, h4, .card-title",
                "price": ".pdp-product-card__price, .price-current, .current-price, .price, .valor",
                "original_price": ".pdp-product-card__price--original, .price-original, .old-price",
                "link": "a, .pdp-product-card__link, .product-link",
                "image": "img, .product-image, .card-image",
                "rating": ".rating, .stars, .avaliacao",
                "reviews": ".reviews-count, .avaliacoes",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://shop.samsung.com.br/",
            },
            rate_limit_delay=3.0,  # Delay maior para Samsung
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """Constrói URL de busca da Samsung - tenta múltiplas estratégias"""
        # Samsung pode ter URLs dinâmicas, vamos tentar diferentes abordagens
        encoded_query = urllib.parse.quote(product_name, safe="")

        # Estratégia principal: página de busca geral
        return f"https://shop.samsung.com.br/busca/{encoded_query}"

    async def scrape(
        self, product_name: str, max_results: int = 10
    ) -> List[ProductInfo]:
        """Override do método scrape para aguardar carregamento dinâmico da Samsung"""
        logger.info(f"Iniciando scraping {self.config.name} para: {product_name}")

        # Para Samsung, vamos tentar múltiplas URLs
        search_urls = self._build_multiple_search_urls(product_name)

        all_products = []

        for search_url in search_urls:
            try:
                # Primeiro tenta com Selenium (melhor para sites dinâmicos)
                products = await self.scrape_with_selenium_wait(search_url, max_results)

                if products:
                    all_products.extend(products)
                    logger.info(
                        f"Samsung: Encontrados {len(products)} produtos na URL: {search_url}"
                    )
                    break  # Para no primeiro sucesso
                else:
                    # Fallback para requests
                    products = await self.scrape_with_requests(search_url, max_results)
                    if products:
                        all_products.extend(products)
                        logger.info(
                            f"Samsung: Encontrados {len(products)} produtos via requests na URL: {search_url}"
                        )
                        break

            except Exception as e:
                logger.warning(f"Erro ao tentar URL Samsung {search_url}: {str(e)}")
                continue

        if all_products:
            logger.info(f"Scraping {self.config.name} concluído via método dinâmico")
        else:
            logger.warning(f"Samsung: Nenhum produto encontrado em nenhuma URL testada")

        return all_products[:max_results]

    def _build_multiple_search_urls(self, product_name: str) -> List[str]:
        """Constrói múltiplas URLs de busca para Samsung"""
        encoded_query = urllib.parse.quote(product_name, safe="")

        urls = [
            # URL de busca principal (sem "busca")
            f"https://shop.samsung.com.br/{encoded_query}",
            # URLs por categoria (se for smartphone/celular)
            f"https://shop.samsung.com.br/celulares/{encoded_query}",
            f"https://shop.samsung.com.br/smartphones/{encoded_query}",
            # URL de busca alternativa com parâmetro
            f"https://shop.samsung.com.br/search?q={encoded_query}",
            # URL com query parameter
            f"https://shop.samsung.com.br/?search={encoded_query}",
        ]

        return urls

    async def scrape_with_selenium_wait(
        self, url: str, max_results: int
    ) -> List[ProductInfo]:
        """Scraping com Selenium aguardando carregamento dinâmico para Samsung"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time

        logger.info(f"Iniciando scraping Samsung com Selenium (wait): {url}")

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"--user-agent={self.config.headers['User-Agent']}")

        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)

            # Aguarda carregamento inicial
            time.sleep(5)

            logger.info("Aguardando carregamento dinâmico dos produtos Samsung...")

            # Aguarda elementos de produto aparecerem (múltiplos seletores)
            selectors_to_wait = [
                "[data-testid*='product']",
                ".product-item",
                ".product-card",
                ".product-tile",
                "[class*='product']",
                ".pd-item",
            ]

            elements_found = False
            for selector in selectors_to_wait:
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(
                            f"Encontrados elementos Samsung com seletor: {selector}"
                        )
                        elements_found = True
                        break
                except:
                    continue

            if not elements_found:
                logger.warning(
                    "Samsung: Nenhum produto encontrado com seletores dinâmicos"
                )
                time.sleep(8)  # Aguarda mais tempo

            # Debug: Vamos inspecionar a estrutura HTML
            logger.info("🔍 DEBUG: Inspecionando estrutura Samsung...")

            # Verificar todos os elementos 'article' na página
            articles = driver.find_elements(By.TAG_NAME, "article")
            logger.info(f"🔍 Encontrados {len(articles)} elementos 'article'")

            # Debug mais detalhado: examinar o HTML dos primeiros 2 articles
            if articles:
                for idx in range(min(2, len(articles))):
                    article = articles[idx]
                    html_content = article.get_attribute("outerHTML")

                    # Buscar todos os links dentro deste article
                    links = article.find_elements(By.TAG_NAME, "a")
                    logger.info(f"🔗 Article {idx+1}: {len(links)} links encontrados")

                    for i, link in enumerate(links):
                        href = link.get_attribute("href")
                        text = link.text[:30] if link.text else "sem texto"
                        logger.info(f"   Link {i+1}: href='{href}' texto='{text}'")

                    # Exibir parte do HTML para análise
                    logger.info(f"🔍 HTML do article {idx+1} (primeiros 800 chars):")
                    logger.info(f"{html_content[:800]}...")

            # Estratégia específica para Samsung VTEX: simular cliques nos elementos
            samsung_products_data = []

            if articles:
                current_url = driver.current_url

                for i in range(
                    min(5, len(articles))
                ):  # Processar apenas os primeiros 5
                    try:
                        logger.info(
                            f"🎯 Tentando extrair URL do produto Samsung {i+1}..."
                        )

                        # Re-localizar articles a cada iteração para evitar stale references
                        articles_fresh = driver.find_elements(By.TAG_NAME, "article")

                        if i >= len(articles_fresh):
                            logger.warning(
                                f"Produto {i+1}: Não há mais articles disponíveis"
                            )
                            break

                        article = articles_fresh[i]

                        # Scroll para o elemento
                        driver.execute_script(
                            "arguments[0].scrollIntoView(true);", article
                        )
                        time.sleep(1)

                        # Capturar URL antes do clique
                        url_before = driver.current_url

                        # Clicar no article
                        article.click()
                        time.sleep(3)  # Aguardar navegação

                        # Capturar URL após o clique
                        url_after = driver.current_url

                        if url_after != url_before and (
                            "/p" in url_after or "skuId" in url_after
                        ):
                            # Extrair nome do produto da nova página
                            try:
                                product_name_elem = driver.find_element(
                                    By.CSS_SELECTOR,
                                    "h1, .product-title, .product-name, [data-testid*='name'], [data-testid*='title']",
                                )
                                product_name = product_name_elem.text.strip()
                            except:
                                product_name = ""

                            samsung_products_data.append(
                                {
                                    "article_index": i,
                                    "url": url_after,
                                    "name": product_name,
                                }
                            )

                            logger.info(
                                f"✅ URL real encontrada para produto {i+1}: {url_after}"
                            )
                            if product_name:
                                logger.info(f"   Nome: {product_name[:50]}...")
                        else:
                            logger.warning(
                                f"❌ URL não mudou para produto {i+1}: {url_after}"
                            )

                        # Voltar para página de busca
                        driver.get(current_url)
                        time.sleep(3)  # Aguardar carregamento completo

                    except Exception as e:
                        logger.warning(
                            f"Erro ao processar produto Samsung {i+1}: {str(e)}"
                        )
                        # Tentar voltar para página de busca em caso de erro
                        try:
                            driver.get(current_url)
                            time.sleep(2)
                        except:
                            pass
                        continue

                logger.info(
                    f"🎯 Encontradas {len(samsung_products_data)} URLs reais para produtos Samsung"
                )

            # Pega o HTML final
            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # Extrai produtos passando os dados de URLs específicas
            products = self.extract_product_info(
                soup, url, max_results, samsung_products_data
            )

            logger.success(
                f"Scraping Samsung Selenium concluído: {len(products)} produtos encontrados"
            )
            return products

        except Exception as e:
            logger.error(f"Erro no scraping Samsung Selenium: {str(e)}")
            return []
        finally:
            if driver:
                driver.quit()

    def _generate_samsung_product_url(self, product_name: str) -> str:
        """Gera URL de produto Samsung baseada no nome"""
        if not product_name:
            return None

        # Limpar e formatar o nome do produto para URL
        import re

        # Remover caracteres especiais e normalizar
        clean_name = re.sub(r"[^\w\s-]", "", product_name.lower())
        clean_name = re.sub(r"\s+", "-", clean_name.strip())
        clean_name = clean_name.replace("--", "-").strip("-")

        # Padrões de URL do Samsung
        base_patterns = [
            f"https://shop.samsung.com.br/produto/{clean_name}",
            f"https://shop.samsung.com.br/p/{clean_name}",
            f"https://shop.samsung.com.br/{clean_name}",
        ]

        # Se o produto tem "samsung" no nome, remover para evitar redundância
        if "samsung" in clean_name:
            clean_name_no_brand = clean_name.replace("samsung-", "").replace(
                "-samsung", ""
            )
            if clean_name_no_brand:
                base_patterns.extend(
                    [
                        f"https://shop.samsung.com.br/produto/{clean_name_no_brand}",
                        f"https://shop.samsung.com.br/p/{clean_name_no_brand}",
                    ]
                )

        # Retornar a primeira URL gerada (pode ser validada depois)
        return base_patterns[0] if base_patterns else None

    def extract_product_info(
        self,
        soup: BeautifulSoup,
        search_url: str,
        max_results: int,
        urls_data: List[dict] = None,
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos da Samsung do HTML"""
        products = []
        seen_urls = set()

        logger.info(f"Iniciando extração de produtos Samsung...")

        # Criar mapa de URLs específicas se fornecido
        url_map = {}
        if urls_data:
            for item in urls_data:
                url_map[item["article_index"]] = item["url"]
            logger.info(f"📋 Usando {len(url_map)} URLs específicas mapeadas")

        # Múltiplos seletores para encontrar containers de produtos
        container_selectors = [
            "[data-testid*='product']",
            ".product-item",
            ".product-card",
            ".product-tile",
            ".pd-item",
            "[class*='product-item']",
            "[class*='product-card']",
            ".item-card",
            "article",
            "[data-product-id]",
        ]

        containers = []
        for selector in container_selectors:
            found_containers = soup.select(selector)
            if found_containers:
                containers = found_containers
                logger.info(
                    f"Samsung: Usando seletor '{selector}' - {len(containers)} containers"
                )
                break

        if not containers:
            logger.warning("Samsung: Nenhum container de produto encontrado")
            return []

        logger.info(f"Encontrados {len(containers)} produtos na Samsung")

        for i, container in enumerate(
            containers[: max_results * 3]
        ):  # Processa mais para filtrar
            if len(products) >= max_results:
                break

            try:
                # Usar URL específica se disponível no mapa
                specific_url = url_map.get(i) if url_map else None

                # Nome do produto - múltiplas tentativas
                name = ""
                name_selectors = [
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    ".product-title",
                    ".product-name",
                    ".item-title",
                    ".item-name",
                    ".title",
                    ".name",
                    "[data-testid*='title']",
                    "[data-testid*='name']",
                    "a[title]",
                    "[aria-label]",
                ]

                for name_sel in name_selectors:
                    name_element = container.select_one(name_sel)
                    if name_element and name_element.get_text(strip=True):
                        name = name_element.get_text(strip=True)
                        break
                    elif name_element and name_element.get("title"):
                        name = name_element["title"].strip()
                        break
                    elif name_element and name_element.get("aria-label"):
                        name = name_element["aria-label"].strip()
                        break

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
                    "[class*='price']",
                    ".pd-price",
                    ".product-price",
                    "span[class*='price']",
                    "div[class*='price']",
                    "strong",
                    "b",
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

                # URL do produto - múltiplas estratégias
                url = specific_url if specific_url else ""

                if not url:
                    # 1. Buscar links específicos com padrões Samsung
                    link_selectors = [
                        "a[href*='/p']",  # Links que contêm '/p' (padrão Samsung)
                        "a[href*='skuId']",  # Links que contêm 'skuId'
                        "a[href*='/produto/']",  # Links que contêm '/produto/'
                        "a[href]",  # Qualquer link
                    ]

                    for link_sel in link_selectors:
                        link_elements = container.select(
                            link_sel
                        )  # Buscar TODOS os links, não apenas o primeiro
                        for link_element in link_elements:
                            href = link_element.get("href")
                            if href:
                                # Verificar se é um link de produto válido
                                if (
                                    "/p" in href
                                    or "skuId" in href
                                    or "/produto/" in href
                                ):
                                    if href.startswith("/"):
                                        url = f"https://shop.samsung.com.br{href}"
                                    elif not href.startswith("http"):
                                        url = f"https://shop.samsung.com.br/{href}"
                                    else:
                                        url = href

                                    logger.debug(
                                        f"Samsung URL real extraída: {url[:100]}..."
                                    )
                                    break

                        if url:  # Se encontrou URL válida, parar de procurar
                            break

                    # 2. Se não encontrar URL específica, usar search_url como último recurso
                    if not url:
                        logger.warning(
                            f"Samsung: Nenhuma URL específica encontrada para: {name[:30]}..."
                        )
                        url = search_url
                else:
                    logger.debug(f"Samsung URL específica do JS usada: {url[:100]}...")

                # Evitar duplicatas por URL
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

                # Imagem do produto
                image_url = ""
                img_element = container.select_one(
                    "img[src], img[data-src], img[data-lazy-src]"
                )
                if img_element:
                    image_url = (
                        img_element.get("src")
                        or img_element.get("data-src")
                        or img_element.get("data-lazy-src", "")
                    )
                    if image_url and not image_url.startswith("http"):
                        if image_url.startswith("//"):
                            image_url = f"https:{image_url}"
                        elif image_url.startswith("/"):
                            image_url = f"https://shop.samsung.com.br{image_url}"

                # Validação final - só adiciona produtos com URL específica
                if name and price and len(name) >= 3:
                    # Preferir produtos com URL específica, mas aceitar search_url se necessário
                    final_url = url if url and url != search_url else search_url

                    product = ProductInfo(
                        name=name,
                        price=price,
                        url=final_url,
                        image_url=image_url if image_url else None,
                        site="Samsung",
                        availability="Disponível",
                    )
                    products.append(product)

                    url_type = "específica" if final_url != search_url else "busca"
                    logger.debug(
                        f"✅ Produto Samsung válido ({url_type}): {name[:50]}... - R$ {price}"
                    )

            except Exception as e:
                logger.warning(f"Erro ao processar produto Samsung: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos da Samsung")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço"""
        if not price_text:
            return None

        # Remove caracteres não numéricos exceto vírgulas e pontos
        import re

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
            logger.debug(f"Não foi possível extrair preço de: {price_text}")
            return None
class LGScraper(BaseScraper):
    """Scraper especÃ­fico para LG Brasil"""

    def __init__(self):
        config = SiteConfig(
            name="LG",
            base_url="https://www.lg.com",
            search_url_pattern="https://www.lg.com/br/busca?q={query}",
            selectors={
                "product_container": ".product-item, .product-card, .search-result-item, .product",
                "title": ".product-title, .product-name, h3, h4, .card-title, .title",
                "price": ".price-current, .current-price, .price, .valor, .preco",
                "original_price": ".price-original, .old-price, .price-before",
                "link": "a, .product-link, .card-link",
                "image": "img, .product-image, .card-image",
                "rating": ".rating, .stars, .avaliacao",
                "reviews": ".reviews-count, .avaliacoes",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://www.lg.com/br/",
            },
            rate_limit_delay=3.0,  # Delay maior para LG
        )
        super().__init__(config)

    def build_search_url(self, product_name: str) -> str:
        """ConstrÃ³i URL de busca da LG - tenta mÃºltiplas estratÃ©gias"""
        # LG pode ter URLs dinÃ¢micas, vamos tentar diferentes abordagens
        encoded_query = urllib.parse.quote(product_name, safe='')
        return self.config.search_url_pattern.format(query=encoded_query)

    async def scrape(self, product_name: str, max_results: int = 10) -> List[ProductInfo]:
        """Override do mÃ©todo scrape para aguardar carregamento dinÃ¢mico da LG"""
        logger.info(f"Iniciando scraping {self.config.name} para: {product_name}")
        
        # Para LG, vamos tentar mÃºltiplas URLs
        search_urls = self._build_multiple_search_urls(product_name)
        
        all_products = []
        
        for search_url in search_urls:
            try:
                # Primeiro tenta com Selenium (melhor para sites dinÃ¢micos)
                products = await self.scrape_with_selenium_wait(search_url, max_results)
                
                if products:
                    all_products.extend(products)
                    logger.info(f"LG: Encontrados {len(products)} produtos na URL: {search_url}")
                    break  # Se encontrou produtos, nÃ£o precisa tentar outras URLs
                else:
                    logger.warning(f"LG: Nenhum produto encontrado na URL: {search_url}")
                        
            except Exception as e:
                logger.warning(f"Erro ao tentar URL LG {search_url}: {str(e)}")
                continue
        
        if all_products:
            logger.info(f"Scraping {self.config.name} concluÃ­do via mÃ©todo dinÃ¢mico")
        else:
            logger.warning(f"LG: Nenhum produto encontrado em nenhuma URL testada")
            
        return all_products[:max_results]
    
    def _build_multiple_search_urls(self, product_name: str) -> List[str]:
        """ConstrÃ³i mÃºltiplas URLs de busca para LG"""
        encoded_query = urllib.parse.quote(product_name, safe='')
        
        urls = [
            # URL de busca principal
            f"https://www.lg.com/br/busca?q={encoded_query}",
            # URLs alternativas
            f"https://www.lg.com/br/search?query={encoded_query}",
            f"https://www.lg.com/br/produtos?search={encoded_query}",
        ]
        
        return urls

    async def scrape_with_selenium_wait(self, url: str, max_results: int) -> List[ProductInfo]:
        """Scraping com Selenium aguardando carregamento dinÃ¢mico para LG"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time
        
        logger.info(f"Iniciando scraping LG com Selenium (wait): {url}")
        
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"--user-agent={self.config.headers['User-Agent']}")
        
        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            
            # Aguarda carregamento inicial
            time.sleep(5)
            
            logger.info("Aguardando carregamento dinÃ¢mico dos produtos LG...")
            
            # Aguarda elementos de produto aparecerem (mÃºltiplos seletores)
            selectors_to_wait = [
                ".product-item",
                ".product-card", 
                ".product",
                "[class*='product']",
                ".search-result-item"
            ]
            
            elements_found = False
            for selector in selectors_to_wait:
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"Encontrados elementos LG com seletor: {selector}")
                        elements_found = True
                        break
                except:
                    continue
            
            if not elements_found:
                logger.warning("LG: Nenhum produto encontrado com seletores dinÃ¢micos")
                time.sleep(8)  # Aguarda mais tempo

            # Debug: Vamos inspecionar a estrutura HTML
            logger.info("ðŸ” DEBUG: Inspecionando estrutura LG...")
            
            # Verificar elementos de produto na pÃ¡gina
            product_elements = driver.find_elements(By.CSS_SELECTOR, 
                ".product-item, .product-card, .product, [class*='product'], .search-result-item")
            logger.info(f"ðŸ” Encontrados {len(product_elements)} elementos de produto")
            
            # Debug mais detalhado: examinar o HTML dos primeiros 2 elementos
            if product_elements:
                for idx in range(min(2, len(product_elements))):
                    element = product_elements[idx]
                    html_content = element.get_attribute('outerHTML')
                    
                    # Buscar todos os links dentro deste elemento
                    links = element.find_elements(By.TAG_NAME, "a")
                    logger.info(f"ðŸ”— Elemento {idx+1}: {len(links)} links encontrados")
                    
                    for i, link in enumerate(links):
                        href = link.get_attribute("href")
                        text = link.text[:30] if link.text else "sem texto"
                        logger.info(f"   Link {i+1}: href='{href}' texto='{text}'")
                    
                    # Exibir parte do HTML para anÃ¡lise
                    logger.info(f"ðŸ” HTML do elemento {idx+1} (primeiros 800 chars):")
                    logger.info(f"{html_content[:800]}...")

            # EstratÃ©gia especÃ­fica para LG: simular cliques nos elementos se necessÃ¡rio
            lg_products_data = []
            
            if product_elements:
                current_url = driver.current_url
                
                for i in range(min(5, len(product_elements))):  # Processar apenas os primeiros 5
                    try:
                        logger.info(f"ðŸŽ¯ Tentando extrair URL do produto LG {i+1}...")
                        
                        # Re-localizar elementos a cada iteraÃ§Ã£o para evitar stale references
                        elements_fresh = driver.find_elements(By.CSS_SELECTOR, 
                            ".product-item, .product-card, .product, [class*='product'], .search-result-item")
                        
                        if i >= len(elements_fresh):
                            logger.warning(f"Produto {i+1}: NÃ£o hÃ¡ mais elementos disponÃ­veis")
                            break
                            
                        element = elements_fresh[i]
                        
                        # Primeiro tentar encontrar links diretos
                        links_in_element = element.find_elements(By.TAG_NAME, "a")
                        product_url = None
                        
                        for link in links_in_element:
                            href = link.get_attribute("href")
                            if href and ('/produto' in href or '/products' in href or 'productId' in href):
                                product_url = href
                                break
                        
                        if product_url:
                            lg_products_data.append({
                                'element_index': i,
                                'url': product_url
                            })
                            logger.info(f"âœ… URL direta encontrada para produto {i+1}: {product_url}")
                        else:
                            # Se nÃ£o encontrar link direto, tentar clicar no elemento
                            try:
                                # Scroll para o elemento
                                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(1)
                                
                                # Capturar URL antes do clique
                                url_before = driver.current_url
                                
                                # Clicar no elemento
                                element.click()
                                time.sleep(3)  # Aguardar navegaÃ§Ã£o
                                
                                # Capturar URL apÃ³s o clique
                                url_after = driver.current_url
                                
                                if url_after != url_before and ('/produto' in url_after or '/products' in url_after or 'productId' in url_after):
                                    lg_products_data.append({
                                        'element_index': i,
                                        'url': url_after
                                    })
                                    
                                    logger.info(f"âœ… URL via clique encontrada para produto {i+1}: {url_after}")
                                else:
                                    logger.warning(f"âŒ URL nÃ£o mudou para produto {i+1}: {url_after}")
                                
                                # Voltar para pÃ¡gina de busca
                                driver.get(current_url)
                                time.sleep(3)  # Aguardar carregamento completo
                                
                            except Exception as e:
                                logger.warning(f"Erro ao clicar no produto LG {i+1}: {str(e)}")
                                try:
                                    driver.get(current_url)
                                    time.sleep(2)
                                except:
                                    pass
                        
                    except Exception as e:
                        logger.warning(f"Erro ao processar produto LG {i+1}: {str(e)}")
                        continue
                
                logger.info(f"ðŸŽ¯ Encontradas {len(lg_products_data)} URLs reais para produtos LG")
            
            # Pega o HTML final
            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            
            # Extrai produtos passando os dados de URLs especÃ­ficas
            products = self.extract_product_info(soup, url, max_results, lg_products_data)
            
            logger.success(f"Scraping LG Selenium concluÃ­do: {len(products)} produtos encontrados")
            return products

        except Exception as e:
            logger.error(f"Erro durante scraping LG com Selenium: {str(e)}")
            return []

        finally:
            if driver:
                driver.quit()

    def extract_product_info(self, soup: BeautifulSoup, search_url: str, max_results: int, urls_data: List[dict] = None) -> List[ProductInfo]:
        """Extrai informaÃ§Ãµes dos produtos da LG do HTML"""
        products = []
        seen_urls = set()

        logger.info(f"Iniciando extraÃ§Ã£o de produtos LG...")

        # Criar mapa de URLs especÃ­ficas se fornecido
        url_map = {}
        if urls_data:
            for item in urls_data:
                url_map[item['element_index']] = item['url']
            logger.info(f"ðŸ“‹ Usando {len(url_map)} URLs especÃ­ficas mapeadas")

        # MÃºltiplos seletores para encontrar containers de produtos
        container_selectors = [
            ".product-item",
            ".product-card",
            ".product", 
            "[class*='product']",
            ".search-result-item",
            "article",
            ".item-card",
            "[data-product-id]"
        ]

        containers = []
        used_selector = None

        for selector in container_selectors:
            containers = soup.select(selector)
            if containers:
                used_selector = selector
                logger.info(f"LG: Usando seletor '{selector}' - {len(containers)} containers")
                break

        if not containers:
            logger.warning("LG: Nenhum container de produto encontrado")
            return []

        logger.info(f"Encontrados {len(containers)} produtos na LG")

        for i, container in enumerate(containers[:max_results * 3]):  # Processa mais para filtrar
            if len(products) >= max_results:
                break

            try:
                # Usar URL especÃ­fica se disponÃ­vel no mapa
                specific_url = url_map.get(i) if url_map else None
                
                # Nome do produto - mÃºltiplas tentativas
                name = ""
                name_selectors = [
                    "h1", "h2", "h3", "h4",
                    ".product-title", ".product-name", ".item-title", ".item-name",
                    ".title", ".name", "[data-testid*='title']", "[data-testid*='name']",
                    "a[title]", "[aria-label]"
                ]

                for name_sel in name_selectors:
                    name_element = container.select_one(name_sel)
                    if name_element and name_element.get_text(strip=True):
                        name = name_element.get_text(strip=True)
                        break
                    elif name_element and name_element.get("title"):
                        name = name_element["title"].strip()
                        break
                    elif name_element and name_element.get("aria-label"):
                        name = name_element["aria-label"].strip()
                        break

                if not name or len(name) < 3:
                    continue

                # PreÃ§o do produto
                price = None
                price_selectors = [
                    "[data-testid*='price']",
                    ".price-current", ".sales-price", ".price", ".value",
                    ".preco", ".valor", "[class*='price']",
                    ".pd-price", ".product-price",
                    "span[class*='price']", "div[class*='price']",
                    "strong", "b"
                ]

                for price_sel in price_selectors:
                    price_elements = container.select(price_sel)
                    for price_elem in price_elements:
                        text = price_elem.get_text(strip=True)
                        if text and ("R$" in text or "," in text or text.replace(".", "").isdigit()):
                            price = self._extract_price(text)
                            if price:
                                break
                    if price:
                        break

                if not price:
                    continue

                # URL do produto - mÃºltiplas estratÃ©gias
                url = specific_url if specific_url else ""
                
                if not url:
                    # 1. Buscar links especÃ­ficos com padrÃµes LG
                    link_selectors = [
                        "a[href*='/produto']",  # Links que contÃªm '/produto'
                        "a[href*='/products']",  # Links que contÃªm '/products'
                        "a[href*='productId']",  # Links que contÃªm 'productId'
                        "a[href]",  # Qualquer link
                    ]
                    
                    for link_sel in link_selectors:
                        link_elements = container.select(link_sel)  # Buscar TODOS os links
                        for link_element in link_elements:
                            href = link_element.get("href")
                            if href:
                                # Verificar se Ã© um link de produto vÃ¡lido
                                if ('/produto' in href or '/products' in href or 'productId' in href):
                                    if href.startswith("/"):
                                        url = f"https://www.lg.com{href}"
                                    elif not href.startswith("http"):
                                        url = f"https://www.lg.com/{href}"
                                    else:
                                        url = href
                                    
                                    logger.debug(f"LG URL real extraÃ­da: {url[:100]}...")
                                    break
                        
                        if url:  # Se encontrou URL vÃ¡lida, parar de procurar
                            break
                    
                    # 2. Se nÃ£o encontrar URL especÃ­fica, usar search_url como Ãºltimo recurso
                    if not url:
                        logger.warning(f"LG: Nenhuma URL especÃ­fica encontrada para: {name[:30]}...")
                        url = search_url
                else:
                    logger.debug(f"LG URL especÃ­fica do mapa usada: {url[:100]}...")

                # Evitar duplicatas por URL
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

                # Imagem do produto
                image_url = ""
                img_element = container.select_one("img[src], img[data-src], img[data-lazy-src]")
                if img_element:
                    image_url = (img_element.get("src") or 
                                img_element.get("data-src") or 
                                img_element.get("data-lazy-src", ""))
                    if image_url and not image_url.startswith("http"):
                        if image_url.startswith("//"):
                            image_url = f"https:{image_url}"
                        elif image_url.startswith("/"):
                            image_url = f"https://www.lg.com{image_url}"

                # ValidaÃ§Ã£o final - sÃ³ adiciona produtos com informaÃ§Ãµes mÃ­nimas
                if name and price and len(name) >= 3:
                    # Preferir produtos com URL especÃ­fica, mas aceitar search_url se necessÃ¡rio
                    final_url = url if url and url != search_url else search_url
                    
                    product = ProductInfo(
                        name=name,
                        price=price,
                        url=final_url,
                        image_url=image_url if image_url else None,
                        site="LG",
                        availability="DisponÃ­vel",
                    )
                    products.append(product)
                    
                    url_type = "especÃ­fica" if final_url != search_url else "busca"
                    logger.debug(f"âœ… Produto LG vÃ¡lido ({url_type}): {name[:50]}... - R$ {price}")

            except Exception as e:
                logger.warning(f"Erro ao processar produto LG: {str(e)}")
                continue

        logger.info(f"ExtraÃ­dos {len(products)} produtos vÃ¡lidos da LG")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numÃ©rico do texto de preÃ§o"""
        if not price_text:
            return None

        # Remove caracteres nÃ£o numÃ©ricos exceto vÃ­rgulas e pontos
        import re
        cleaned = re.sub(r"[^\d,.]", "", price_text)

        # Trata diferentes formatos de preÃ§o brasileiros
        if "," in cleaned and "." in cleaned:
            # Formato: 1.234,56
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            # Formato: 1234,56
            cleaned = cleaned.replace(",", ".")

        try:
            return float(cleaned)
        except ValueError:
            logger.debug(f"NÃ£o foi possÃ­vel extrair preÃ§o de: {price_text}")
            return None
 
 c l a s s   L G S c r a p e r ( B a s e S c r a p e r ) :  
         " " " S c r a p e r   e s p e c � � f i c o   p a r a   L G   B r a s i l " " "  
  
         d e f   _ _ i n i t _ _ ( s e l f ) :  
                 c o n f i g   =   S i t e C o n f i g (  
                         n a m e = " L G " ,  
                         b a s e _ u r l = " h t t p s : / / w w w . l g . c o m " ,  
                         s e a r c h _ u r l _ p a t t e r n = " h t t p s : / / w w w . l g . c o m / b r / b u s c a ? q = { q u e r y } " ,  
                         s e l e c t o r s = {  
                                 " p r o d u c t _ c o n t a i n e r " :   " . p r o d u c t - i t e m ,   . p r o d u c t - c a r d ,   . s e a r c h - r e s u l t - i t e m ,   . p r o d u c t " ,  
                                 " t i t l e " :   " . p r o d u c t - t i t l e ,   . p r o d u c t - n a m e ,   h 3 ,   h 4 ,   . c a r d - t i t l e ,   . t i t l e " ,  
                                 " p r i c e " :   " . p r i c e - c u r r e n t ,   . c u r r e n t - p r i c e ,   . p r i c e ,   . v a l o r ,   . p r e c o " ,  
                                 " o r i g i n a l _ p r i c e " :   " . p r i c e - o r i g i n a l ,   . o l d - p r i c e ,   . p r i c e - b e f o r e " ,  
                                 " l i n k " :   " a ,   . p r o d u c t - l i n k ,   . c a r d - l i n k " ,  
                                 " i m a g e " :   " i m g ,   . p r o d u c t - i m a g e ,   . c a r d - i m a g e " ,  
                                 " r a t i n g " :   " . r a t i n g ,   . s t a r s ,   . a v a l i a c a o " ,  
                                 " r e v i e w s " :   " . r e v i e w s - c o u n t ,   . a v a l i a c o e s " ,  
                         } ,  
                         h e a d e r s = {  
                                 " U s e r - A g e n t " :   " M o z i l l a / 5 . 0   ( W i n d o w s   N T   1 0 . 0 ;   W i n 6 4 ;   x 6 4 )   A p p l e W e b K i t / 5 3 7 . 3 6   ( K H T M L ,   l i k e   G e c k o )   C h r o m e / 1 2 0 . 0 . 0 . 0   S a f a r i / 5 3 7 . 3 6 " ,  
                                 " A c c e p t " :   " t e x t / h t m l , a p p l i c a t i o n / x h t m l + x m l , a p p l i c a t i o n / x m l ; q = 0 . 9 , i m a g e / w e b p , * / * ; q = 0 . 8 " ,  
                                 " A c c e p t - L a n g u a g e " :   " p t - B R , p t ; q = 0 . 9 , e n ; q = 0 . 8 " ,  
                                 " A c c e p t - E n c o d i n g " :   " g z i p ,   d e f l a t e ,   b r " ,  
                                 " C a c h e - C o n t r o l " :   " n o - c a c h e " ,  
                                 " P r a g m a " :   " n o - c a c h e " ,  
                                 " R e f e r e r " :   " h t t p s : / / w w w . l g . c o m / b r / " ,  
                         } ,  
                         r a t e _ l i m i t _ d e l a y = 3 . 0 ,     #   D e l a y   m a i o r   p a r a   L G  
                 )  
                 s u p e r ( ) . _ _ i n i t _ _ ( c o n f i g )  
  
         d e f   b u i l d _ s e a r c h _ u r l ( s e l f ,   p r o d u c t _ n a m e :   s t r )   - >   s t r :  
                 " " " C o n s t r � � i   U R L   d e   b u s c a   d a   L G   -   t e n t a   m � � l t i p l a s   e s t r a t � � g i a s " " "  
                 #   L G   p o d e   t e r   U R L s   d i n � � m i c a s ,   v a m o s   t e n t a r   d i f e r e n t e s   a b o r d a g e n s  
                 e n c o d e d _ q u e r y   =   u r l l i b . p a r s e . q u o t e ( p r o d u c t _ n a m e ,   s a f e = ' ' )  
                 r e t u r n   s e l f . c o n f i g . s e a r c h _ u r l _ p a t t e r n . f o r m a t ( q u e r y = e n c o d e d _ q u e r y )  
  
         a s y n c   d e f   s c r a p e ( s e l f ,   p r o d u c t _ n a m e :   s t r ,   m a x _ r e s u l t s :   i n t   =   1 0 )   - >   L i s t [ P r o d u c t I n f o ] :  
                 " " " O v e r r i d e   d o   m � � t o d o   s c r a p e   p a r a   a g u a r d a r   c a r r e g a m e n t o   d i n � � m i c o   d a   L G " " "  
                 l o g g e r . i n f o ( f " I n i c i a n d o   s c r a p i n g   { s e l f . c o n f i g . n a m e }   p a r a :   { p r o d u c t _ n a m e } " )  
                  
                 #   P a r a   L G ,   v a m o s   t e n t a r   m � � l t i p l a s   U R L s  
                 s e a r c h _ u r l s   =   s e l f . _ b u i l d _ m u l t i p l e _ s e a r c h _ u r l s ( p r o d u c t _ n a m e )  
                  
                 a l l _ p r o d u c t s   =   [ ]  
                  
                 f o r   s e a r c h _ u r l   i n   s e a r c h _ u r l s :  
                         t r y :  
                                 #   P r i m e i r o   t e n t a   c o m   S e l e n i u m   ( m e l h o r   p a r a   s i t e s   d i n � � m i c o s )  
                                 p r o d u c t s   =   a w a i t   s e l f . s c r a p e _ w i t h _ s e l e n i u m _ w a i t ( s e a r c h _ u r l ,   m a x _ r e s u l t s )  
                                  
                                 i f   p r o d u c t s :  
                                         a l l _ p r o d u c t s . e x t e n d ( p r o d u c t s )  
                                         l o g g e r . i n f o ( f " L G :   E n c o n t r a d o s   { l e n ( p r o d u c t s ) }   p r o d u t o s   n a   U R L :   { s e a r c h _ u r l } " )  
                                         b r e a k     #   S e   e n c o n t r o u   p r o d u t o s ,   n � � o   p r e c i s a   t e n t a r   o u t r a s   U R L s  
                                 e l s e :  
                                         l o g g e r . w a r n i n g ( f " L G :   N e n h u m   p r o d u t o   e n c o n t r a d o   n a   U R L :   { s e a r c h _ u r l } " )  
                                                  
                         e x c e p t   E x c e p t i o n   a s   e :  
                                 l o g g e r . w a r n i n g ( f " E r r o   a o   t e n t a r   U R L   L G   { s e a r c h _ u r l } :   { s t r ( e ) } " )  
                                 c o n t i n u e  
                  
                 i f   a l l _ p r o d u c t s :  
                         l o g g e r . i n f o ( f " S c r a p i n g   { s e l f . c o n f i g . n a m e }   c o n c l u � � d o   v i a   m � � t o d o   d i n � � m i c o " )  
                 e l s e :  
                         l o g g e r . w a r n i n g ( f " L G :   N e n h u m   p r o d u t o   e n c o n t r a d o   e m   n e n h u m a   U R L   t e s t a d a " )  
                          
                 r e t u r n   a l l _ p r o d u c t s [ : m a x _ r e s u l t s ]  
          
         d e f   _ b u i l d _ m u l t i p l e _ s e a r c h _ u r l s ( s e l f ,   p r o d u c t _ n a m e :   s t r )   - >   L i s t [ s t r ] :  
                 " " " C o n s t r � � i   m � � l t i p l a s   U R L s   d e   b u s c a   p a r a   L G " " "  
                 e n c o d e d _ q u e r y   =   u r l l i b . p a r s e . q u o t e ( p r o d u c t _ n a m e ,   s a f e = ' ' )  
                  
                 u r l s   =   [  
                         #   U R L   d e   b u s c a   p r i n c i p a l  
                         f " h t t p s : / / w w w . l g . c o m / b r / b u s c a ? q = { e n c o d e d _ q u e r y } " ,  
                         #   U R L s   a l t e r n a t i v a s  
                         f " h t t p s : / / w w w . l g . c o m / b r / s e a r c h ? q u e r y = { e n c o d e d _ q u e r y } " ,  
                         f " h t t p s : / / w w w . l g . c o m / b r / p r o d u t o s ? s e a r c h = { e n c o d e d _ q u e r y } " ,  
                 ]  
                  
                 r e t u r n   u r l s  
  
         a s y n c   d e f   s c r a p e _ w i t h _ s e l e n i u m _ w a i t ( s e l f ,   u r l :   s t r ,   m a x _ r e s u l t s :   i n t )   - >   L i s t [ P r o d u c t I n f o ] :  
                 " " " S c r a p i n g   c o m   S e l e n i u m   a g u a r d a n d o   c a r r e g a m e n t o   d i n � � m i c o   p a r a   L G " " "  
                 f r o m   s e l e n i u m   i m p o r t   w e b d r i v e r  
                 f r o m   s e l e n i u m . w e b d r i v e r . c h r o m e . o p t i o n s   i m p o r t   O p t i o n s  
                 f r o m   s e l e n i u m . w e b d r i v e r . c o m m o n . b y   i m p o r t   B y  
                 f r o m   s e l e n i u m . w e b d r i v e r . s u p p o r t . u i   i m p o r t   W e b D r i v e r W a i t  
                 f r o m   s e l e n i u m . w e b d r i v e r . s u p p o r t   i m p o r t   e x p e c t e d _ c o n d i t i o n s   a s   E C  
                 i m p o r t   t i m e  
                  
                 l o g g e r . i n f o ( f " I n i c i a n d o   s c r a p i n g   L G   c o m   S e l e n i u m   ( w a i t ) :   { u r l } " )  
                  
                 c h r o m e _ o p t i o n s   =   O p t i o n s ( )  
                 c h r o m e _ o p t i o n s . a d d _ a r g u m e n t ( " - - h e a d l e s s " )  
                 c h r o m e _ o p t i o n s . a d d _ a r g u m e n t ( " - - n o - s a n d b o x " )  
                 c h r o m e _ o p t i o n s . a d d _ a r g u m e n t ( " - - d i s a b l e - d e v - s h m - u s a g e " )  
                 c h r o m e _ o p t i o n s . a d d _ a r g u m e n t ( " - - d i s a b l e - g p u " )  
                 c h r o m e _ o p t i o n s . a d d _ a r g u m e n t ( " - - w i n d o w - s i z e = 1 9 2 0 , 1 0 8 0 " )  
                 c h r o m e _ o p t i o n s . a d d _ a r g u m e n t ( f " - - u s e r - a g e n t = { s e l f . c o n f i g . h e a d e r s [ ' U s e r - A g e n t ' ] } " )  
                  
                 d r i v e r   =   N o n e  
                 t r y :  
                         d r i v e r   =   w e b d r i v e r . C h r o m e ( o p t i o n s = c h r o m e _ o p t i o n s )  
                         d r i v e r . g e t ( u r l )  
                          
                         #   A g u a r d a   c a r r e g a m e n t o   i n i c i a l  
                         t i m e . s l e e p ( 5 )  
                          
                         l o g g e r . i n f o ( " A g u a r d a n d o   c a r r e g a m e n t o   d i n � � m i c o   d o s   p r o d u t o s   L G . . . " )  
                          
                         #   A g u a r d a   e l e m e n t o s   d e   p r o d u t o   a p a r e c e r e m   ( m � � l t i p l o s   s e l e t o r e s )  
                         s e l e c t o r s _ t o _ w a i t   =   [  
                                 " . p r o d u c t - i t e m " ,  
                                 " . p r o d u c t - c a r d " ,    
                                 " . p r o d u c t " ,  
                                 " [ c l a s s * = ' p r o d u c t ' ] " ,  
                                 " . s e a r c h - r e s u l t - i t e m "  
                         ]  
                          
                         e l e m e n t s _ f o u n d   =   F a l s e  
                         f o r   s e l e c t o r   i n   s e l e c t o r s _ t o _ w a i t :  
                                 t r y :  
                                         W e b D r i v e r W a i t ( d r i v e r ,   1 0 ) . u n t i l (  
                                                 E C . p r e s e n c e _ o f _ e l e m e n t _ l o c a t e d ( ( B y . C S S _ S E L E C T O R ,   s e l e c t o r ) )  
                                         )  
                                         e l e m e n t s   =   d r i v e r . f i n d _ e l e m e n t s ( B y . C S S _ S E L E C T O R ,   s e l e c t o r )  
                                         i f   e l e m e n t s :  
                                                 l o g g e r . i n f o ( f " E n c o n t r a d o s   e l e m e n t o s   L G   c o m   s e l e t o r :   { s e l e c t o r } " )  
                                                 e l e m e n t s _ f o u n d   =   T r u e  
                                                 b r e a k  
                                 e x c e p t :  
                                         c o n t i n u e  
                          
                         i f   n o t   e l e m e n t s _ f o u n d :  
                                 l o g g e r . w a r n i n g ( " L G :   N e n h u m   p r o d u t o   e n c o n t r a d o   c o m   s e l e t o r e s   d i n � � m i c o s " )  
                                 t i m e . s l e e p ( 8 )     #   A g u a r d a   m a i s   t e m p o  
  
                         #   D e b u g :   V a m o s   i n s p e c i o n a r   a   e s t r u t u r a   H T M L  
                         l o g g e r . i n f o ( " � x �   D E B U G :   I n s p e c i o n a n d o   e s t r u t u r a   L G . . . " )  
                          
                         #   V e r i f i c a r   e l e m e n t o s   d e   p r o d u t o   n a   p � � g i n a  
                         p r o d u c t _ e l e m e n t s   =   d r i v e r . f i n d _ e l e m e n t s ( B y . C S S _ S E L E C T O R ,    
                                 " . p r o d u c t - i t e m ,   . p r o d u c t - c a r d ,   . p r o d u c t ,   [ c l a s s * = ' p r o d u c t ' ] ,   . s e a r c h - r e s u l t - i t e m " )  
                         l o g g e r . i n f o ( f " � x �   E n c o n t r a d o s   { l e n ( p r o d u c t _ e l e m e n t s ) }   e l e m e n t o s   d e   p r o d u t o " )  
                          
                         #   D e b u g   m a i s   d e t a l h a d o :   e x a m i n a r   o   H T M L   d o s   p r i m e i r o s   2   e l e m e n t o s  
                         i f   p r o d u c t _ e l e m e n t s :  
                                 f o r   i d x   i n   r a n g e ( m i n ( 2 ,   l e n ( p r o d u c t _ e l e m e n t s ) ) ) :  
                                         e l e m e n t   =   p r o d u c t _ e l e m e n t s [ i d x ]  
                                         h t m l _ c o n t e n t   =   e l e m e n t . g e t _ a t t r i b u t e ( ' o u t e r H T M L ' )  
                                          
                                         #   B u s c a r   t o d o s   o s   l i n k s   d e n t r o   d e s t e   e l e m e n t o  
                                         l i n k s   =   e l e m e n t . f i n d _ e l e m e n t s ( B y . T A G _ N A M E ,   " a " )  
                                         l o g g e r . i n f o ( f " � x    E l e m e n t o   { i d x + 1 } :   { l e n ( l i n k s ) }   l i n k s   e n c o n t r a d o s " )  
                                          
                                         f o r   i ,   l i n k   i n   e n u m e r a t e ( l i n k s ) :  
                                                 h r e f   =   l i n k . g e t _ a t t r i b u t e ( " h r e f " )  
                                                 t e x t   =   l i n k . t e x t [ : 3 0 ]   i f   l i n k . t e x t   e l s e   " s e m   t e x t o "  
                                                 l o g g e r . i n f o ( f "       L i n k   { i + 1 } :   h r e f = ' { h r e f } '   t e x t o = ' { t e x t } ' " )  
                                          
                                         #   E x i b i r   p a r t e   d o   H T M L   p a r a   a n � � l i s e  
                                         l o g g e r . i n f o ( f " � x �   H T M L   d o   e l e m e n t o   { i d x + 1 }   ( p r i m e i r o s   8 0 0   c h a r s ) : " )  
                                         l o g g e r . i n f o ( f " { h t m l _ c o n t e n t [ : 8 0 0 ] } . . . " )  
  
                         #   E s t r a t � � g i a   e s p e c � � f i c a   p a r a   L G :   s i m u l a r   c l i q u e s   n o s   e l e m e n t o s   s e   n e c e s s � � r i o  
                         l g _ p r o d u c t s _ d a t a   =   [ ]  
                          
                         i f   p r o d u c t _ e l e m e n t s :  
                                 c u r r e n t _ u r l   =   d r i v e r . c u r r e n t _ u r l  
                                  
                                 f o r   i   i n   r a n g e ( m i n ( 5 ,   l e n ( p r o d u c t _ e l e m e n t s ) ) ) :     #   P r o c e s s a r   a p e n a s   o s   p r i m e i r o s   5  
                                         t r y :  
                                                 l o g g e r . i n f o ( f " � x}�   T e n t a n d o   e x t r a i r   U R L   d o   p r o d u t o   L G   { i + 1 } . . . " )  
                                                  
                                                 #   R e - l o c a l i z a r   e l e m e n t o s   a   c a d a   i t e r a � � � � o   p a r a   e v i t a r   s t a l e   r e f e r e n c e s  
                                                 e l e m e n t s _ f r e s h   =   d r i v e r . f i n d _ e l e m e n t s ( B y . C S S _ S E L E C T O R ,    
                                                         " . p r o d u c t - i t e m ,   . p r o d u c t - c a r d ,   . p r o d u c t ,   [ c l a s s * = ' p r o d u c t ' ] ,   . s e a r c h - r e s u l t - i t e m " )  
                                                  
                                                 i f   i   > =   l e n ( e l e m e n t s _ f r e s h ) :  
                                                         l o g g e r . w a r n i n g ( f " P r o d u t o   { i + 1 } :   N � � o   h � �   m a i s   e l e m e n t o s   d i s p o n � � v e i s " )  
                                                         b r e a k  
                                                          
                                                 e l e m e n t   =   e l e m e n t s _ f r e s h [ i ]  
                                                  
                                                 #   P r i m e i r o   t e n t a r   e n c o n t r a r   l i n k s   d i r e t o s  
                                                 l i n k s _ i n _ e l e m e n t   =   e l e m e n t . f i n d _ e l e m e n t s ( B y . T A G _ N A M E ,   " a " )  
                                                 p r o d u c t _ u r l   =   N o n e  
                                                  
                                                 f o r   l i n k   i n   l i n k s _ i n _ e l e m e n t :  
                                                         h r e f   =   l i n k . g e t _ a t t r i b u t e ( " h r e f " )  
                                                         i f   h r e f   a n d   ( ' / p r o d u t o '   i n   h r e f   o r   ' / p r o d u c t s '   i n   h r e f   o r   ' p r o d u c t I d '   i n   h r e f ) :  
                                                                 p r o d u c t _ u r l   =   h r e f  
                                                                 b r e a k  
                                                  
                                                 i f   p r o d u c t _ u r l :  
                                                         l g _ p r o d u c t s _ d a t a . a p p e n d ( {  
                                                                 ' e l e m e n t _ i n d e x ' :   i ,  
                                                                 ' u r l ' :   p r o d u c t _ u r l  
                                                         } )  
                                                         l o g g e r . i n f o ( f " � S&   U R L   d i r e t a   e n c o n t r a d a   p a r a   p r o d u t o   { i + 1 } :   { p r o d u c t _ u r l } " )  
                                                 e l s e :  
                                                         #   S e   n � � o   e n c o n t r a r   l i n k   d i r e t o ,   t e n t a r   c l i c a r   n o   e l e m e n t o  
                                                         t r y :  
                                                                 #   S c r o l l   p a r a   o   e l e m e n t o  
                                                                 d r i v e r . e x e c u t e _ s c r i p t ( " a r g u m e n t s [ 0 ] . s c r o l l I n t o V i e w ( t r u e ) ; " ,   e l e m e n t )  
                                                                 t i m e . s l e e p ( 1 )  
                                                                  
                                                                 #   C a p t u r a r   U R L   a n t e s   d o   c l i q u e  
                                                                 u r l _ b e f o r e   =   d r i v e r . c u r r e n t _ u r l  
                                                                  
                                                                 #   C l i c a r   n o   e l e m e n t o  
                                                                 e l e m e n t . c l i c k ( )  
                                                                 t i m e . s l e e p ( 3 )     #   A g u a r d a r   n a v e g a � � � � o  
                                                                  
                                                                 #   C a p t u r a r   U R L   a p � � s   o   c l i q u e  
                                                                 u r l _ a f t e r   =   d r i v e r . c u r r e n t _ u r l  
                                                                  
                                                                 i f   u r l _ a f t e r   ! =   u r l _ b e f o r e   a n d   ( ' / p r o d u t o '   i n   u r l _ a f t e r   o r   ' / p r o d u c t s '   i n   u r l _ a f t e r   o r   ' p r o d u c t I d '   i n   u r l _ a f t e r ) :  
                                                                         l g _ p r o d u c t s _ d a t a . a p p e n d ( {  
                                                                                 ' e l e m e n t _ i n d e x ' :   i ,  
                                                                                 ' u r l ' :   u r l _ a f t e r  
                                                                         } )  
                                                                          
                                                                         l o g g e r . i n f o ( f " � S&   U R L   v i a   c l i q u e   e n c o n t r a d a   p a r a   p r o d u t o   { i + 1 } :   { u r l _ a f t e r } " )  
                                                                 e l s e :  
                                                                         l o g g e r . w a r n i n g ( f " � � R  U R L   n � � o   m u d o u   p a r a   p r o d u t o   { i + 1 } :   { u r l _ a f t e r } " )  
                                                                  
                                                                 #   V o l t a r   p a r a   p � � g i n a   d e   b u s c a  
                                                                 d r i v e r . g e t ( c u r r e n t _ u r l )  
                                                                 t i m e . s l e e p ( 3 )     #   A g u a r d a r   c a r r e g a m e n t o   c o m p l e t o  
                                                                  
                                                         e x c e p t   E x c e p t i o n   a s   e :  
                                                                 l o g g e r . w a r n i n g ( f " E r r o   a o   c l i c a r   n o   p r o d u t o   L G   { i + 1 } :   { s t r ( e ) } " )  
                                                                 t r y :  
                                                                         d r i v e r . g e t ( c u r r e n t _ u r l )  
                                                                         t i m e . s l e e p ( 2 )  
                                                                 e x c e p t :  
                                                                         p a s s  
                                                  
                                         e x c e p t   E x c e p t i o n   a s   e :  
                                                 l o g g e r . w a r n i n g ( f " E r r o   a o   p r o c e s s a r   p r o d u t o   L G   { i + 1 } :   { s t r ( e ) } " )  
                                                 c o n t i n u e  
                                  
                                 l o g g e r . i n f o ( f " � x}�   E n c o n t r a d a s   { l e n ( l g _ p r o d u c t s _ d a t a ) }   U R L s   r e a i s   p a r a   p r o d u t o s   L G " )  
                          
                         #   P e g a   o   H T M L   f i n a l  
                         h t m l   =   d r i v e r . p a g e _ s o u r c e  
                         s o u p   =   B e a u t i f u l S o u p ( h t m l ,   " h t m l . p a r s e r " )  
                          
                         #   E x t r a i   p r o d u t o s   p a s s a n d o   o s   d a d o s   d e   U R L s   e s p e c � � f i c a s  
                         p r o d u c t s   =   s e l f . e x t r a c t _ p r o d u c t _ i n f o ( s o u p ,   u r l ,   m a x _ r e s u l t s ,   l g _ p r o d u c t s _ d a t a )  
                          
                         l o g g e r . s u c c e s s ( f " S c r a p i n g   L G   S e l e n i u m   c o n c l u � � d o :   { l e n ( p r o d u c t s ) }   p r o d u t o s   e n c o n t r a d o s " )  
                         r e t u r n   p r o d u c t s  
  
                 e x c e p t   E x c e p t i o n   a s   e :  
                         l o g g e r . e r r o r ( f " E r r o   d u r a n t e   s c r a p i n g   L G   c o m   S e l e n i u m :   { s t r ( e ) } " )  
                         r e t u r n   [ ]  
  
                 f i n a l l y :  
                         i f   d r i v e r :  
                                 d r i v e r . q u i t ( )  
  
         d e f   e x t r a c t _ p r o d u c t _ i n f o ( s e l f ,   s o u p :   B e a u t i f u l S o u p ,   s e a r c h _ u r l :   s t r ,   m a x _ r e s u l t s :   i n t ,   u r l s _ d a t a :   L i s t [ d i c t ]   =   N o n e )   - >   L i s t [ P r o d u c t I n f o ] :  
                 " " " E x t r a i   i n f o r m a � � � � e s   d o s   p r o d u t o s   d a   L G   d o   H T M L " " "  
                 p r o d u c t s   =   [ ]  
                 s e e n _ u r l s   =   s e t ( )  
  
                 l o g g e r . i n f o ( f " I n i c i a n d o   e x t r a � � � � o   d e   p r o d u t o s   L G . . . " )  
  
                 #   C r i a r   m a p a   d e   U R L s   e s p e c � � f i c a s   s e   f o r n e c i d o  
                 u r l _ m a p   =   { }  
                 i f   u r l s _ d a t a :  
                         f o r   i t e m   i n   u r l s _ d a t a :  
                                 u r l _ m a p [ i t e m [ ' e l e m e n t _ i n d e x ' ] ]   =   i t e m [ ' u r l ' ]  
                         l o g g e r . i n f o ( f " � x 9   U s a n d o   { l e n ( u r l _ m a p ) }   U R L s   e s p e c � � f i c a s   m a p e a d a s " )  
  
                 #   M � � l t i p l o s   s e l e t o r e s   p a r a   e n c o n t r a r   c o n t a i n e r s   d e   p r o d u t o s  
                 c o n t a i n e r _ s e l e c t o r s   =   [  
                         " . p r o d u c t - i t e m " ,  
                         " . p r o d u c t - c a r d " ,  
                         " . p r o d u c t " ,    
                         " [ c l a s s * = ' p r o d u c t ' ] " ,  
                         " . s e a r c h - r e s u l t - i t e m " ,  
                         " a r t i c l e " ,  
                         " . i t e m - c a r d " ,  
                         " [ d a t a - p r o d u c t - i d ] "  
                 ]  
  
                 c o n t a i n e r s   =   [ ]  
                 u s e d _ s e l e c t o r   =   N o n e  
  
                 f o r   s e l e c t o r   i n   c o n t a i n e r _ s e l e c t o r s :  
                         c o n t a i n e r s   =   s o u p . s e l e c t ( s e l e c t o r )  
                         i f   c o n t a i n e r s :  
                                 u s e d _ s e l e c t o r   =   s e l e c t o r  
                                 l o g g e r . i n f o ( f " L G :   U s a n d o   s e l e t o r   ' { s e l e c t o r } '   -   { l e n ( c o n t a i n e r s ) }   c o n t a i n e r s " )  
                                 b r e a k  
  
                 i f   n o t   c o n t a i n e r s :  
                         l o g g e r . w a r n i n g ( " L G :   N e n h u m   c o n t a i n e r   d e   p r o d u t o   e n c o n t r a d o " )  
                         r e t u r n   [ ]  
  
                 l o g g e r . i n f o ( f " E n c o n t r a d o s   { l e n ( c o n t a i n e r s ) }   p r o d u t o s   n a   L G " )  
  
                 f o r   i ,   c o n t a i n e r   i n   e n u m e r a t e ( c o n t a i n e r s [ : m a x _ r e s u l t s   *   3 ] ) :     #   P r o c e s s a   m a i s   p a r a   f i l t r a r  
                         i f   l e n ( p r o d u c t s )   > =   m a x _ r e s u l t s :  
                                 b r e a k  
  
                         t r y :  
                                 #   U s a r   U R L   e s p e c � � f i c a   s e   d i s p o n � � v e l   n o   m a p a  
                                 s p e c i f i c _ u r l   =   u r l _ m a p . g e t ( i )   i f   u r l _ m a p   e l s e   N o n e  
                                  
                                 #   N o m e   d o   p r o d u t o   -   m � � l t i p l a s   t e n t a t i v a s  
                                 n a m e   =   " "  
                                 n a m e _ s e l e c t o r s   =   [  
                                         " h 1 " ,   " h 2 " ,   " h 3 " ,   " h 4 " ,  
                                         " . p r o d u c t - t i t l e " ,   " . p r o d u c t - n a m e " ,   " . i t e m - t i t l e " ,   " . i t e m - n a m e " ,  
                                         " . t i t l e " ,   " . n a m e " ,   " [ d a t a - t e s t i d * = ' t i t l e ' ] " ,   " [ d a t a - t e s t i d * = ' n a m e ' ] " ,  
                                         " a [ t i t l e ] " ,   " [ a r i a - l a b e l ] "  
                                 ]  
  
                                 f o r   n a m e _ s e l   i n   n a m e _ s e l e c t o r s :  
                                         n a m e _ e l e m e n t   =   c o n t a i n e r . s e l e c t _ o n e ( n a m e _ s e l )  
                                         i f   n a m e _ e l e m e n t   a n d   n a m e _ e l e m e n t . g e t _ t e x t ( s t r i p = T r u e ) :  
                                                 n a m e   =   n a m e _ e l e m e n t . g e t _ t e x t ( s t r i p = T r u e )  
                                                 b r e a k  
                                         e l i f   n a m e _ e l e m e n t   a n d   n a m e _ e l e m e n t . g e t ( " t i t l e " ) :  
                                                 n a m e   =   n a m e _ e l e m e n t [ " t i t l e " ] . s t r i p ( )  
                                                 b r e a k  
                                         e l i f   n a m e _ e l e m e n t   a n d   n a m e _ e l e m e n t . g e t ( " a r i a - l a b e l " ) :  
                                                 n a m e   =   n a m e _ e l e m e n t [ " a r i a - l a b e l " ] . s t r i p ( )  
                                                 b r e a k  
  
                                 i f   n o t   n a m e   o r   l e n ( n a m e )   <   3 :  
                                         c o n t i n u e  
  
                                 #   P r e � � o   d o   p r o d u t o  
                                 p r i c e   =   N o n e  
                                 p r i c e _ s e l e c t o r s   =   [  
                                         " [ d a t a - t e s t i d * = ' p r i c e ' ] " ,  
                                         " . p r i c e - c u r r e n t " ,   " . s a l e s - p r i c e " ,   " . p r i c e " ,   " . v a l u e " ,  
                                         " . p r e c o " ,   " . v a l o r " ,   " [ c l a s s * = ' p r i c e ' ] " ,  
                                         " . p d - p r i c e " ,   " . p r o d u c t - p r i c e " ,  
                                         " s p a n [ c l a s s * = ' p r i c e ' ] " ,   " d i v [ c l a s s * = ' p r i c e ' ] " ,  
                                         " s t r o n g " ,   " b "  
                                 ]  
  
                                 f o r   p r i c e _ s e l   i n   p r i c e _ s e l e c t o r s :  
                                         p r i c e _ e l e m e n t s   =   c o n t a i n e r . s e l e c t ( p r i c e _ s e l )  
                                         f o r   p r i c e _ e l e m   i n   p r i c e _ e l e m e n t s :  
                                                 t e x t   =   p r i c e _ e l e m . g e t _ t e x t ( s t r i p = T r u e )  
                                                 i f   t e x t   a n d   ( " R $ "   i n   t e x t   o r   " , "   i n   t e x t   o r   t e x t . r e p l a c e ( " . " ,   " " ) . i s d i g i t ( ) ) :  
                                                         p r i c e   =   s e l f . _ e x t r a c t _ p r i c e ( t e x t )  
                                                         i f   p r i c e :  
                                                                 b r e a k  
                                         i f   p r i c e :  
                                                 b r e a k  
  
                                 i f   n o t   p r i c e :  
                                         c o n t i n u e  
  
                                 #   U R L   d o   p r o d u t o   -   m � � l t i p l a s   e s t r a t � � g i a s  
                                 u r l   =   s p e c i f i c _ u r l   i f   s p e c i f i c _ u r l   e l s e   " "  
                                  
                                 i f   n o t   u r l :  
                                         #   1 .   B u s c a r   l i n k s   e s p e c � � f i c o s   c o m   p a d r � � e s   L G  
                                         l i n k _ s e l e c t o r s   =   [  
                                                 " a [ h r e f * = ' / p r o d u t o ' ] " ,     #   L i n k s   q u e   c o n t � � m   ' / p r o d u t o '  
                                                 " a [ h r e f * = ' / p r o d u c t s ' ] " ,     #   L i n k s   q u e   c o n t � � m   ' / p r o d u c t s '  
                                                 " a [ h r e f * = ' p r o d u c t I d ' ] " ,     #   L i n k s   q u e   c o n t � � m   ' p r o d u c t I d '  
                                                 " a [ h r e f ] " ,     #   Q u a l q u e r   l i n k  
                                         ]  
                                          
                                         f o r   l i n k _ s e l   i n   l i n k _ s e l e c t o r s :  
                                                 l i n k _ e l e m e n t s   =   c o n t a i n e r . s e l e c t ( l i n k _ s e l )     #   B u s c a r   T O D O S   o s   l i n k s  
                                                 f o r   l i n k _ e l e m e n t   i n   l i n k _ e l e m e n t s :  
                                                         h r e f   =   l i n k _ e l e m e n t . g e t ( " h r e f " )  
                                                         i f   h r e f :  
                                                                 #   V e r i f i c a r   s e   � �   u m   l i n k   d e   p r o d u t o   v � � l i d o  
                                                                 i f   ( ' / p r o d u t o '   i n   h r e f   o r   ' / p r o d u c t s '   i n   h r e f   o r   ' p r o d u c t I d '   i n   h r e f ) :  
                                                                         i f   h r e f . s t a r t s w i t h ( " / " ) :  
                                                                                 u r l   =   f " h t t p s : / / w w w . l g . c o m { h r e f } "  
                                                                         e l i f   n o t   h r e f . s t a r t s w i t h ( " h t t p " ) :  
                                                                                 u r l   =   f " h t t p s : / / w w w . l g . c o m / { h r e f } "  
                                                                         e l s e :  
                                                                                 u r l   =   h r e f  
                                                                          
                                                                         l o g g e r . d e b u g ( f " L G   U R L   r e a l   e x t r a � � d a :   { u r l [ : 1 0 0 ] } . . . " )  
                                                                         b r e a k  
                                                  
                                                 i f   u r l :     #   S e   e n c o n t r o u   U R L   v � � l i d a ,   p a r a r   d e   p r o c u r a r  
                                                         b r e a k  
                                          
                                         #   2 .   S e   n � � o   e n c o n t r a r   U R L   e s p e c � � f i c a ,   u s a r   s e a r c h _ u r l   c o m o   � � l t i m o   r e c u r s o  
                                         i f   n o t   u r l :  
                                                 l o g g e r . w a r n i n g ( f " L G :   N e n h u m a   U R L   e s p e c � � f i c a   e n c o n t r a d a   p a r a :   { n a m e [ : 3 0 ] } . . . " )  
                                                 u r l   =   s e a r c h _ u r l  
                                 e l s e :  
                                         l o g g e r . d e b u g ( f " L G   U R L   e s p e c � � f i c a   d o   m a p a   u s a d a :   { u r l [ : 1 0 0 ] } . . . " )  
  
                                 #   E v i t a r   d u p l i c a t a s   p o r   U R L  
                                 i f   u r l   a n d   u r l   i n   s e e n _ u r l s :  
                                         c o n t i n u e  
                                 i f   u r l :  
                                         s e e n _ u r l s . a d d ( u r l )  
  
                                 #   I m a g e m   d o   p r o d u t o  
                                 i m a g e _ u r l   =   " "  
                                 i m g _ e l e m e n t   =   c o n t a i n e r . s e l e c t _ o n e ( " i m g [ s r c ] ,   i m g [ d a t a - s r c ] ,   i m g [ d a t a - l a z y - s r c ] " )  
                                 i f   i m g _ e l e m e n t :  
                                         i m a g e _ u r l   =   ( i m g _ e l e m e n t . g e t ( " s r c " )   o r    
                                                                 i m g _ e l e m e n t . g e t ( " d a t a - s r c " )   o r    
                                                                 i m g _ e l e m e n t . g e t ( " d a t a - l a z y - s r c " ,   " " ) )  
                                         i f   i m a g e _ u r l   a n d   n o t   i m a g e _ u r l . s t a r t s w i t h ( " h t t p " ) :  
                                                 i f   i m a g e _ u r l . s t a r t s w i t h ( " / / " ) :  
                                                         i m a g e _ u r l   =   f " h t t p s : { i m a g e _ u r l } "  
                                                 e l i f   i m a g e _ u r l . s t a r t s w i t h ( " / " ) :  
                                                         i m a g e _ u r l   =   f " h t t p s : / / w w w . l g . c o m { i m a g e _ u r l } "  
  
                                 #   V a l i d a � � � � o   f i n a l   -   s � �   a d i c i o n a   p r o d u t o s   c o m   i n f o r m a � � � � e s   m � � n i m a s  
                                 i f   n a m e   a n d   p r i c e   a n d   l e n ( n a m e )   > =   3 :  
                                         #   P r e f e r i r   p r o d u t o s   c o m   U R L   e s p e c � � f i c a ,   m a s   a c e i t a r   s e a r c h _ u r l   s e   n e c e s s � � r i o  
                                         f i n a l _ u r l   =   u r l   i f   u r l   a n d   u r l   ! =   s e a r c h _ u r l   e l s e   s e a r c h _ u r l  
                                          
                                         p r o d u c t   =   P r o d u c t I n f o (  
                                                 n a m e = n a m e ,  
                                                 p r i c e = p r i c e ,  
                                                 u r l = f i n a l _ u r l ,  
                                                 i m a g e _ u r l = i m a g e _ u r l   i f   i m a g e _ u r l   e l s e   N o n e ,  
                                                 s i t e = " L G " ,  
                                                 a v a i l a b i l i t y = " D i s p o n � � v e l " ,  
                                         )  
                                         p r o d u c t s . a p p e n d ( p r o d u c t )  
                                          
                                         u r l _ t y p e   =   " e s p e c � � f i c a "   i f   f i n a l _ u r l   ! =   s e a r c h _ u r l   e l s e   " b u s c a "  
                                         l o g g e r . d e b u g ( f " � S&   P r o d u t o   L G   v � � l i d o   ( { u r l _ t y p e } ) :   { n a m e [ : 5 0 ] } . . .   -   R $   { p r i c e } " )  
  
                         e x c e p t   E x c e p t i o n   a s   e :  
                                 l o g g e r . w a r n i n g ( f " E r r o   a o   p r o c e s s a r   p r o d u t o   L G :   { s t r ( e ) } " )  
                                 c o n t i n u e  
  
                 l o g g e r . i n f o ( f " E x t r a � � d o s   { l e n ( p r o d u c t s ) }   p r o d u t o s   v � � l i d o s   d a   L G " )  
                 r e t u r n   p r o d u c t s  
  
         d e f   _ e x t r a c t _ p r i c e ( s e l f ,   p r i c e _ t e x t :   s t r )   - >   O p t i o n a l [ f l o a t ] :  
                 " " " E x t r a i   v a l o r   n u m � � r i c o   d o   t e x t o   d e   p r e � � o " " "  
                 i f   n o t   p r i c e _ t e x t :  
                         r e t u r n   N o n e  
  
                 #   R e m o v e   c a r a c t e r e s   n � � o   n u m � � r i c o s   e x c e t o   v � � r g u l a s   e   p o n t o s  
                 i m p o r t   r e  
                 c l e a n e d   =   r e . s u b ( r " [ ^ \ d , . ] " ,   " " ,   p r i c e _ t e x t )  
  
                 #   T r a t a   d i f e r e n t e s   f o r m a t o s   d e   p r e � � o   b r a s i l e i r o s  
                 i f   " , "   i n   c l e a n e d   a n d   " . "   i n   c l e a n e d :  
                         #   F o r m a t o :   1 . 2 3 4 , 5 6  
                         c l e a n e d   =   c l e a n e d . r e p l a c e ( " . " ,   " " ) . r e p l a c e ( " , " ,   " . " )  
                 e l i f   " , "   i n   c l e a n e d :  
                         #   F o r m a t o :   1 2 3 4 , 5 6  
                         c l e a n e d   =   c l e a n e d . r e p l a c e ( " , " ,   " . " )  
  
                 t r y :  
                         r e t u r n   f l o a t ( c l e a n e d )  
                 e x c e p t   V a l u e E r r o r :  
                         l o g g e r . d e b u g ( f " N � � o   f o i   p o s s � � v e l   e x t r a i r   p r e � � o   d e :   { p r i c e _ t e x t } " )  
                         r e t u r n   N o n e  
 