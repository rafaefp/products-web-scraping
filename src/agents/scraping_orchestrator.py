from typing import List, Dict, Any, TypedDict
import asyncio
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from loguru import logger

from src.models import ScrapingRequest, ScrapingResult, ProductInfo
from src.scrapers import (
    AmazonBRScraper,
    MercadoLivreScraper,
    AmericanasScraper,
    MagazineLuizaScraper,
    CasasBahiaScraper,
    PontoFrioScraper,
    CarrefourScraper,
    SamsungScraper,
    LGScraper,
)

from ..models import ScrapingRequest, ScrapingResult, ProductInfo
from ..scrapers.ecommerce_scrapers import (
    AmazonBRScraper,
    MercadoLivreScraper,
    AmericanasScraper,
    MagazineLuizaScraper,
    CasasBahiaScraper,
    PontoFrioScraper,
    CarrefourScraper,
    SamsungScraper,
)


class ScrapingState(TypedDict):
    """Estado compartilhado entre os agentes"""

    request: ScrapingRequest
    products: List[ProductInfo]
    errors: List[str]
    completed_sites: List[str]
    messages: List[BaseMessage]


class ScrapingOrchestrator:
    """Orquestrador principal dos agentes de scraping"""

    def __init__(self):
        self.scrapers = {
            "amazon": AmazonBRScraper(),
            "mercadolivre": MercadoLivreScraper(),
            "americanas": AmericanasScraper(),
            "magazine_luiza": MagazineLuizaScraper(),
            "casas_bahia": CasasBahiaScraper(),
            "pontofrio": PontoFrioScraper(),
            "carrefour": CarrefourScraper(),
            "samsung": SamsungScraper(),
            "lg": LGScraper(),
        }
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Constrói o grafo de agentes LangGraph"""

        workflow = StateGraph(ScrapingState)

        # Nós do grafo
        workflow.add_node("coordinator", self._coordinator_agent)
        workflow.add_node("amazon_scraper", self._amazon_scraper_agent)
        workflow.add_node("mercadolivre_scraper", self._mercadolivre_scraper_agent)
        workflow.add_node("americanas_scraper", self._americanas_scraper_agent)
        workflow.add_node("magazine_luiza_scraper", self._magazine_luiza_scraper_agent)
        workflow.add_node("casas_bahia_scraper", self._casas_bahia_scraper_agent)
        workflow.add_node("pontofrio_scraper", self._pontofrio_scraper_agent)
        workflow.add_node("carrefour_scraper", self._carrefour_scraper_agent)
        workflow.add_node("samsung_scraper", self._samsung_scraper_agent)
        workflow.add_node("lg_scraper", self._lg_scraper_agent)
        workflow.add_node("results_aggregator", self._results_aggregator_agent)

        # Fluxo do grafo
        workflow.set_entry_point("coordinator")

        # Coordenador decide quais scrapers executar
        workflow.add_conditional_edges(
            "coordinator",
            self._decide_scrapers,
            {
                "amazon": "amazon_scraper",
                "mercadolivre": "mercadolivre_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "americanas": "americanas_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "pontofrio": "pontofrio_scraper",
                "carrefour": "carrefour_scraper",
                "samsung": "samsung_scraper",
                "lg": "lg_scraper",
                "multiple": "amazon_scraper",  # Inicia com Amazon se múltiplos sites
                "end": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "amazon_scraper",
            self._check_remaining_scrapers,
            {
                "mercadolivre": "mercadolivre_scraper",
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "americanas": "americanas_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "pontofrio": "pontofrio_scraper",
                "samsung": "samsung_scraper",
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "mercadolivre_scraper",
            self._check_remaining_scrapers,
            {
                "carrefour": "carrefour_scraper",
                "magazine_luiza": "magazine_luiza_scraper",
                "americanas": "americanas_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "pontofrio": "pontofrio_scraper",
                "samsung": "samsung_scraper",
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "carrefour_scraper",
            self._check_remaining_scrapers,
            {
                "magazine_luiza": "magazine_luiza_scraper",
                "americanas": "americanas_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "pontofrio": "pontofrio_scraper",
                "samsung": "samsung_scraper",
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "magazine_luiza_scraper",
            self._check_remaining_scrapers,
            {
                "americanas": "americanas_scraper",
                "casas_bahia": "casas_bahia_scraper",
                "pontofrio": "pontofrio_scraper",
                "samsung": "samsung_scraper",
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "americanas_scraper",
            self._check_remaining_scrapers,
            {
                "casas_bahia": "casas_bahia_scraper",
                "pontofrio": "pontofrio_scraper",
                "samsung": "samsung_scraper",
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "casas_bahia_scraper",
            self._check_remaining_scrapers,
            {
                "pontofrio": "pontofrio_scraper",
                "samsung": "samsung_scraper",
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "pontofrio_scraper",
            self._check_remaining_scrapers,
            {
                "samsung": "samsung_scraper",
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "samsung_scraper",
            self._check_remaining_scrapers,
            {
                "done": "results_aggregator",
            },
        )

        workflow.add_conditional_edges(
            "lg_scraper",
            self._check_remaining_scrapers,
            {
                "done": "results_aggregator",
            },
        )

        workflow.add_edge("results_aggregator", END)

        return workflow.compile()

    def _coordinator_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente coordenador que analisa a requisição"""
        logger.info("Agente Coordenador: Analisando requisição de scraping")

        request = state["request"]

        # Expande "all" para todos os sites disponíveis
        if "all" in request.target_sites:
            request.target_sites = [
                "amazon",
                "mercadolivre",
                "magazine_luiza",
                "americanas",
                "casas_bahia",
            ]

        # Valida sites disponíveis
        available_sites = []
        supported_sites = [
            "amazon",
            "mercadolivre",
            "magazine_luiza",
            "americanas",
            "casas_bahia",
            "pontofrio",
            "carrefour",
            "samsung",
        ]

        for site in request.target_sites:
            site_lower = site.lower()
            if site_lower in supported_sites:
                available_sites.append(site_lower)
            else:
                state["errors"].append(f"Site não suportado: {site}")

        # Atualiza a requisição com sites válidos
        state["request"].target_sites = available_sites

        # Adiciona mensagem de coordenação
        message = HumanMessage(
            content=f"Iniciando scraping para '{request.product_name}' nos sites: {', '.join(available_sites)}"
        )
        state["messages"].append(message)

        logger.info(f"Sites válidos identificados: {available_sites}")
        return state

    def _amazon_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping da Amazon"""
        logger.info("Agente Amazon: Iniciando scraping")

        try:
            scraper = self.scrapers["amazon"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("amazon")

            # Adiciona mensagem de resultado
            message = AIMessage(content=f"Amazon: {len(products)} produtos encontrados")
            state["messages"].append(message)

            logger.success(f"Amazon scraping concluído: {len(products)} produtos")

        except Exception as e:
            error_msg = f"Erro no scraping da Amazon: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _mercadolivre_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Mercado Livre"""
        logger.info("Agente Mercado Livre: Iniciando scraping")

        try:
            scraper = self.scrapers["mercadolivre"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("mercadolivre")

            # Adiciona mensagem de resultado
            message = AIMessage(
                content=f"Mercado Livre: {len(products)} produtos encontrados"
            )
            state["messages"].append(message)

            logger.success(
                f"Mercado Livre scraping concluído: {len(products)} produtos"
            )

        except Exception as e:
            error_msg = f"Erro no scraping do Mercado Livre: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _americanas_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Americanas"""
        logger.info("Agente Americanas: Iniciando scraping")

        try:
            scraper = self.scrapers["americanas"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("americanas")

            # Adiciona mensagem de resultado
            message = AIMessage(
                content=f"Americanas: {len(products)} produtos encontrados"
            )
            state["messages"].append(message)

            logger.success(f"Americanas scraping concluído: {len(products)} produtos")

        except Exception as e:
            error_msg = f"Erro no scraping do Americanas: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _magazine_luiza_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Magazine Luiza"""
        logger.info("Agente Magazine Luiza: Iniciando scraping")

        try:
            scraper = self.scrapers["magazine_luiza"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("magazine_luiza")

            # Adiciona mensagem de resultado
            message = AIMessage(
                content=f"Magazine Luiza: {len(products)} produtos encontrados"
            )
            state["messages"].append(message)

            logger.success(
                f"Magazine Luiza scraping concluído: {len(products)} produtos"
            )

        except Exception as e:
            error_msg = f"Erro no scraping do Magazine Luiza: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _casas_bahia_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping das Casas Bahia"""
        logger.info("Agente Casas Bahia: Iniciando scraping")

        try:
            scraper = self.scrapers["casas_bahia"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("casas_bahia")

            logger.success(f"Casas Bahia scraping concluído: {len(products)} produtos")

        except Exception as e:
            error_msg = f"Erro no scraping das Casas Bahia: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _pontofrio_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Ponto Frio"""
        logger.info("Agente Ponto Frio: Iniciando scraping")

        try:
            scraper = self.scrapers["pontofrio"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("pontofrio")

            logger.success(f"Ponto Frio scraping concluído: {len(products)} produtos")

        except Exception as e:
            error_msg = f"Erro no scraping do Ponto Frio: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _carrefour_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping do Carrefour"""
        logger.info("Agente Carrefour: Iniciando scraping")

        try:
            scraper = self.scrapers["carrefour"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("carrefour")

            # Adiciona mensagem de resultado
            message = AIMessage(
                content=f"Carrefour: {len(products)} produtos encontrados"
            )
            state["messages"].append(message)

            logger.success(f"Carrefour scraping concluído: {len(products)} produtos")

        except Exception as e:
            error_msg = f"Erro no scraping do Carrefour: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _samsung_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping da Samsung Brasil"""
        logger.info("Agente Samsung: Iniciando scraping")

        try:
            scraper = self.scrapers["samsung"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("samsung")

            # Adiciona mensagem de resultado
            message = AIMessage(
                content=f"Samsung: {len(products)} produtos encontrados"
            )
            state["messages"].append(message)

            logger.success(f"Samsung scraping concluído: {len(products)} produtos")

        except Exception as e:
            error_msg = f"Erro no scraping da Samsung: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _lg_scraper_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente especializado em scraping da LG Brasil"""
        logger.info("Agente LG: Iniciando scraping")

        try:
            scraper = self.scrapers["lg"]
            request = state["request"]

            # Executa scraping assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            products = loop.run_until_complete(
                scraper.scrape(request.product_name, request.max_results_per_site)
            )

            loop.close()

            # Adiciona produtos encontrados
            state["products"].extend(products)
            state["completed_sites"].append("lg")

            # Adiciona mensagem de resultado
            message = AIMessage(
                content=f"LG: {len(products)} produtos encontrados"
            )
            state["messages"].append(message)

            logger.success(f"LG scraping concluído: {len(products)} produtos")

        except Exception as e:
            error_msg = f"Erro no scraping da LG: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)

        return state

    def _results_aggregator_agent(self, state: ScrapingState) -> ScrapingState:
        """Agente agregador que consolida os resultados"""
        logger.info("Agente Agregador: Consolidando resultados")

        total_products = len(state["products"])
        total_sites = len(state["completed_sites"])
        total_errors = len(state["errors"])

        # Ordena produtos por preço (menor primeiro)
        state["products"].sort(key=lambda p: p.price or float("inf"))

        # Adiciona mensagem de resumo
        summary_message = AIMessage(
            content=f"Scraping concluído: {total_products} produtos de {total_sites} sites. {total_errors} erros."
        )
        state["messages"].append(summary_message)

        logger.success(f"Agregação concluída: {total_products} produtos consolidados")
        return state

    def _decide_scrapers(self, state: ScrapingState) -> str:
        """Decide quais scrapers executar baseado na requisição"""
        target_sites = state["request"].target_sites

        if not target_sites:
            return "end"

        # Mapeia sites para decisão
        has_amazon = any(site in ["amazon", "all"] for site in target_sites)
        has_mercadolivre = any(
            site in ["mercadolivre", "mercado livre", "all"] for site in target_sites
        )
        has_magazine_luiza = any(
            site in ["magazine_luiza", "magazineluiza", "magazine luiza", "all"]
            for site in target_sites
        )
        has_americanas = any(site in ["americanas"] for site in target_sites)
        has_casas_bahia = any(
            site in ["casas_bahia", "casasbahia", "casas bahia"]
            for site in target_sites
        )
        has_pontofrio = any(
            site in ["pontofrio", "ponto frio"] for site in target_sites
        )
        has_carrefour = any(site in ["carrefour", "all"] for site in target_sites)
        has_samsung = any(site in ["samsung"] for site in target_sites)

        # Conta quantos sites foram solicitados
        site_count = sum(
            [
                has_amazon,
                has_mercadolivre,
                has_magazine_luiza,
                has_americanas,
                has_casas_bahia,
                has_pontofrio,
                has_carrefour,
                has_samsung,
            ]
        )

        # Lógica atualizada para múltiplos sites
        if site_count > 1:
            return "multiple"
        elif has_amazon:
            return "amazon"
        elif has_mercadolivre:
            return "mercadolivre"
        elif has_magazine_luiza:
            return "magazine_luiza"
        elif has_americanas:
            return "americanas"
        elif has_casas_bahia:
            return "casas_bahia"
        elif has_pontofrio:
            return "pontofrio"
        elif has_carrefour:
            return "carrefour"
        elif has_samsung:
            return "samsung"
        else:
            return "end"

    def _check_remaining_scrapers(self, state: ScrapingState) -> str:
        """Verifica se há mais scrapers para executar na ordem: mercadolivre → carrefour → magazine_luiza → americanas → casas_bahia → pontofrio"""
        target_sites = state["request"].target_sites
        completed_sites = state["completed_sites"]

        # Verifica cada site que deve ser executado
        has_mercadolivre = any(
            site in ["mercadolivre", "mercado livre", "all"] for site in target_sites
        )
        has_magazine_luiza = any(
            site in ["magazine_luiza", "magazineluiza", "magazine luiza", "all"]
            for site in target_sites
        )
        has_americanas = any(site in ["americanas"] for site in target_sites)
        has_casas_bahia = any(
            site in ["casas_bahia", "casasbahia", "casas bahia"]
            for site in target_sites
        )
        has_pontofrio = any(
            site in ["pontofrio", "ponto frio"] for site in target_sites
        )
        has_carrefour = any(site in ["carrefour", "all"] for site in target_sites)
        has_samsung = any(site in ["samsung"] for site in target_sites)

        mercadolivre_completed = "mercadolivre" in completed_sites
        magazine_luiza_completed = "magazine_luiza" in completed_sites
        americanas_completed = "americanas" in completed_sites
        casas_bahia_completed = "casas_bahia" in completed_sites
        pontofrio_completed = "pontofrio" in completed_sites
        carrefour_completed = "carrefour" in completed_sites
        samsung_completed = "samsung" in completed_sites

        if has_mercadolivre and not mercadolivre_completed:
            return "mercadolivre"
        elif has_carrefour and not carrefour_completed:
            return "carrefour"
        elif has_magazine_luiza and not magazine_luiza_completed:
            return "magazine_luiza"
        elif has_americanas and not americanas_completed:
            return "americanas"
        elif has_casas_bahia and not casas_bahia_completed:
            return "casas_bahia"
        elif has_pontofrio and not pontofrio_completed:
            return "pontofrio"
        elif has_samsung and not samsung_completed:
            return "samsung"
        else:
            return "done"

    async def execute_scraping(self, request: ScrapingRequest) -> ScrapingResult:
        """Executa o processo completo de scraping usando LangGraph"""
        logger.info(f"Iniciando orquestração de scraping para: {request.product_name}")

        import time

        start_time = time.time()

        # Estado inicial
        initial_state: ScrapingState = {
            "request": request,
            "products": [],
            "errors": [],
            "completed_sites": [],
            "messages": [],
        }

        try:
            # Executa o grafo
            final_state = await asyncio.get_event_loop().run_in_executor(
                None, self.graph.invoke, initial_state
            )

            execution_time = time.time() - start_time

            # Cria resultado final
            result = ScrapingResult(
                request=request,
                products=final_state["products"],
                errors=final_state["errors"],
                total_found=len(final_state["products"]),
                execution_time=execution_time,
            )

            logger.success(f"Orquestração concluída em {execution_time:.2f}s")
            return result

        except Exception as e:
            logger.error(f"Erro na orquestração: {str(e)}")
            execution_time = time.time() - start_time

            return ScrapingResult(
                request=request,
                products=[],
                errors=[f"Erro na orquestração: {str(e)}"],
                total_found=0,
                execution_time=execution_time,
            )
