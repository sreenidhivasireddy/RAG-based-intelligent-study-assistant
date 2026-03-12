import builtins


class _DummyElasticsearch:
    """A tiny placeholder to satisfy type annotations during test collection."""
    pass


# Inject a dummy `Elasticsearch` symbol into builtins so test modules that use
# unqualified annotations like `es: Elasticsearch` don't raise NameError at
# import time when the real `elasticsearch` package isn't installed.
builtins.Elasticsearch = _DummyElasticsearch
