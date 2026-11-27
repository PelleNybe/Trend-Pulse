import shutil
from pathlib import Path

TYPED_FIELD_DEFAULTS = {
    "HOST": ("str", '"0.0.0.0"'),
    "PORT": ("int", "5000"),
    "DB_PORT": ("int", "3306"),
    "DB_DIALECT": ("str", '"postgresql"'),
    "DB_CHARSET": ("str", '"utf8mb4"'),
    "REDIS_HOST": ("str", '"localhost"'),
    "REDIS_PORT": ("int", "6379"),
    "REDIS_DB": ("int", "0"),
    "SEARCH_TOOL_TYPE": ("str", '"AnspireAPI"'),
    "ANSPIRE_BASE_URL": ("str", '"https://plugin.anspire.cn/api/ntsearch/search"'),
    "BOCHA_BASE_URL": ("str", '"https://api.bocha.cn/v1/ai-search"'),
    "OUTPUT_DIR": ("str", '"reports"'),
    "SAVE_INTERMEDIATE_STATES": ("bool", "True"),
    "MAX_REFLECTIONS": ("int", "2"),
    "MAX_CONTENT_LENGTH": ("int", "500000"),
    "SEARCH_CONTENT_MAX_LENGTH": ("int", "20000"),
    "MAX_SEARCH_RESULTS_FOR_LLM": ("int", "0"),
    "DEFAULT_SEARCH_HOT_CONTENT_LIMIT": ("int", "100"),
    "DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE": ("int", "50"),
    "DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE": ("int", "100"),
    "DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT": ("int", "500"),
    "DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT": ("int", "200"),
    "CHAPTER_OUTPUT_DIR": ("str", '"final_reports/chapters"'),
    "DOCUMENT_IR_OUTPUT_DIR": ("str", '"final_reports/ir"'),
    "JSON_ERROR_LOG_DIR": ("str", '"logs/json_errors"'),
    "LOG_FILE": ("str", '"logs/report.log"'),
    "TEMPLATE_DIR": ("str", '"ReportEngine/report_template"'),
    "CHAPTER_JSON_MAX_ATTEMPTS": ("int", "2"),
    "WEBHOOK_ENDPOINTS": ("str", '"[]"'),
}


def generate_config(base_dir: Path | None = None):
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parent
    env_file = root / ".env"
    example_file = root / ".env.example"

    if not env_file.exists():
        if example_file.exists():
            print("Creating .env from .env.example")
            shutil.copy2(example_file, env_file)
        else:
            print("No .env or .env.example found.")
            return

    keys_seen = []
    for src in (example_file, env_file):
        if not src.exists():
            continue
        for raw_line in src.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=", 1)[0].strip()
                if key and key not in keys_seen:
                    keys_seen.append(key)

    for key in TYPED_FIELD_DEFAULTS:
        if key not in keys_seen:
            keys_seen.append(key)

    lines = [
        "from pathlib import Path",
        "from typing import Any, Optional",
        "from pydantic import ConfigDict, Field",
        "from pydantic_settings import BaseSettings",
        "",
        "PROJECT_ROOT: Path = Path(__file__).resolve().parents[0]",
        'CWD_ENV: Path = Path.cwd() / ".env"',
        'ENV_FILE: str = str(CWD_ENV if CWD_ENV.exists() else (PROJECT_ROOT / ".env"))',
        "",
        "",
        "class Settings(BaseSettings):",
    ]

    for key in keys_seen:
        if key in TYPED_FIELD_DEFAULTS:
            py_type, default_expr = TYPED_FIELD_DEFAULTS[key]
            lines.append(
                f'    {key}: {py_type} = Field({default_expr}, description="{key}")'
            )
        else:
            lines.append(
                f'    {key}: Optional[str] = Field(None, description="{key}")'
            )

    lines.extend(
        [
            "",
            "    def get(self, key: str, default: Any = None) -> Any:",
            '        """Dict-style accessor for legacy callers."""',
            "        value = getattr(self, key, default)",
            "        return default if value is None else value",
            "",
            "    model_config = ConfigDict(",
            "        env_file=ENV_FILE,",
            '        env_prefix="",',
            "        case_sensitive=False,",
            '        extra="allow",',
            "    )",
            "",
            "",
            "def reload_settings():",
            "    global settings",
            "    settings = Settings()",
            "    return settings",
            "",
            "",
            "settings = Settings()",
            "",
        ]
    )

    config_path = root / "config.py"
    config_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {config_path}")


if __name__ == "__main__":
    generate_config()
