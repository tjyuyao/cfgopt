import cfgopt


def func1(dummy_arg1, **keywords):
    assert dummy_arg1 == "dummy_arg1"
    assert keywords["dummy_kwd1"] == 1
    assert keywords["dummy_kwd2"] == None
    assert keywords["dummy_kwd3"] == "3"
    assert keywords["dummy_kwd4"] == {"x":1}
    assert keywords["dummy_kwd5"] == [4, 5, 7]
    return keywords

def test_blockref_in_list():
    cfg = cfgopt.parse_configs(cfg_root='test_var_keywords/cfg', args=[])["config.json"]

    cfg["func1_1"]()
    assert cfg["func1_1"](dummy_kwd6=6)["dummy_kwd6"] == 6