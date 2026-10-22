def check(cfg, rules):
    failed = []
    for key, predicate in rules.items():
        # TODO: report keys that are missing from cfg as failed
        if key not in cfg:
            continue
        if not predicate(cfg[key]):
            failed.append(key)
    return failed
