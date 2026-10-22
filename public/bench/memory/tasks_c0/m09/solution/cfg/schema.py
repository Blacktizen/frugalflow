def check(cfg, rules):
    failed = []
    for key, predicate in rules.items():
        if key not in cfg or not predicate(cfg[key]):
            failed.append(key)
    return failed
