import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MYSQL_USER: str = os.getenv("MYSQL_USER", "shortener_user")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_DB: str = os.getenv("MYSQL_DB", "shortener")
    TOKENS_ENV: str = os.getenv("ADMIN_TOKENS", "")

    @property
    def admin_tokens(self) -> set[str]:
        tokens = {t.strip() for t in self.TOKENS_ENV.split(",") if t.strip()}
        if not tokens:
            raise RuntimeError("ADMIN_TOKENS is not configured; set it in the environment.")
        return tokens

    @property
    def database_url(self) -> str:
        from sqlalchemy.engine import URL as DBUrl
        return DBUrl.create(
            "mysql+aiomysql",
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD,
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            database=self.MYSQL_DB,
        )

settings = Settings()
