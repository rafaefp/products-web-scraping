from typing import List, Optional
import urllib.parse
import re
import time
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from ..models import ProductInfo, SiteConfig


class LGScraper(BaseScraper):
    """
    Scraper específico para LG Brasil

    Desafio: LG possui e-commerce, mas sem funcionalidade de busca unificada.
    Os produtos estão organizados em dezenas de categorias específicas,
    exigindo navegação manual por cada subcategoria para encontrar itens.

    Para implementação futura: mapear todas as categorias/subcategorias
    do site LG para permitir busca efetiva por tipo de produto.
    """

    def __init__(self):
        config = SiteConfig(
            name="LG",
            base_url="https://www.lg.com",
            search_url_pattern="https://www.lg.com/br/produtos/",
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
        """Constrói URL de busca da LG"""
        encoded_query = urllib.parse.quote(product_name, safe="")
        return self.config.search_url_pattern.format(query=encoded_query)

    async def scrape(
        self, product_name: str, max_results: int = 10
    ) -> List[ProductInfo]:
        """Override do método scrape - LG requer navegação por categorias específicas"""
        logger.info(f"Iniciando scraping {self.config.name} para: {product_name}")

        # LG Brasil possui e-commerce, mas sem funcionalidade de busca unificada
        # Seria necessário navegar por dezenas de categorias específicas
        logger.warning(
            "LG Brasil: E-commerce com navegação por categorias específicas - sem busca unificada"
        )
        logger.info(
            "LG requer navegação manual por categorias para encontrar produtos específicos"
        )
        logger.info(
            "Para implementação futura: mapear todas as subcategorias LG para busca efetiva"
        )

        return []

    def _build_multiple_search_urls(self, product_name: str) -> List[str]:
        """Constrói múltiplas URLs baseadas em categorias LG"""

        # Mapeamento de queries para categorias da LG
        category_mapping = {
            "tv": [
                "https://www.lg.com/br/tvs/",
                "https://www.lg.com/br/tvs-e-soundbars/",
            ],
            "televisao": [
                "https://www.lg.com/br/tvs/",
                "https://www.lg.com/br/tvs-e-soundbars/",
            ],
            "smart tv": [
                "https://www.lg.com/br/tvs/",
                "https://www.lg.com/br/tvs-e-soundbars/",
            ],
            "monitor": ["https://www.lg.com/br/monitores/"],
            "refrigerador": ["https://www.lg.com/br/refrigeradores/"],
            "geladeira": ["https://www.lg.com/br/refrigeradores/"],
            "ar condicionado": ["https://www.lg.com/br/ar-condicionado/"],
            "notebook": ["https://www.lg.com/br/computadores/"],
            "celular": ["https://www.lg.com/br/celulares/"],
            "smartphone": ["https://www.lg.com/br/celulares/"],
        }

        query_lower = product_name.lower()
        urls = []

        # Procura por correspondências exatas ou parciais
        for key, category_urls in category_mapping.items():
            if key in query_lower:
                urls.extend(category_urls)
                break

        # Se não encontrou categoria específica, usa URL genérica de produtos
        if not urls:
            urls = ["https://www.lg.com/br/produtos/"]

        return list(set(urls))  # Remove duplicatas

    async def scrape_with_selenium_wait(
        self, url: str, max_results: int
    ) -> List[ProductInfo]:
        """Scraping com Selenium aguardando carregamento dinâmico para LG"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        logger.info(f"Iniciando scraping LG com Selenium: {url}")

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
            time.sleep(5)

            logger.info("Aguardando carregamento dinâmico dos produtos LG...")

            selectors_to_wait = [
                ".product-item",
                ".product-card",
                ".product",
                "[class*='product']",
                ".search-result-item",
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
                logger.warning("LG: Nenhum produto encontrado com seletores dinâmicos")
                time.sleep(8)

            # Estratégia específica para LG: simular cliques nos elementos se necessário
            product_elements = driver.find_elements(
                By.CSS_SELECTOR,
                ".product-item, .product-card, .product, [class*='product'], .search-result-item",
            )

            lg_products_data = []

            if product_elements:
                current_url = driver.current_url

                for i in range(min(5, len(product_elements))):
                    try:
                        logger.info(f"Tentando extrair URL do produto LG {i+1}...")

                        elements_fresh = driver.find_elements(
                            By.CSS_SELECTOR,
                            ".product-item, .product-card, .product, [class*='product'], .search-result-item",
                        )

                        if i >= len(elements_fresh):
                            break

                        element = elements_fresh[i]

                        # Primeiro tentar encontrar links diretos
                        links_in_element = element.find_elements(By.TAG_NAME, "a")
                        product_url = None

                        for link in links_in_element:
                            href = link.get_attribute("href")
                            if href and (
                                "/produto" in href
                                or "/products" in href
                                or "productId" in href
                            ):
                                product_url = href
                                break

                        if product_url:
                            lg_products_data.append(
                                {"element_index": i, "url": product_url}
                            )
                            logger.info(f"URL direta encontrada para produto {i+1}")
                        else:
                            # Se não encontrar link direto, tentar clicar no elemento
                            try:
                                driver.execute_script(
                                    "arguments[0].scrollIntoView(true);", element
                                )
                                time.sleep(1)

                                url_before = driver.current_url
                                element.click()
                                time.sleep(3)
                                url_after = driver.current_url

                                if url_after != url_before and (
                                    "/produto" in url_after or "/products" in url_after
                                ):
                                    lg_products_data.append(
                                        {"element_index": i, "url": url_after}
                                    )
                                    logger.info(
                                        f"URL via clique encontrada para produto {i+1}"
                                    )

                                driver.get(current_url)
                                time.sleep(3)

                            except Exception as e:
                                logger.warning(
                                    f"Erro ao clicar no produto LG {i+1}: {str(e)}"
                                )
                                try:
                                    driver.get(current_url)
                                    time.sleep(2)
                                except:
                                    pass

                    except Exception as e:
                        logger.warning(f"Erro ao processar produto LG {i+1}: {str(e)}")
                        continue

                logger.info(
                    f"Encontradas {len(lg_products_data)} URLs reais para produtos LG"
                )

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            products = self.extract_product_info(
                soup, url, max_results, lg_products_data
            )

            logger.success(
                f"Scraping LG Selenium concluído: {len(products)} produtos encontrados"
            )
            return products

        except Exception as e:
            logger.error(f"Erro durante scraping LG com Selenium: {str(e)}")
            return []

        finally:
            if driver:
                driver.quit()

    def extract_product_info(
        self,
        soup: BeautifulSoup,
        search_url: str,
        max_results: int,
        urls_data: List[dict] = None,
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos da LG do HTML"""
        products = []
        seen_urls = set()

        logger.info("Iniciando extração de produtos LG...")

        url_map = {}
        if urls_data:
            for item in urls_data:
                url_map[item["element_index"]] = item["url"]
            logger.info(f"Usando {len(url_map)} URLs específicas mapeadas")

        container_selectors = [
            ".product-item",
            ".product-card",
            ".product",
            "[class*='product']",
            ".search-result-item",
            "article",
            ".item-card",
            "[data-product-id]",
        ]

        containers = []
        for selector in container_selectors:
            containers = soup.select(selector)
            if containers:
                logger.info(
                    f"LG: Usando seletor '{selector}' - {len(containers)} containers"
                )
                break

        if not containers:
            logger.warning("LG: Nenhum container de produto encontrado")
            return []

        logger.info(f"Encontrados {len(containers)} produtos na LG")

        for i, container in enumerate(containers[: max_results * 3]):
            if len(products) >= max_results:
                break

            try:
                specific_url = url_map.get(i) if url_map else None

                # Nome do produto
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

                # Preço do produto
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

                # URL do produto
                url = specific_url if specific_url else ""

                if not url:
                    link_selectors = [
                        "a[href*='/produto']",
                        "a[href*='/products']",
                        "a[href*='productId']",
                        "a[href]",
                    ]

                    for link_sel in link_selectors:
                        link_elements = container.select(link_sel)
                        for link_element in link_elements:
                            href = link_element.get("href")
                            if href:
                                if (
                                    "/produto" in href
                                    or "/products" in href
                                    or "productId" in href
                                ):
                                    if href.startswith("/"):
                                        url = f"https://www.lg.com{href}"
                                    elif not href.startswith("http"):
                                        url = f"https://www.lg.com/{href}"
                                    else:
                                        url = href
                                    break
                        if url:
                            break

                    if not url:
                        url = search_url

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
                            image_url = f"https://www.lg.com{image_url}"

                if name and price and len(name) >= 3:
                    final_url = url if url and url != search_url else search_url

                    product = ProductInfo(
                        name=name,
                        price=price,
                        url=final_url,
                        image_url=image_url if image_url else None,
                        site="LG",
                        availability="Disponível",
                    )
                    products.append(product)

            except Exception as e:
                logger.warning(f"Erro ao processar produto LG: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos da LG")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço"""
        if not price_text:
            return None

        import re

        cleaned = re.sub(r"[^\d,.]", "", price_text)

        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")

        try:
            return float(cleaned)
        except ValueError:
            logger.debug(f"Não foi possível extrair preço de: {price_text}")
            return None
