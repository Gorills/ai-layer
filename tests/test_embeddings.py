from ai_layer.memory.embeddings import HashEmbedding


def test_hash_embedding_is_deterministic_and_normalized():
    model = HashEmbedding(384)
    a, b = model.embed(["hello project memory", "hello project memory"])
    assert a == b
    assert len(a) == 384
    norm = sum(x * x for x in a) ** 0.5
    assert 0.999 < norm < 1.001


def test_embedding_signature_rejects_dimension_drift(monkeypatch):
    from types import SimpleNamespace

    from ai_layer.memory import embeddings

    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: SimpleNamespace(
            embedding_provider="hash",
            embedding_model="ignored",
            embedding_dimensions=768,
        ),
    )
    try:
        embeddings.embedding_signature()
    except RuntimeError as exc:
        assert "schema requires 384" in str(exc)
    else:
        raise AssertionError("dimension drift must fail before vectors reach VECTOR(384)")


def test_fastembed_adapter_rejects_model_with_wrong_dimensions():
    from ai_layer.memory.embeddings import FastEmbedEmbedding

    class Vector:
        def tolist(self):
            return [0.0] * 3

    class Model:
        def embed(self, texts):
            return [Vector() for _ in texts]

    adapter = object.__new__(FastEmbedEmbedding)
    adapter.model_name = "wrong-dimension-model"
    adapter.expected_dimensions = 384
    adapter.model = Model()

    try:
        adapter.embed(["x"])
    except RuntimeError as exc:
        assert "returned 3 dimensions" in str(exc)
    else:
        raise AssertionError("wrong vector dimensions must be rejected")
