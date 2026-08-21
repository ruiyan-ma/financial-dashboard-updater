"""Environment configuration for the transaction tracker."""

from dotenv import load_dotenv

from shared.utils import required_env


class TrackerConfig:
    """Environment configuration for the transaction tracker."""

    def __init__(self):
        load_dotenv()
        self.notion_token = required_env("INTERNAL_INTEGRATION_TOKEN")
        self.inc_exp_db_id = required_env("INC_EXP_DATABASE_ID")
        self.category_db_id = required_env("CATEGORIES_DATABASE_ID")
        self.account_db_id = required_env("ACCOUNTS_DATABASE_ID")
        self.model_api_key = required_env("MODEL_API_KEY")
        self.model_base_url = required_env("MODEL_BASE_URL")
        self.model_name = required_env("MODEL_NAME")
        self.cache_ttl_seconds = int(required_env("CACHE_TTL_SECONDS"))
        self.port = int(required_env("TRIGGER_PORT"))
