import cfgopt

def test_blockref_in_list():
    cfg = cfgopt.parse_configs(cfg_root='test_blockref_in_list/cfg')

    # following lines are equivalent
    assert cfg["recipes.json"]["recipe2"]["use_data"][1]["meta"]["location"] == "/data/2/loc"
    assert cfg["recipes.json"]["recipe2/use_data/1/meta/location"] == "/data/2/loc"
    assert cfg["recipes.json/recipe2/use_data/1/meta/location"] == "/data/2/loc"