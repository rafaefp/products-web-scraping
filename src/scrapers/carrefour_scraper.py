from typing import List, Optional
import urllib.parse
import re
import time
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from ..models import ProductInfo, SiteConfig


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
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"Encontrados elementos com seletor: {selector}")
                        products_found = True
                        break
                except:
                    continue

            if not products_found:
                logger.warning(
                    "Carregamento dinâmico: Nenhum produto encontrado com seletores dinâmicos"
                )

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
                    logger.info(f"Carrefour: Usando seletor fallback '{selector}'")
                    break

        logger.info(f"Encontrados {len(product_containers)} produtos no Carrefour")

        for container in product_containers:
            try:
                # Título
                title = None
                for title_selector in self.config.selectors["title"].split(", "):
                    title_elem = container.select_one(title_selector.strip())
                    if title_elem and title_elem.get_text(strip=True):
                        title = title_elem.get_text(strip=True)
                        break

                if not title:
                    continue

                # Preço
                price = None
                price_selectors = [
                    ".vtex-product-price-1-x-currencyInteger",
                    ".vtex-product-price-1-x-sellingPriceValue",
                    "[data-testid*='price']",
                    ".price",
                    "span:contains('R$')",
                ]

                for price_selector in price_selectors:
                    price_elem = container.select_one(price_selector)
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        if "R$" in price_text or "," in price_text:
                            price = self._extract_price(price_text)
                            if price:
                                break

                if not price:
                    continue

                # URL do produto
                product_url = None
                if container.name == "a" and container.get("href"):
                    product_url = container["href"]
                else:
                    link_elem = container.select_one("a[href]")
                    if link_elem:
                        product_url = link_elem["href"]

                if product_url and not product_url.startswith("http"):
                    product_url = f"https://www.carrefour.com.br{product_url}"

                # Imagem
                image_url = None
                img_elem = container.select_one("img[src], img[data-src]")
                if img_elem:
                    image_url = img_elem.get("src") or img_elem.get("data-src")

                if title and price:
                    product = ProductInfo(
                        name=title,
                        price=price,
                        url=product_url or base_url,
                        image_url=image_url,
                        site=self.config.name,
                        availability="Disponível",
                    )
                    products.append(product)

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
