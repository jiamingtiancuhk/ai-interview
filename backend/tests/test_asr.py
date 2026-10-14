from app.asr import _prompt, _tidy, vocabulary


def test_vocabulary_extracts_tech_terms_in_order_without_duplicates():
    terms = vocabulary("你怎么保证 Kafka 消息不丢？", "熟悉 Go、kafka、Redis、K8s，P99 从 800ms 降到 120ms，C++ 和 Node.js")
    assert terms[:2] == ["Kafka", "Go"]
    assert "kafka" not in terms  # case-insensitive dedupe
    for t in ["Redis", "K8s", "P99", "C++", "Node.js"]:
        assert t in terms


def test_prompt_lists_terms():
    assert _prompt("zh", ["Kafka", "Redis"]).endswith("可能出现的术语：Kafka、Redis。")
    assert "Terms: Kafka, Redis." in _prompt("en", ["Kafka", "Redis"])


def test_chinese_punctuation_is_full_width_but_english_untouched():
    assert _tidy("我负责下单,然后写 Kafka,好吗?", "zh") == "我负责下单，然后写 Kafka，好吗？"
    assert _tidy("v1.2, ok?", "zh") == "v1.2, ok?"
