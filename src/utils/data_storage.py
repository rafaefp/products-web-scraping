import os
import json
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from ..models import ScrapingResult, ProductInfo


class DataStorage:
    """Gerenciador de armazenamento de dados do scraping"""

    def __init__(self, base_path: str = "data"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)

        # Subdiretórios
        self.results_path = self.base_path / "results"
        self.products_path = self.base_path / "products"
        self.logs_path = self.base_path / "logs"

        for path in [self.results_path, self.products_path, self.logs_path]:
            path.mkdir(exist_ok=True)

    def save_scraping_result(
        self, result: ScrapingResult, filename: Optional[str] = None
    ) -> str:
        """Salva resultado completo do scraping"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            product_name = result.request.product_name.replace(" ", "_").lower()
            filename = f"scraping_{product_name}_{timestamp}.json"

        filepath = self.results_path / filename

        # Converte para dict serializable
        result_dict = result.dict()

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2, default=str)

        return str(filepath)

    def save_products_csv(
        self, products: List[ProductInfo], filename: Optional[str] = None
    ) -> str:
        """Salva produtos em formato CSV"""
        import pandas as pd

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"products_{timestamp}.csv"

        filepath = self.products_path / filename

        # Converte produtos para DataFrame
        products_data = [product.dict() for product in products]
        df = pd.DataFrame(products_data)

        # Salva CSV
        df.to_csv(filepath, index=False, encoding="utf-8")

        return str(filepath)

    def load_scraping_result(self, filename: str) -> Optional[ScrapingResult]:
        """Carrega resultado do scraping"""
        filepath = self.results_path / filename

        if not filepath.exists():
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            return ScrapingResult(**data)
        except Exception as e:
            print(f"Erro ao carregar resultado: {e}")
            return None

    def list_results(self) -> List[str]:
        """Lista todos os resultados salvos"""
        return [f.name for f in self.results_path.glob("*.json")]

    def get_latest_result(self) -> Optional[ScrapingResult]:
        """Obtém o resultado mais recente"""
        results = self.list_results()
        if not results:
            return None

        # Ordena por data de modificação
        latest_file = max(
            [self.results_path / f for f in results], key=lambda x: x.stat().st_mtime
        )

        return self.load_scraping_result(latest_file.name)

    def cleanup_old_results(self, days: int = 30):
        """Remove resultados antigos"""
        import time

        cutoff_time = time.time() - (days * 24 * 60 * 60)

        for filepath in self.results_path.glob("*.json"):
            if filepath.stat().st_mtime < cutoff_time:
                filepath.unlink()
                print(f"Removido: {filepath.name}")


class ConfigManager:
    """Gerenciador de configurações"""

    def __init__(self, config_file: str = ".env"):
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Carrega configurações do arquivo .env"""
        config = {}

        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()

        # Configurações padrão
        defaults = {
            "DEBUG": "False",
            "MAX_CONCURRENT_SCRAPERS": "3",
            "REQUEST_TIMEOUT": "30",
            "PAGE_LOAD_TIMEOUT": "10",
            "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        for key, value in defaults.items():
            if key not in config:
                config[key] = value

        return config

    def get(self, key: str, default=None):
        """Obtém valor de configuração"""
        return self.config.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Obtém valor booleano"""
        value = self.get(key, str(default)).lower()
        return value in ["true", "1", "yes", "on"]

    def get_int(self, key: str, default: int = 0) -> int:
        """Obtém valor inteiro"""
        try:
            return int(self.get(key, default))
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Obtém valor float"""
        try:
            return float(self.get(key, default))
        except (ValueError, TypeError):
            return default


class Logger:
    """Configurador de logging"""

    @staticmethod
    def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
        """Configura sistema de logging"""
        from loguru import logger
        import sys

        # Remove configuração padrão
        logger.remove()

        # Configuração para console
        logger.add(
            sys.stdout,
            level=level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True,
        )

        # Configuração para arquivo se especificado
        if log_file:
            logger.add(
                log_file,
                level=level,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                rotation="10 MB",
                retention="30 days",
                compression="zip",
            )

        return logger
