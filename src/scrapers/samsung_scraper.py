from typing import List, Optional
import urllib.parse
import re
import time
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from ..models import ProductInfo, SiteConfig


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
                products = await self.scrape_with_selenium_wait(search_url, max_results)

                if products:
                    all_products.extend(products)
                    logger.info(
                        f"Samsung: Encontrados {len(products)} produtos na URL: {search_url}"
                    )
                    break  # Se encontrou produtos, não precisa tentar outras URLs
                else:
                    logger.warning(
                        f"Samsung: Nenhum produto encontrado na URL: {search_url}"
                    )

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
                # Aguarda mais tempo como fallback
                time.sleep(8)

            # Estratégia específica para Samsung VTEX: simular cliques nos elementos
            samsung_products_data = []

            # Verificar todos os elementos 'article' na página
            articles = driver.find_elements(By.TAG_NAME, "article")
            logger.info(f"🔍 Encontrados {len(articles)} elementos 'article'")

            if articles:
                current_url = driver.current_url

                # Processa apenas os primeiros 5 produtos para evitar timeout
                for i in range(min(5, len(articles))):
                    try:
                        logger.info(f"Tentando extrair URL do produto Samsung {i+1}...")

                        # Busca elementos novamente para evitar stale reference
                        articles_fresh = driver.find_elements(By.TAG_NAME, "article")

                        if i >= len(articles_fresh):
                            break

                        article = articles_fresh[i]

                        # Primeiro, tenta encontrar links diretos no article com padrões Samsung específicos
                        links_in_article = article.find_elements(By.TAG_NAME, "a")
                        product_url = None

                        for link in links_in_article:
                            href = link.get_attribute("href")
                            if href:
                                # Padrões Samsung específicos
                                if (
                                    "/p?skuId=" in href
                                    or "/produto/" in href
                                    or "/br/" in href
                                    or "/p/" in href
                                ):
                                    product_url = href
                                    logger.info(
                                        f"URL direta Samsung encontrada: {href}"
                                    )
                                    break

                        if product_url:
                            samsung_products_data.append(
                                {"element_index": i, "url": product_url}
                            )
                            logger.info(
                                f"URL direta encontrada para produto {i+1}: {product_url}"
                            )
                        else:
                            # Se não encontrar link direto, tenta clicar no article
                            try:
                                # Scroll para o elemento para garantir que está visível
                                driver.execute_script(
                                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                                    article,
                                )
                                time.sleep(2)

                                # Captura URL atual antes do clique
                                url_before = driver.current_url
                                logger.info(f"URL antes do clique: {url_before}")

                                # Tenta diferentes elementos clicáveis dentro do article
                                clickable_elements = []

                                # Busca por links específicos
                                clickable_elements.extend(
                                    article.find_elements(By.TAG_NAME, "a")
                                )

                                # Busca por elementos com onclick ou cursor pointer
                                clickable_elements.extend(
                                    article.find_elements(
                                        By.XPATH,
                                        ".//*[@onclick or contains(@class, 'clickable') or contains(@style, 'cursor: pointer')]",
                                    )
                                )

                                clicked = False
                                for clickable in clickable_elements[
                                    :3
                                ]:  # Testa apenas os primeiros 3
                                    try:
                                        # Tenta usar JavaScript click para ser mais confiável
                                        driver.execute_script(
                                            "arguments[0].click();", clickable
                                        )
                                        time.sleep(4)  # Aguarda navegação

                                        url_after = driver.current_url
                                        logger.info(f"URL após clique: {url_after}")

                                        # Verifica se navegou para página de produto
                                        if url_after != url_before and (
                                            "/p?skuId=" in url_after
                                            or "/produto/" in url_after
                                            or "/br/" in url_after
                                        ):
                                            samsung_products_data.append(
                                                {"element_index": i, "url": url_after}
                                            )
                                            logger.info(
                                                f"✅ URL via clique encontrada para produto {i+1}: {url_after}"
                                            )
                                            clicked = True
                                            break

                                    except Exception as click_e:
                                        logger.debug(
                                            f"Erro no clique específico: {str(click_e)}"
                                        )
                                        continue

                                # Se não conseguiu com elementos específicos, tenta clicar no article inteiro
                                if not clicked:
                                    try:
                                        driver.execute_script(
                                            "arguments[0].click();", article
                                        )
                                        time.sleep(4)

                                        url_after = driver.current_url
                                        logger.info(
                                            f"URL após clique no article: {url_after}"
                                        )

                                        if url_after != url_before and (
                                            "/p?skuId=" in url_after
                                            or "/produto/" in url_after
                                            or "/br/" in url_after
                                        ):
                                            samsung_products_data.append(
                                                {"element_index": i, "url": url_after}
                                            )
                                            logger.info(
                                                f"✅ URL via clique no article encontrada para produto {i+1}: {url_after}"
                                            )
                                            clicked = True
                                    except Exception as article_click_e:
                                        logger.warning(
                                            f"Erro ao clicar no article: {str(article_click_e)}"
                                        )

                                # Sempre volta para a página de busca
                                if clicked or driver.current_url != url_before:
                                    logger.info("Voltando para página de busca...")
                                    driver.get(current_url)
                                    time.sleep(4)  # Aguarda recarregamento completo

                            except Exception as e:
                                logger.warning(
                                    f"Erro geral ao processar produto Samsung {i+1}: {str(e)}"
                                )
                                # Tenta voltar para a página de busca em caso de erro
                                try:
                                    driver.get(current_url)
                                    time.sleep(3)
                                except:
                                    pass

                    except Exception as e:
                        logger.warning(
                            f"Erro ao processar produto Samsung {i+1}: {str(e)}"
                        )
                        continue

                logger.info(
                    f"Encontradas {len(samsung_products_data)} URLs reais para produtos Samsung"
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
                url_map[item["element_index"]] = item["url"]
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
                # Usar URL específica se disponível
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

                # URL do produto - prioriza URL específica obtida por clique
                url = specific_url if specific_url else ""
                logger.debug(f"URL específica para produto {i}: {specific_url}")

                if not url:
                    # Busca por links com padrões Samsung específicos
                    link_selectors = [
                        "a[href*='p?skuId=']",  # Padrão principal Samsung
                        "a[href*='/br/']",  # Produtos BR Samsung
                        "a[href*='/produto/']",  # Páginas de produto
                        "a[href*='/p/']",  # Padrão alternativo
                        "a[href]",  # Qualquer link como fallback
                    ]

                    for link_sel in link_selectors:
                        link_elements = container.select(link_sel)
                        for link_element in link_elements:
                            href = link_element.get("href")
                            if href:
                                # Verifica padrões Samsung específicos primeiro
                                if (
                                    "p?skuId=" in href
                                    or "/br/" in href
                                    or "/produto/" in href
                                    or "/p/" in href
                                ):
                                    if href.startswith("/"):
                                        url = f"https://shop.samsung.com.br{href}"
                                    elif not href.startswith("http"):
                                        url = f"https://shop.samsung.com.br/{href}"
                                    else:
                                        url = href
                                    logger.info(f"URL Samsung encontrada: {url}")
                                    break
                        if url:
                            break

                    # Se ainda não tem URL, usa a URL de busca como fallback
                    if not url:
                        url = search_url
                        logger.warning(
                            f"Usando URL de busca como fallback para produto {i}"
                        )
                else:
                    logger.info(
                        f"Usando URL específica do clique para produto {i}: {url}"
                    )

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

                # Criar produto se tem informações mínimas
                if name and price and len(name) >= 3:
                    # Usar URL específica se disponível, senão usar URL encontrada ou de busca
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

            except Exception as e:
                logger.warning(f"Erro ao processar produto Samsung: {str(e)}")
                continue

        logger.info(f"Extraídos {len(products)} produtos válidos da Samsung")
        return products

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extrai valor numérico do texto de preço"""
        if not price_text:
            return None

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
