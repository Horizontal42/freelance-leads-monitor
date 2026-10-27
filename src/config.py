"""Unified configuration loading credentials from .env and application settings from config.yml."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_YAML_PATH = BASE_DIR / "config.yml"


# ==========================================
# 1. Структура конфигурации из config.yml
# ==========================================

class StorageConfig(BaseModel):
    db_path: str = "data/jobs.db"


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8086


class PollingConfig(BaseModel):
    interval_seconds: int = 180
    kwork_interval: int = 180
    fl_interval: int = 180
    initial_backfill: bool = True


class KworkCollectorConfig(BaseModel):
    base_url: str = "https://kwork.ru"
    category_ids: List[int] = Field(default_factory=lambda: [11, 41])
    max_pages: int = 5
    include_all_pages: int = 2


class FlRuCollectorConfig(BaseModel):
    rss_url: str = "https://www.fl.ru/rss/all.xml"


class FreelanceRuCollectorConfig(BaseModel):
    base_url: str = "https://freelance.ru"
    categories: List[int] = Field(default_factory=lambda: [4, 724])
    normal_pages: int = 2
    backfill_pages: int = 4


class PchelNetCollectorConfig(BaseModel):
    base_url: str = "https://pchel.net"
    usd_rate: float = 95.0
    normal_pages: int = 1
    backfill_pages: int = 3


class RemoteJobCollectorConfig(BaseModel):
    base_url: str = "https://remote-job.ru"
    normal_pages: int = 1
    backfill_pages: int = 3


class HhRuCollectorConfig(BaseModel):
    base_url: str = "https://api.hh.ru"
    enabled: bool = True
    days: int = 30
    area: Optional[List[int]] = None
    work_format: List[str] = Field(default_factory=list)
    max_pages: int = 2
    per_page: int = 50
    queries: List[str] = Field(
        default_factory=lambda: [
            "NAME:(AI OR ИИ) AND NAME:(инженер OR engineer OR разработчик OR developer)",
            "NAME:(junior OR джуниор OR стажер OR стажёр OR intern) AND NAME:(AI OR ИИ OR LLM OR ML OR нейросет*)",
            'NAME:(ML OR "machine learning" OR "машинное обучение") AND NAME:(инженер OR engineer OR разработчик OR developer OR стажер OR стажёр)',
            "NAME:(LLM OR RAG OR GPT)",
            "NAME:Python AND NAME:(AI OR ИИ OR LLM OR нейросет* OR ML)",
            'NAME:"computer vision" OR NAME:"компьютерное зрение"',
            'NAME:(AI-агент* OR ИИ-агент* OR "AI agent")',
            'NAME:(промпт-инженер OR "prompt engineer")',
        ]
    )
    drop_title: str = r"middle|мидл|senior|сеньор|\blead\b|тимлид|team lead|ведущ|старш|principal|head of|руководител|архитектор|architect"
    junior_title: str = r"junior|джуниор|\bджун\b|стаж[её]р|стажировк|\bintern\b|\binternship\b|\btrainee\b|начинающ|младш"
    drop_experience: List[str] = Field(default_factory=lambda: ["От 3 до 6 лет", "Более 6 лет"])
    stop_title_hard: List[str] = Field(
        default_factory=lambda: [
            r"\bsmm\b",
            "копирайт",
            r"сбор\w* данных",
            r"разметчик|разметк\w+ данных|ai[- ]?тренер|ai trainer",
        ]
    )
    stop_title_soft: List[str] = Field(
        default_factory=lambda: [
            r"продаж|\bsales\b|продавец",
            r"маркетолог|маркетинг|marketing",
            r"наставник|куратор|тренер|преподав|менторств|\bкурс(?:ы|ов|а|е|у)?\b|школ|обучени\w*\s+(?:нейросет|ии\b|ai\b|персонал|сотрудник)",
            r"системн\w+ администратор|администриров",
            r"робот|\brobot",
        ]
    )
    engineering_marker: str = r"инженер|engineer|разработчик|developer|программист|\bml\b|\bllm\b|\brag\b"


class CollectorsConfig(BaseModel):
    kwork: KworkCollectorConfig = Field(default_factory=KworkCollectorConfig)
    fl_ru: FlRuCollectorConfig = Field(default_factory=FlRuCollectorConfig)
    freelance_ru: FreelanceRuCollectorConfig = Field(default_factory=FreelanceRuCollectorConfig)
    pchel_net: PchelNetCollectorConfig = Field(default_factory=PchelNetCollectorConfig)
    remote_job: RemoteJobCollectorConfig = Field(default_factory=RemoteJobCollectorConfig)
    hh_ru: HhRuCollectorConfig = Field(default_factory=HhRuCollectorConfig)


class FilterConfig(BaseModel):
    min_budget: int = 10000
    hot_score_threshold: int = 7
    filter_pro_only: bool = False
    stop_words: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class AntigravityConfig(BaseModel):
    binary: str = "agy"
    model: str = "gemini-3.8-flash-medium"
    effort: str = "medium"  # low | medium | high | xhigh | max (пользователь задает сам)
    timeout_seconds: float = 180.0


class MistralModelProfile(BaseModel):
    rpm_limit: int = 30
    max_concurrency: int = 2
    timeout_seconds: float = 60.0
    retry_attempts: int = 3
    retry_min_wait: float = 2.0
    retry_max_wait: float = 10.0


class MistralConfig(BaseModel):
    model: str = "ministral-14b-latest"
    active_model: Optional[str] = None
    timeout_seconds: Optional[float] = None
    max_concurrency: Optional[int] = None
    rpm_limit: Optional[int] = None
    retry_attempts: Optional[int] = None
    retry_min_wait: Optional[float] = None
    retry_max_wait: Optional[float] = None
    models: Dict[str, MistralModelProfile] = Field(
        default_factory=lambda: {
            "ministral-8b-latest": MistralModelProfile(
                rpm_limit=150,
                max_concurrency=4,
                timeout_seconds=40.0,
                retry_attempts=3,
                retry_min_wait=2.0,
                retry_max_wait=8.0,
            ),
            "ministral-14b-latest": MistralModelProfile(
                rpm_limit=25,
                max_concurrency=2,
                timeout_seconds=60.0,
                retry_attempts=3,
                retry_min_wait=2.0,
                retry_max_wait=10.0,
            ),
        }
    )


class LLMConfig(BaseModel):
    provider: str = "antigravity"
    antigravity: AntigravityConfig = Field(default_factory=AntigravityConfig)
    mistral: MistralConfig = Field(default_factory=MistralConfig)


class ProjectDossierItem(BaseModel):
    name: str
    stack: str
    highlights: str
    use_for: str


class DeveloperProfileConfig(BaseModel):
    name: str = "Андрей Пименов"
    username: str = "@horizontal42"
    level: str = "Junior+ / Middle"
    specialization: str = "Python Backend, Telegram-боты, парсинг, CRM"
    min_budget: int = 10000
    hourly_rate_rub: int = 750


class PromptRulesConfig(BaseModel):
    strict_no_em_dash: bool = True
    preview_rule_140_chars: bool = True
    cold_start_strategy: bool = True
    no_ai_cliches: bool = True


class PromptTemplatesConfig(BaseModel):
    analysis_system_prompt: str = ""
    proposal_prompt_template: str = ""
    vacancy_analysis_system_prompt: str = ""
    cover_letter_template: str = ""


class PromptsConfig(BaseModel):
    developer_profile: DeveloperProfileConfig = Field(default_factory=DeveloperProfileConfig)
    projects_dossier: List[ProjectDossierItem] = Field(default_factory=list)
    rules: PromptRulesConfig = Field(default_factory=PromptRulesConfig)
    templates: PromptTemplatesConfig = Field(default_factory=PromptTemplatesConfig)


class YamlAppConfig(BaseModel):
    storage: StorageConfig = Field(default_factory=StorageConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    collectors: CollectorsConfig = Field(default_factory=CollectorsConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)


def load_yaml_config(yaml_path: Path) -> YamlAppConfig:
    """Загрузить и провалидировать config.yml."""
    if not yaml_path.exists():
        logger.warning("Файл %s не найден, используются дефолтные параметры", yaml_path)
        return YamlAppConfig()

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
        return YamlAppConfig.model_validate(raw_data)
    except Exception as e:
        logger.error("Ошибка чтения %s: %s. Используются дефолтные параметры.", yaml_path, e)
        return YamlAppConfig()


# ==========================================
# 2. Секреты и учетные данные из .env
# ==========================================

class Secrets(BaseSettings):
    """Секреты и токены, читаемые строго из .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = ""
    ADMIN_CHAT_ID: int = 0
    MISTRAL_API_KEY: str = ""
    HH_APP_TOKEN: str = ""
    HH_USER_AGENT: str = "JobSearch/1.0 (frolka84@gmail.com)"


