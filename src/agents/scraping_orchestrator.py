from typing import List, Dict, Any, TypedDict
import asyncio
import time
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from loguru import logger

from src.models import ScrapingRequest, ScrapingResult, ProductInfo
from src.scrapers import (
    AmazonBRScraper,
    MercadoLivreScraper,
    CarrefourScraper,
    MagazineLuizaScraper,
    SamsungScraper,
    LGScraper,
    CasasBahiaScraper,
    PontoFrioScraper,
)


class ScrapingState(TypedDict):
    """Estado compartilhado entre agentes"""

    request: ScrapingRequest
    results: List[ProductInfo]
    completed_sites: List[str]
    remaining_sites: List[str]
    messages: List[BaseMessage]
    max_results_per_site: int


class ScrapingOrchestrator:
    """Orquestrador principal dos agentes de scraping"""

    def __init__(self):
        self.scrapers = {
            "amazon": AmazonBRScraper(),
            "mercadolivre": MercadoLivreScraper(),
            "carrefour": CarrefourScraper(),
            "magazine_luiza": MagazineLuizaScraper(),
            "samsung": SamsungScraper(),
            "lg": LGScraper(),
            "casas_bahia": CasasBahiaScraper(),
            "ponto_frio": PontoFrioScraper(),
        }
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Constrói o grafo de agentes LangGraph"""

        workflow = StateGraph(ScrapingState)

        # Adiciona nós para cada tipo de agente
        workflow.add_node("coordinator", self._coordinator_agent)
        workflow.add_node("amazon_scraper", self._amazon_scraper_agent)
        workflow.add_node("mercadolivre_scraper", self._mercadolivre_scraper_agent)
        workflow.add_node("carrefour_scraper", self._carrefour_scraper_agent)
        workflow.add_node("magazine_luiza_scraper", self._magazine_luiza_scraper_agent)
        workflow.add_node("samsung_scraper", self._samsung_scraper_agent)
        workflow.add_node("lg_scraper", self._lg_scraper_agent)
        workflow.add_node("casas_bahia_scraper", self._casas_bahia_scraper_agent)
        workflow.add_node("ponto_frio_scraper", self._ponto_frio_scraper_agent)
        workflow.add_node("aggregator", self._aggregator_agent)

        # Define entrada
        workflow.set_entry_point("coordinator")

        # Coordenador decide quais scrapers executar
        workflow.add_conditional_edges(
            "coordinator",
            self._decide_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "ponto_frio": "ponto_frio_scraper",
            },
        )

        # Cada scraper volta para verificar se há mais sites
        workflow.add_conditional_edges(
            "amazon_scraper",
            self._check_remaining_scrapers,
            {
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "ponto_frio": "ponto_frio_scraper",
                "end": "aggregator",
            },
        )

        workflow.add_conditional_edges(
            "mercadolivre_scraper",
            self._check_remaining_scrapers,
            {
                "amazon": "amazon_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "ponto_frio": "ponto_frio_scraper",
                "end": "aggregator",
            },
        )

        workflow.add_conditional_edges(
            "carrefour_scraper",
            self._check_remaining_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "ponto_frio": "ponto_frio_scraper",
                "end": "aggregator",
            },
        )

        workflow.add_conditional_edges(
            "magazine_luiza_scraper",
            self._check_remaining_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "ponto_frio": "ponto_frio_scraper",
                "end": "aggregator",
            },
        )

        workflow.add_conditional_edges(
            "samsung_scraper",
            self._check_remaining_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "lg": "lg_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "ponto_frio": "ponto_frio_scraper",
                "end": "aggregator",
            },
        )

        workflow.add_conditional_edges(
            "lg_scraper",
            self._check_remaining_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "samsung": "samsung_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "ponto_frio": "ponto_frio_scraper",
                "end": "aggregator",
            },
        )

        workflow.add_conditional_edges(
            "casas_bahia_scraper",
            self._check_remaining_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "ponto_frio": "ponto_frio_scraper",
                "end": "aggregator",
            },
        )

        workflow.add_conditional_edges(
            "ponto_frio_scraper",
            self._check_remaining_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "end": "aggregator",
            },
        )

        # Agregador é o fim
        workflow.add_edge("aggregator", END)

        return workflow.compile()

    def _coordinator_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente coordenador que decide qual scraper executar primeiro"""
        logger.info("Coordenador: Iniciando orquestração de scraping")

        # Define quais sites scraping baseado na requisição
        sites_to_scrape = [
            "amazon",
            "mercadolivre",
            "carrefour",
            "magazine_luiza",
            "samsung",
            "lg",
            "casas_bahia",
            "ponto_frio",
        ]

        # Filtra sites se especificados na requisição
        if hasattr(state["request"], "target_sites") and state["request"].target_sites:
            sites_to_scrape = [
                site
                for site in sites_to_scrape
                if site in state["request"].target_sites
            ]

        state["remaining_sites"] = sites_to_scrape
        state["completed_sites"] = []
        state["results"] = []
        state["max_results_per_site"] = state["request"].max_results_per_site

        state["messages"].append(
            AIMessage(
                content=f"Coordenador: Iniciando scraping em {len(sites_to_scrape)} sites"
            )
        )

        logger.info(f"Sites selecionados para scraping: {sites_to_scrape}")
        return state

    def _decide_scrapers(self, state: ScrapingState) -> str:
        """Decide qual scraper executar próximo"""
        if not state["remaining_sites"]:
            return "end"

        next_site = state["remaining_sites"][0]
        logger.info(f"Próximo site: {next_site}")
        return next_site

    def _check_remaining_scrapers(self, state: ScrapingState) -> str:
        """Verifica se há mais scrapers para executar"""
        if not state["remaining_sites"]:
            return "end"

        next_site = state["remaining_sites"][0]
        return next_site

    def _amazon_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping da Amazon BR"""
        logger.info("Agente Amazon: Iniciando scraping")

        try:
            scraper = self.scrapers["amazon"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("amazon")
            state["completed_sites"].append("amazon")

            state["messages"].append(
                AIMessage(content=f"Amazon: {len(products)} produtos encontrados")
            )

            logger.info(f"Amazon: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping Amazon: {str(e)}")
            state["remaining_sites"].remove("amazon")
            state["messages"].append(
                AIMessage(content=f"Amazon: Erro durante scraping - {str(e)}")
            )

        return state

    def _mercadolivre_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Mercado Livre"""
        logger.info("Agente Mercado Livre: Iniciando scraping")

        try:
            scraper = self.scrapers["mercadolivre"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("mercadolivre")
            state["completed_sites"].append("mercadolivre")

            state["messages"].append(
                AIMessage(
                    content=f"Mercado Livre: {len(products)} produtos encontrados"
                )
            )

            logger.info(f"Mercado Livre: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping Mercado Livre: {str(e)}")
            state["remaining_sites"].remove("mercadolivre")
            state["messages"].append(
                AIMessage(content=f"Mercado Livre: Erro durante scraping - {str(e)}")
            )

        return state

    def _carrefour_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Carrefour"""
        logger.info("Agente Carrefour: Iniciando scraping")

        try:
            scraper = self.scrapers["carrefour"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("carrefour")
            state["completed_sites"].append("carrefour")

            state["messages"].append(
                AIMessage(content=f"Carrefour: {len(products)} produtos encontrados")
            )

            logger.info(f"Carrefour: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping Carrefour: {str(e)}")
            state["remaining_sites"].remove("carrefour")
            state["messages"].append(
                AIMessage(content=f"Carrefour: Erro durante scraping - {str(e)}")
            )

        return state

    def _magazine_luiza_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Magazine Luiza"""
        logger.info("Agente Magazine Luiza: Iniciando scraping")

        try:
            scraper = self.scrapers["magazine_luiza"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("magazine_luiza")
            state["completed_sites"].append("magazine_luiza")

            state["messages"].append(
                AIMessage(
                    content=f"Magazine Luiza: {len(products)} produtos encontrados"
                )
            )

            logger.info(f"Magazine Luiza: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping Magazine Luiza: {str(e)}")
            state["remaining_sites"].remove("magazine_luiza")
            state["messages"].append(
                AIMessage(content=f"Magazine Luiza: Erro durante scraping - {str(e)}")
            )

        return state

    def _samsung_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping da Samsung"""
        logger.info("Agente Samsung: Iniciando scraping")

        try:
            scraper = self.scrapers["samsung"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("samsung")
            state["completed_sites"].append("samsung")

            state["messages"].append(
                AIMessage(content=f"Samsung: {len(products)} produtos encontrados")
            )

            logger.info(f"Samsung: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping Samsung: {str(e)}")
            state["remaining_sites"].remove("samsung")
            state["messages"].append(
                AIMessage(content=f"Samsung: Erro durante scraping - {str(e)}")
            )

        return state

    def _lg_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping da LG"""
        logger.info("Agente LG: Iniciando scraping")

        try:
            scraper = self.scrapers["lg"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("lg")
            state["completed_sites"].append("lg")

            state["messages"].append(
                AIMessage(content=f"LG: {len(products)} produtos encontrados")
            )

            logger.info(f"LG: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping LG: {str(e)}")
            state["remaining_sites"].remove("lg")
            state["messages"].append(
                AIMessage(content=f"LG: Erro durante scraping - {str(e)}")
            )

        return state

    def _casas_bahia_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Casas Bahia"""
        logger.info("Agente Casas Bahia: Iniciando scraping")

        try:
            scraper = self.scrapers["casas_bahia"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("casas_bahia")
            state["completed_sites"].append("casas_bahia")

            state["messages"].append(
                AIMessage(content=f"Casas Bahia: {len(products)} produtos encontrados")
            )

            logger.info(f"Casas Bahia: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping Casas Bahia: {str(e)}")
            state["remaining_sites"].remove("casas_bahia")
            state["messages"].append(
                AIMessage(content=f"Casas Bahia: Erro durante scraping - {str(e)}")
            )

        return state

    def _ponto_frio_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Ponto Frio"""
        logger.info("Agente Ponto Frio: Iniciando scraping")

        try:
            scraper = self.scrapers["ponto_frio"]
            products = asyncio.run(
                scraper.scrape(
                    state["request"].product_name, state["max_results_per_site"]
                )
            )

            state["results"].extend(products)
            state["remaining_sites"].remove("ponto_frio")
            state["completed_sites"].append("ponto_frio")

            state["messages"].append(
                AIMessage(content=f"Ponto Frio: {len(products)} produtos encontrados")
            )

            logger.info(f"Ponto Frio: {len(products)} produtos coletados")

        except Exception as e:
            logger.error(f"Erro no scraping Ponto Frio: {str(e)}")
            state["remaining_sites"].remove("ponto_frio")
            state["messages"].append(
                AIMessage(content=f"Ponto Frio: Erro durante scraping - {str(e)}")
            )

        return state

    def _aggregator_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente agregador que consolida os resultados"""
        logger.info("Agente Agregador: Consolidando resultados")

        total_products = len(state["results"])
        sites_completed = len(state["completed_sites"])

        # Ordena produtos por preço (menores primeiro)
        state["results"].sort(key=lambda x: x.price if x.price else float("inf"))

        # Adiciona estatísticas finais
        state["messages"].append(
            AIMessage(
                content=f"Scraping concluído: {total_products} produtos encontrados em {sites_completed} sites"
            )
        )

        # Log das estatísticas por site
        site_name_mapping = {
            "amazon": "Amazon BR",
            "mercadolivre": "Mercado Livre",
            "carrefour": "Carrefour",
            "magazine_luiza": "Magazine Luiza",
            "samsung": "Samsung",
            "lg": "LG",
            "casas_bahia": "Casas Bahia",
            "ponto_frio": "Ponto Frio",
        }

        for site in state["completed_sites"]:
            site_display_name = site_name_mapping.get(site, site)
            site_products = [p for p in state["results"] if p.site == site_display_name]
            logger.info(f"{site}: {len(site_products)} produtos")

        logger.success(f"Agregação concluída: {total_products} produtos consolidados")
        return state

    async def scrape(self, request: ScrapingRequest) -> ScrapingResult:
        """Executa o processo de scraping orquestrado"""
        logger.info(f"Iniciando scraping orquestrado para: {request.product_name}")

        initial_state: ScrapingState = {
            "request": request,
            "results": [],
            "completed_sites": [],
            "remaining_sites": [],
            "messages": [HumanMessage(content=f"Buscar por: {request.product_name}")],
            "max_results_per_site": request.max_results_per_site,
        }

        start_time = time.time()

        try:
            # Executa o grafo de agentes
            final_state = await asyncio.to_thread(self.graph.invoke, initial_state)

            # Calcula tempo de execução
            execution_time = time.time() - start_time

            # Cria resultado consolidado
            result = ScrapingResult(
                request=request,
                products=final_state["results"],
                total_found=len(final_state["results"]),
                execution_time=execution_time,
                errors=[],
            )

            logger.success(
                f"Scraping orquestrado concluído: {result.total_found} produtos de {len(final_state['completed_sites'])} sites em {execution_time:.2f}s"
            )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Erro durante scraping orquestrado: {str(e)}")
            return ScrapingResult(
                request=request,
                products=[],
                total_found=0,
                execution_time=execution_time,
                errors=[str(e)],
            )
