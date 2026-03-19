from pydantic import BaseModel, Field


class Config(BaseModel):
    cs2radar_priority: int | None = Field(default=None, ge=1, le=20)
    cs2radar_bind_db_path: str | None = Field(default=None)
    cs2radar_http_timeout: int | None = Field(default=None, ge=5, le=60)

    cs2radar_llm_enabled: bool | None = Field(default=None)
    cs2radar_llm_api_type: str | None = Field(default=None)
    cs2radar_llm_api_url: str | None = Field(default=None)
    cs2radar_llm_api_key: str | None = Field(default=None)
    cs2radar_llm_model: str | None = Field(default=None)
    cs2radar_llm_backup_enabled: bool | None = Field(default=None)
    cs2radar_llm_backup_api_type: str | None = Field(default=None)
    cs2radar_llm_backup_api_url: str | None = Field(default=None)
    cs2radar_llm_backup_api_key: str | None = Field(default=None)
    cs2radar_llm_backup_model: str | None = Field(default=None)
    cs2radar_llm_timeout: int | None = Field(default=None, ge=5, le=120)
    cs2radar_llm_system_prompt: str | None = Field(default=None)

    cs_pro_priority: int | None = Field(default=None, ge=1, le=20)
    cs_pro_bind_db_path: str | None = Field(default=None)
    cs_pro_http_timeout: int | None = Field(default=None, ge=5, le=60)
    cs_pro_llm_enabled: bool | None = Field(default=None)
    cs_pro_llm_api_type: str | None = Field(default=None)
    cs_pro_llm_api_url: str | None = Field(default=None)
    cs_pro_llm_api_key: str | None = Field(default=None)
    cs_pro_llm_model: str | None = Field(default=None)
    cs_pro_llm_backup_enabled: bool | None = Field(default=None)
    cs_pro_llm_backup_api_type: str | None = Field(default=None)
    cs_pro_llm_backup_api_url: str | None = Field(default=None)
    cs_pro_llm_backup_api_key: str | None = Field(default=None)
    cs_pro_llm_backup_model: str | None = Field(default=None)
    cs_pro_llm_timeout: int | None = Field(default=None, ge=5, le=120)
    cs_pro_llm_system_prompt: str | None = Field(default=None)

    @staticmethod
    def _pick(new_value, old_value, default):
        if new_value is not None:
            return new_value
        if old_value is not None:
            return old_value
        return default

    @property
    def priority(self) -> int:
        return int(self._pick(self.cs2radar_priority, self.cs_pro_priority, 5))

    @property
    def bind_db_path(self) -> str:
        return str(self._pick(self.cs2radar_bind_db_path, self.cs_pro_bind_db_path, "") or "")

    @property
    def http_timeout(self) -> int:
        return int(self._pick(self.cs2radar_http_timeout, self.cs_pro_http_timeout, 15))

    @property
    def llm_enabled(self) -> bool:
        return bool(self._pick(self.cs2radar_llm_enabled, self.cs_pro_llm_enabled, True))

    @property
    def llm_api_type(self) -> str:
        return str(self._pick(self.cs2radar_llm_api_type, self.cs_pro_llm_api_type, "openai"))

    @property
    def llm_api_url(self) -> str:
        return str(self._pick(self.cs2radar_llm_api_url, self.cs_pro_llm_api_url, "https://api.openai.com/v1"))

    @property
    def llm_api_key(self) -> str:
        return str(self._pick(self.cs2radar_llm_api_key, self.cs_pro_llm_api_key, "") or "")

    @property
    def llm_model(self) -> str:
        return str(self._pick(self.cs2radar_llm_model, self.cs_pro_llm_model, "gpt-4o-mini"))

    @property
    def llm_backup_enabled(self) -> bool:
        return bool(self._pick(self.cs2radar_llm_backup_enabled, self.cs_pro_llm_backup_enabled, False))

    @property
    def llm_backup_api_type(self) -> str:
        return str(self._pick(self.cs2radar_llm_backup_api_type, self.cs_pro_llm_backup_api_type, "openai"))

    @property
    def llm_backup_api_url(self) -> str:
        return str(self._pick(self.cs2radar_llm_backup_api_url, self.cs_pro_llm_backup_api_url, "https://api.openai.com/v1"))

    @property
    def llm_backup_api_key(self) -> str:
        return str(self._pick(self.cs2radar_llm_backup_api_key, self.cs_pro_llm_backup_api_key, "") or "")

    @property
    def llm_backup_model(self) -> str:
        return str(self._pick(self.cs2radar_llm_backup_model, self.cs_pro_llm_backup_model, "gpt-4o-mini"))

    @property
    def llm_timeout(self) -> int:
        return int(self._pick(self.cs2radar_llm_timeout, self.cs_pro_llm_timeout, 30))

    @property
    def llm_system_prompt(self) -> str:
        return str(
            self._pick(
                self.cs2radar_llm_system_prompt,
                self.cs_pro_llm_system_prompt,
                (
                    "你是一名职业CS2战队的数据分析师。请根据提供的对局数据，进行深入的战术复盘和表现分析。"
                    "输出必须是严格的JSON格式，包含以下字段："
                    "1. title: 用8-16个字精准概括该玩家（主角）的本场表现风格（如‘进攻端突破核心’或‘防守端稳健支柱’）。"
                    "2. detail: 撰写500字的详细分析报告。内容应包含："
                    "   - 团队整体表现分析（攻防节奏、关键局势）。"
                    "   - 主角（Player）的个人表现评价（Rating/ADR/KDA等数据的战术意义）。"
                    "   - 队友与对手的关键互动或差距分析。"
                    "   - 针对性的改进建议或战术调整方向。"
                    "   - 语言风格需专业、客观、犀利，像是在战队复盘会上发言。"
                ),
            )
        )
