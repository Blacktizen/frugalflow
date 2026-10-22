import sys
import os
import subprocess

TRUST = ["private", "trusted_third_party", "untrusted_third_party"]

GOOD = {"models": [{"id": "a", "trust": "private"}, {"id": "r", "trust": "untrusted_third_party"}],
 "layers": [{"name": "reading", "delegable": True}, {"name": "kept", "delegable": False}],
 "roles": [{"name": "code", "layer": "reading", "model": "a"},
           {"name": "remote", "layer": "reading", "model": "r"},
           {"name": "judgment", "layer": "kept", "model": ""}]}

BAD = {"models": [{"id": "a", "trust": "private"}],
 "layers": [{"name": "reading", "delegable": True}, {"name": "kept", "delegable": False},
            {"name": "review", "delegable": True}, {"name": "reading", "delegable": True}],
 "roles": [{"name": "code", "model": "a"},
           {"name": "docs", "layer": "writing", "model": "a"},
           {"name": "judgment", "layer": "kept", "model": "a"},
           {"name": "read", "layer": "reading", "model": "zz"}]}


def verify(doc):
    if not isinstance(doc, dict):
        return ["document must be an object"]

    layers = doc.get("layers")
    if not isinstance(layers, list) or len(layers) == 0:
        return ["layers must be a non-empty list"]

    roles = doc.get("roles")
    if not isinstance(roles, list) or len(roles) == 0:
        return ["roles must be a non-empty list"]

    errors = []
    known_layer_names = set()
    layer_order = []

    for i, layer in enumerate(layers):
        P = "layers[" + str(i) + "]"
        if not isinstance(layer, dict):
            errors.append(P + " must be an object")
            continue
        name = layer.get("name")
        if not isinstance(name, str) or len(name) == 0:
            errors.append(P + ".name must be a non-empty string")
        else:
            if name in known_layer_names:
                errors.append(P + ".name duplicates " + name)
            else:
                known_layer_names.add(name)
                layer_order.append(name)
        delegable = layer.get("delegable")
        if not isinstance(delegable, bool):
            errors.append(P + ".delegable must be true or false")

    models = doc.get("models")
    known_model_ids = set()
    if isinstance(models, list):
        for m in models:
            if isinstance(m, dict) and "id" in m:
                known_model_ids.add(m["id"])

    layer_delegable = {}
    for name in layer_order:
        for l in layers:
            if isinstance(l, dict) and l.get("name") == name:
                layer_delegable[name] = l.get("delegable")
                break

    seen_role_names = set()
    for j, role in enumerate(roles):
        P = "roles[" + str(j) + "]"
        if not isinstance(role, dict):
            errors.append(P + " must be an object")
            continue
        name = role.get("name")
        if not isinstance(name, str) or len(name) == 0:
            errors.append(P + ".name must be a non-empty string")
            continue
        if name in seen_role_names:
            errors.append(P + ".name duplicates " + name)
            continue
        seen_role_names.add(name)

        layer_name = role.get("layer")
        if not isinstance(layer_name, str) or len(layer_name) == 0:
            errors.append(P + ".layer is missing")
            continue
        if layer_name not in known_layer_names:
            errors.append(P + ".layer names unknown layer " + layer_name)
            continue

        model = role.get("model", "")
        if layer_delegable[layer_name] is False:
            if model != "":
                errors.append(P + " is in kept layer " + layer_name + " and may not be given a model")
        else:
            if model not in known_model_ids:
                errors.append(P + ".model names unknown model " + str(model))

    for name in layer_order:
        used = False
        for role in roles:
            if isinstance(role, dict) and role.get("layer") == name:
                used = True
                break
        if not used:
            errors.append("layer " + name + " is empty")

    return errors