# ==========================================
# 3. Единый фасад настроек (Settings)
# ==========================================

class Settings:
    """Единый фасад для доступа к секретам (.env) и конфигурации (config.yml)."""

    def __init__(
        self,
        yaml_path: Optional[Path] = None,
        env_file: Optional[Path] = None,
    ) -> None:
        self.yaml_path = yaml_path or CONFIG_YAML_PATH
        self.app_config = load_yaml_config(self.yaml_path)
        self.secrets = Secrets(_env_file=env_file or (BASE_DIR / ".env"))

    # Секреты из .env
    @property
    def BOT_TOKEN(self) -> str:
        return self.secrets.BOT_TOKEN

    @property
    def ADMIN_CHAT_ID(self) -> int:
        return self.secrets.ADMIN_CHAT_ID

    @property
    def MISTRAL_API_KEY(self) -> str:
        return self.secrets.MISTRAL_API_KEY

    @property
    def HH_APP_TOKEN(self) -> str:
        return self.secrets.HH_APP_TOKEN

    @property
    def HH_USER_AGENT(self) -> str:
        return self.secrets.HH_USER_AGENT

    # База данных
    @property
    def DB_PATH(self) -> Path:
        p = Path(self.app_config.storage.db_path)
        return p if p.is_absolute() else (BASE_DIR / p)

    # Веб-дашборд
    @property
    def WEB_HOST(self) -> str:
        return self.app_config.web.host

    @property
    def WEB_PORT(self) -> int:
        return self.app_config.web.port

    # Интервалы опроса
    @property
    def KWORK_POLL_INTERVAL(self) -> int:
        return self.app_config.polling.kwork_interval

    @property
    def FL_POLL_INTERVAL(self) -> int:
        return self.app_config.polling.fl_interval

    # Источники
    @property
    def KWORK_BASE_URL(self) -> str:
        return self.app_config.collectors.kwork.base_url

    @property
    def KWORK_CATEGORY_IDS(self) -> List[int]:
        return self.app_config.collectors.kwork.category_ids

    @property
    def KWORK_MAX_PAGES(self) -> int:
        return self.app_config.collectors.kwork.max_pages

    @property
    def KWORK_INCLUDE_ALL_PAGES(self) -> int:
        return self.app_config.collectors.kwork.include_all_pages

    @property
    def FL_RSS_URL(self) -> str:
        return self.app_config.collectors.fl_ru.rss_url

    @property
    def FREELANCE_RU_BASE_URL(self) -> str:
        return self.app_config.collectors.freelance_ru.base_url

    @property
    def FREELANCE_RU_CATEGORIES(self) -> List[int]:
        return self.app_config.collectors.freelance_ru.categories

    @property
    def FREELANCE_RU_NORMAL_PAGES(self) -> int:
        return self.app_config.collectors.freelance_ru.normal_pages

    @property
    def FREELANCE_RU_BACKFILL_PAGES(self) -> int:
        return self.app_config.collectors.freelance_ru.backfill_pages

    @property
    def PCHEL_NET_BASE_URL(self) -> str:
        return self.app_config.collectors.pchel_net.base_url

    @property
    def PCHEL_NET_USD_RATE(self) -> float:
        return self.app_config.collectors.pchel_net.usd_rate

    @property
    def PCHEL_NET_NORMAL_PAGES(self) -> int:
        return self.app_config.collectors.pchel_net.normal_pages

    @property
    def PCHEL_NET_BACKFILL_PAGES(self) -> int:
        return self.app_config.collectors.pchel_net.backfill_pages

    @property
    def REMOTE_JOB_BASE_URL(self) -> str:
        return self.app_config.collectors.remote_job.base_url

    @property
    def REMOTE_JOB_NORMAL_PAGES(self) -> int:
        return self.app_config.collectors.remote_job.normal_pages

    @property
    def REMOTE_JOB_BACKFILL_PAGES(self) -> int:
        return self.app_config.collectors.remote_job.backfill_pages

    @property
    def COLLECTORS_HH_RU(self) -> HhRuCollectorConfig:
        return self.app_config.collectors.hh_ru

    @property
    def POLLING_INTERVAL_SECONDS(self) -> int:
        return self.app_config.polling.interval_seconds

    @property
    def INITIAL_BACKFILL(self) -> bool:
        return self.app_config.polling.initial_backfill

    # Фильтры
    @property
    def MIN_BUDGET(self) -> int:
        return self.app_config.filter.min_budget

    @property
    def HOT_SCORE_THRESHOLD(self) -> int:
        return self.app_config.filter.hot_score_threshold

    @property
    def FILTER_PRO_ONLY(self) -> bool:
        return self.app_config.filter.filter_pro_only

    @property
    def STOP_WORDS(self) -> List[str]:
        return self.app_config.filter.stop_words

    @property
    def KEYWORDS(self) -> List[str]:
        return self.app_config.filter.keywords

    # LLM
    @property
    def LLM_PROVIDER(self) -> str:
        return self.app_config.llm.provider

    @property
    def ANTIGRAVITY_BIN(self) -> str:
        return self.app_config.llm.antigravity.binary

    @property
    def ANTIGRAVITY_MODEL(self) -> str:
        return self.app_config.llm.antigravity.model

    @property
    def ANTIGRAVITY_PROPOSAL_MODEL(self) -> str:
        return self.app_config.llm.antigravity.proposal_model

    @property
    def ANTIGRAVITY_EFFORT(self) -> str:
        return self.app_config.llm.antigravity.effort

    @property
    def ANTIGRAVITY_TIMEOUT(self) -> float:
        return self.app_config.llm.antigravity.timeout_seconds

    @property
    def MISTRAL_MODEL(self) -> str:
        cfg = self.app_config.llm.mistral
        return cfg.active_model or cfg.model or "ministral-14b-latest"

    @property
    def _MISTRAL_ACTIVE_PROFILE(self) -> MistralModelProfile:
        cfg = self.app_config.llm.mistral
        model_name = self.MISTRAL_MODEL
        if model_name in cfg.models:
            return cfg.models[model_name]
        return MistralModelProfile()

    @property
    def MISTRAL_TIMEOUT(self) -> float:
        cfg = self.app_config.llm.mistral
        if cfg.timeout_seconds is not None:
            return cfg.timeout_seconds
        return self._MISTRAL_ACTIVE_PROFILE.timeout_seconds

    @property
    def MISTRAL_MAX_CONCURRENCY(self) -> int:
        cfg = self.app_config.llm.mistral
        if cfg.max_concurrency is not None:
            return cfg.max_concurrency
        return self._MISTRAL_ACTIVE_PROFILE.max_concurrency

    @property
    def MISTRAL_RPM_LIMIT(self) -> int:
        cfg = self.app_config.llm.mistral
        if cfg.rpm_limit is not None:
            return cfg.rpm_limit
        return self._MISTRAL_ACTIVE_PROFILE.rpm_limit

    @property
    def MISTRAL_RETRY_ATTEMPTS(self) -> int:
        cfg = self.app_config.llm.mistral
        if cfg.retry_attempts is not None:
            return cfg.retry_attempts
        return self._MISTRAL_ACTIVE_PROFILE.retry_attempts

    @property
    def MISTRAL_RETRY_MIN_WAIT(self) -> float:
        cfg = self.app_config.llm.mistral
        if cfg.retry_min_wait is not None:
            return cfg.retry_min_wait
        return self._MISTRAL_ACTIVE_PROFILE.retry_min_wait

    @property
    def MISTRAL_RETRY_MAX_WAIT(self) -> float:
        cfg = self.app_config.llm.mistral
        if cfg.retry_max_wait is not None:
            return cfg.retry_max_wait
        return self._MISTRAL_ACTIVE_PROFILE.retry_max_wait

    # Промпты и досье проектов из config.yml
    @property
    def PROMPTS_CONFIG(self) -> PromptsConfig:
        return self.app_config.prompts

    @property
    def DOSSIER_TEXT(self) -> str:
        items = self.app_config.prompts.projects_dossier
        if not items:
            return ""
        lines = []
        for i, p in enumerate(items, 1):
            lines.append(
                f"{i}. {p.name}: {p.stack}. "
                f"Ключевые решения: {p.highlights}. "
                f"Для каких задач: {p.use_for}."
            )
        return "\n".join(lines)

    @property
    def ANALYSIS_SYSTEM_PROMPT(self) -> str:
        tmpl = self.app_config.prompts.templates.analysis_system_prompt
        if not tmpl:
            return ""
        return tmpl.format(dossier_text=self.DOSSIER_TEXT).strip()

    @property
    def PROPOSAL_PROMPT_TEMPLATE(self) -> str:
        tmpl = self.app_config.prompts.templates.proposal_prompt_template
        if not tmpl:
            return ""
        # Подставляем dossier_text, оставляя {source}, {title}, {price}, {description}, {extra_context} для format
        return tmpl.replace("{dossier_text}", self.DOSSIER_TEXT).strip()

    @property
    def VACANCY_ANALYSIS_SYSTEM_PROMPT(self) -> str:
        tmpl = self.app_config.prompts.templates.vacancy_analysis_system_prompt
        if not tmpl:
            return ""
        return tmpl.format(dossier_text=self.DOSSIER_TEXT).strip()

    @property
    def COVER_LETTER_TEMPLATE(self) -> str:
        tmpl = self.app_config.prompts.templates.cover_letter_template
        if not tmpl:
            return ""
        return tmpl.replace("{dossier_text}", self.DOSSIER_TEXT).strip()


settings = Settings()
