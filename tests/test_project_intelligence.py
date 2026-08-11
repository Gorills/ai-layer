from types import SimpleNamespace
from pathlib import Path

from ai_layer.memory.intelligence import build_project_intelligence
from ai_layer.memory.source import parse_dependencies


def _row(path: str, language: str | None = None, risks: list[str] | None = None):
    return SimpleNamespace(path=path, language=language, indexed=True, risk_flags=risks or [])


def test_project_intelligence_maps_laravel_docker_persistence_design_seo_and_docs(tmp_path: Path):
    files = {
        "composer.json": '{"require":{"php":"^8.3","laravel/framework":"^12.0"}}',
        "package.json": '{"dependencies":{"vue":"^3.5","vite":"^7.0"}}',
        "artisan": "#!/usr/bin/env php\n",
        "routes/web.php": "<?php Route::get('/products', fn () => 'ok');\n",
        "config/filesystems.php": "<?php return ['default' => 'local'];\n",
        "database/migrations/2026_01_01_create_products.php": "<?php // migration\n",
        "storage/app/.gitignore": "*\n",
        "compose.yaml": """
services:
  app:
    build: .
    volumes:
      - .:/var/www/html
      - media:/var/www/html/storage/app/public
    depends_on: [db]
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  media: {}
  pgdata: {}
""",
        "Dockerfile": "FROM php:8.3-fpm\nWORKDIR /var/www/html\n",
        "resources/css/theme.css": ":root{--color-primary:#224466;--space-2:8px} body{font-family:Inter,sans-serif;border-radius:8px}",
        "resources/js/pages/Product.vue": '<template><main><h1>Product</h1><button>Buy</button></main></template><script>const metadata={description:"x",canonical:"/p"}</script>',
        "public/robots.txt": "User-agent: *\nAllow: /\nSitemap: https://example.test/sitemap.xml\n",
        "public/sitemap.xml": "<urlset></urlset>",
        "docs/DEPLOY.md": "# Deploy\nRun containers and migrations.\n",
        ".env.example": "APP_ENV=local\nDB_HOST=db\n",
        "app/Services/LegacyPayment.php": "<?php\n// TODO compatibility\n" + ("x" * 60000),
    }
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    rows = [
        _row("composer.json"), _row("package.json"), _row("artisan"),
        _row("routes/web.php", "php"), _row("config/filesystems.php", "php"),
        _row("database/migrations/2026_01_01_create_products.php", "php"), _row("storage/app/.gitignore"),
        _row("compose.yaml", "yaml"),
        _row("Dockerfile"), _row("resources/css/theme.css", "css"),
        _row("resources/js/pages/Product.vue", "vue"), _row("public/robots.txt"), _row("public/sitemap.xml"),
        _row("docs/DEPLOY.md", "markdown"), _row(".env.example"),
        _row("app/Services/LegacyPayment.php", "php", ["large_file", "contains_todo_or_fixme"]),
    ]
    dependencies = parse_dependencies(tmp_path)
    intelligence = build_project_intelligence(
        tmp_path,
        rows,
        {"php": 2, "vue": 1, "css": 1},
        dependencies,
    )

    assert "laravel/framework@^12.0" in dependencies["composer"]
    assert {"laravel", "vue"} <= set(intelligence["stack"]["frameworks"])
    laravel = intelligence["stack"]["framework_details"]["laravel"]
    assert laravel["route_files"] == ["routes/web.php"]
    assert laravel["migration_files"] == 1
    assert "config/filesystems.php" in laravel["config_files"]
    assert intelligence["docker"]["present"] is True
    assert intelligence["docker"]["source_bind_mounts"][0]["role"] == "source_code"
    roles = {item["role"] for item in intelligence["docker"]["persistent_mounts"]}
    assert {"database_data", "user_media"} <= roles
    assert "postgresql" in intelligence["data"]["databases"]
    assert intelligence["design"]["design_system_signal"] == "explicit_tokens"
    assert intelligence["design"]["css_custom_properties"]["--color-primary"] == "#224466"
    assert intelligence["seo"]["public_web_surface"] is True
    assert intelligence["documentation"]["domains"]["deployment"] == ["docs/DEPLOY.md"]
    assert intelligence["legacy"]["level"] in {"medium", "high"}
    assert {"docker", "frontend", "design-system", "public-web", "project-docs", "legacy-fragility"} <= set(intelligence["signals"])

    # Project Intelligence remains scanner evidence only; it no longer selects skills.

