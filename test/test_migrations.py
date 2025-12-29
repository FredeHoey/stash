import importlib.resources


def test_migrations_package_available():
    migrations_root = importlib.resources.files("migrations")
    assert migrations_root.joinpath("versions").is_dir()