def route(doc, role_name, max_trust):
    if max_trust not in TRUST:
        return (None, "unknown trust ceiling " + str(max_trust))

    role = None
    if isinstance(doc, dict):
        roles = doc.get("roles")
        if isinstance(roles, list):
            for r in roles:
                if isinstance(r, dict) and r.get("name") == role_name:
                    role = r
                    break
    if role is None:
        return (None, "unknown role " + role_name)

    layer_name = role.get("layer")
    layer = None
    if isinstance(doc, dict):
        layers = doc.get("layers")
        if isinstance(layers, list):
            for l in layers:
                if isinstance(l, dict) and l.get("name") == layer_name:
                    layer = l
                    break
    if layer is None:
        return (None, "role " + role_name + " names unknown layer " + str(layer_name))

    if layer.get("delegable") is False:
        return (None, "role " + role_name + " is in kept layer " + layer_name + ": it is never delegated")

    model_id = role.get("model")
    model = None
    if isinstance(doc, dict):
        models = doc.get("models")
        if isinstance(models, list):
            for m in models:
                if isinstance(m, dict) and m.get("id") == model_id:
                    model = m
                    break
    if model is None:
        return (None, "role " + role_name + " names unknown model " + str(model_id))

    trust = model.get("trust")
    if trust not in TRUST:
        return (None, "model " + str(model_id) + " has unknown trust " + str(trust))

    if TRUST.index(trust) > TRUST.index(max_trust):
        return (None, "model " + str(model_id) + " trust " + trust + " exceeds ceiling " + max_trust)

    return (model, "")


def _notice():
    sys.stdout.write(
        "NAME      layers.py - checks the delegation layers and roles, and says which model does a role under a trust ceiling.\n"
        "READS     nothing: pure module; verify() and route() read the decoded models.json they are given.\n"
        "WRITES    nothing: verify() returns error lines, route() returns the model or the reason it refuses.\n"
        "EXAMPLE   python3 layers.py --notice\n"
        "PITFALLS  2026-09-23 the old trust check treated an unknown ceiling as the loosest one: it failed open.\n"
        "          route() now refuses an unknown ceiling or an unknown trust level.\n"
    )


def _autotest():
    failures = 0

    # Test 1
    expected = []
    got = verify(GOOD)
    if got == expected:
        print("PASS 1: verify(GOOD) == []")
    else:
        print("FAIL 1: verify(GOOD) expected %r got %r" % (expected, got))
        failures += 1

    # Test 2
    expected = [
        "layers[3].name duplicates reading",
        "roles[0].layer is missing",
        "roles[1].layer names unknown layer writing",
        "roles[2] is in kept layer kept and may not be given a model",
        "roles[3].model names unknown model zz",
        "layer review is empty",
    ]
    got = verify(BAD)
    if got == expected:
        print("PASS 2: verify(BAD) == 6 expected errors")
    else:
        print("FAIL 2: verify(BAD) expected %r got %r" % (expected, got))
        failures += 1

    # Test 3
    got = route(GOOD, "code", "private")
    ok3 = (
        isinstance(got, tuple)
        and len(got) == 2
        and isinstance(got[0], dict)
        and got[0].get("id") == "a"
        and got[1] == ""
    )
    if ok3:
        print("PASS 3: route(GOOD,'code','private') returns model id='a'")
    else:
        print("FAIL 3: route(GOOD,'code','private') expected (dict id='a','') got %r" % (got,))
        failures += 1

    # Test 4
    t4a = route(GOOD, "remote", "private")
    t4b = route(GOOD, "judgment", "untrusted_third_party")
    t4c = route(GOOD, "code", "everything")
    exp4a = (None, "model r trust untrusted_third_party exceeds ceiling private")
    exp4b = (None, "role judgment is in kept layer kept: it is never delegated")
    exp4c = (None, "unknown trust ceiling everything")
    if t4a == exp4a and t4b == exp4b and t4c == exp4c:
        print("PASS 4: three route() refusals match")
    else:
        print("FAIL 4: route() refusals expected %r %r %r got %r %r %r" % (exp4a, exp4b, exp4c, t4a, t4b, t4c))
        failures += 1

    # Test 5
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    ok5 = proc.returncode == 0 and proc.stdout.startswith("NAME      layers.py")
    if ok5:
        print("PASS 5: subprocess --notice exit 0, stdout starts with NAME")
    else:
        print("FAIL 5: subprocess --notice exit %d stdout[:40]=%r" % (proc.returncode, proc.stdout[:40]))
        failures += 1

    sys.exit(1 if failures else 0)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        _notice()
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        _autotest()
    else:
        print("usage: layers.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "layers", sys.argv[1:])
