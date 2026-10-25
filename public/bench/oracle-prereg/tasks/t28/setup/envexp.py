def env_expand(template, env):
    result = []
    i = 0
    n = len(template)
    while i < n:
        ch = template[i]
        if ch == '$':
            if i + 1 < n and template[i + 1] == '$':
                result.append('$')
                i += 2
            elif i + 1 < n and template[i + 1] == '{':
                j = template.find('}', i + 2)
                if j == -1:
                    raise ValueError("unclosed brace")
                inner = template[i + 2:j]
                if ':-' in inner:
                    name, default = inner.split(':-', 1)
                    if name not in env:
                        result.append(default)
                    else:
                        result.append(env_expand(env[name], env))
                else:
                    val = env.get(inner, '')
                    result.append(env_expand(val, env))
                i = j + 1
            else:
                result.append('$')
                i += 1
        else:
            result.append(ch)
            i += 1
    return ''.join(result)

