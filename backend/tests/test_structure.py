"""PER-6 AC5: the backend layout matches ARCHITECTURE.md Section 3."""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

DOMAINS = [
    "api",
    "worker",
    "ingestion",
    "identity",
    "scoring",
    "tabs",
    "lifecycle",
    "digest",
    "backtest",
    "ai",
    "costs",
    "db",
]


def test_every_domain_package_exists_with_init() -> None:
    for domain in DOMAINS:
        assert (BACKEND / "tidewatch" / domain / "__init__.py").is_file(), domain


def test_tests_mirror_every_domain() -> None:
    for domain in DOMAINS:
        assert (BACKEND / "tests" / domain / "__init__.py").is_file(), domain


def test_no_extra_top_level_packages_in_tidewatch() -> None:
    packages = {p.name for p in (BACKEND / "tidewatch").iterdir() if p.is_dir()}
    packages.discard("__pycache__")
    assert packages == set(DOMAINS)


def test_no_technical_layer_folders_at_top_level() -> None:
    """CLAUDE.md §3: no top-level services/ or utils/ folders."""
    for forbidden in ("services", "utils"):
        assert not (REPO / forbidden).exists()
        assert not (BACKEND / forbidden).exists()
        assert not (BACKEND / "tidewatch" / forbidden).exists()


def test_supporting_folders_exist() -> None:
    assert (BACKEND / "scripts").is_dir()
    assert (REPO / "docs" / "spikes").is_dir()
    assert (REPO / "apps" / "web").is_dir()
