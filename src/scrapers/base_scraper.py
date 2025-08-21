from abc import ABC, abstractmethod
from typing import List
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from loguru import logger

from ..models import ProductInfo, SiteConfig


class BaseScraper(ABC):
    """Scraper base para todos os sites de e-commerce"""

    def __init__(self, site_config: SiteConfig):
        self.config = site_config
        self.session = None
        self._setup_session()

    def _setup_session(self):
        """Configura sessão HTTP"""
        self.session = requests.Session()
        if self.config.headers:
            self.session.headers.update(self.config.headers)

    def _create_webdriver(self) -> webdriver.Chrome:
        """Cria instância do WebDriver Chrome"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        if self.config.headers and "User-Agent" in self.config.headers:
            chrome_options.add_argument(
                f'--user-agent={self.config.headers["User-Agent"]}'
            )

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            # Adiciona mais propriedades para evitar detecção
            if hasattr(self.config, "headers") and self.config.headers:
                user_agent = self.config.headers.get(
                    "User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                )
            else:
                user_agent = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )

            driver.execute_cdp_cmd(
                "Network.setUserAgentOverride", {"userAgent": user_agent}
            )
            return driver
        except Exception as e:
            logger.error(f"Erro ao criar WebDriver: {str(e)}")
            raise

    @abstractmethod
    def build_search_url(self, product_name: str) -> str:
        """Constrói a URL de busca para o produto"""
        pass

    @abstractmethod
    def extract_product_info(
        self, html_content: str, base_url: str
    ) -> List[ProductInfo]:
        """Extrai informações dos produtos do HTML"""
        pass

    async def scrape_with_selenium(
        self, product_name: str, max_results: int = 5
    ) -> List[ProductInfo]:
        """Executa scraping usando Selenium"""
        driver = None
        try:
            search_url = self.build_search_url(product_name)
            logger.info(f"Iniciando scraping com Selenium: {search_url}")

            driver = self._create_webdriver()
            driver.get(search_url)

            # Aguarda carregamento da página
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Aguarda específico para cada site
            if "americanas" in search_url.lower():
                try:
                    # Aguarda produtos aparecerem ou estado de busca vazia
                    WebDriverWait(driver, 15).until(
                        lambda d: (
                            d.find_elements(
                                By.CSS_SELECTOR,
                                "[data-testid='product-card'], .product-item, article",
                            )
                            or d.find_elements(
                                By.CSS_SELECTOR, "[data-fs-empty-state='true']"
                            )
                            or "não encontramos nenhum resultado"
                            in d.page_source.lower()
                        )
                    )
                    time.sleep(3)  # Tempo adicional para carregamento completo
                except Exception as e:
                    logger.warning(f"Timeout aguardando produtos do Americanas: {e}")
                    time.sleep(5)  # Fallback

            elif "magazineluiza" in search_url.lower():
                try:
                    # Magazine Luiza usa renderização JavaScript pesada
                    # Aguarda elementos de produto carregarem
                    WebDriverWait(driver, 20).until(
                        lambda d: (
                            d.find_elements(
                                By.CSS_SELECTOR,
                                "li[data-testid], [class*='product'], .sc-kpDqfm, .sc-dcJsrY",
                            )
                            or d.find_elements(
                                By.CSS_SELECTOR, ".empty-state, .no-results"
                            )
                            or len(d.find_elements(By.TAG_NAME, "li")) > 10
                        )
                    )

                    # Aguarda carregamento adicional e faz scroll para carregar lazy loading
                    time.sleep(3)
                    driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight/2);"
                    )
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(2)

                except Exception as e:
                    logger.warning(
                        f"Timeout aguardando produtos do Magazine Luiza: {e}"
                    )
                    time.sleep(5)

            else:
                # Para outros sites (Amazon, Mercado Livre)
                time.sleep(5)  # Aumentei o delay para ML

            # Obtém HTML da página
            html_content = driver.page_source

            # Extrai produtos
            products = self.extract_product_info(html_content, search_url)

            logger.success(
                f"Scraping Selenium concluído: {len(products)} produtos encontrados em {self.config.name}"
            )
            return products[:max_results]

        except TimeoutException:
            logger.error(f"Timeout ao carregar página para {self.config.name}")
            return []
        except WebDriverException as e:
            logger.error(f"Erro no WebDriver para {self.config.name}: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Erro no scraping Selenium para {self.config.name}: {str(e)}")
            return []
        finally:
            if driver:
                driver.quit()

    async def scrape_with_requests(
        self, product_name: str, max_results: int = 5
    ) -> List[ProductInfo]:
        """Executa scraping usando requests simples"""
        try:
            search_url = self.build_search_url(product_name)
            logger.info(f"Iniciando scraping com requests: {search_url}")

            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()

            # Extrai produtos
            products = self.extract_product_info(response.text, search_url)

            logger.success(
                f"Scraping requests concluído: {len(products)} produtos encontrados em {self.config.name}"
            )
            return products[:max_results]

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro na requisição para {self.config.name}: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Erro no scraping requests para {self.config.name}: {str(e)}")
            return []

    async def scrape(
        self, product_name: str, max_results: int = 5
    ) -> List[ProductInfo]:
        """Executa scraping usando a melhor estratégia disponível"""
        start_time = time.time()

        try:
            # Tenta com Selenium (mais robusto para SPAs e JavaScript)
            products = await self.scrape_with_selenium(product_name, max_results)
            if products:
                execution_time = time.time() - start_time
                logger.info(
                    f"Scraping {self.config.name} concluído em {execution_time:.2f}s via Selenium"
                )
                return products

            # Fallback para requests simples
            products = await self.scrape_with_requests(product_name, max_results)
            execution_time = time.time() - start_time
            logger.info(
                f"Scraping {self.config.name} concluído em {execution_time:.2f}s via requests"
            )
            return products

        except Exception as e:
            logger.error(f"Erro no scraping de {self.config.name}: {str(e)}")
            return []

    def add_delay(self):
        """Adiciona delay entre requests"""
        time.sleep(self.config.rate_limit_delay)
