
SMALL = {'a', 'an', 'the', 'of', 'in', 'on', 'and', 'or', 'to'}

def _is_allcaps(word):
    return len(word) >= 2 and word.isalpha() and word == word.upper()

def title_case(s):
    parts = s.split(' ')
    non_empty = [i for i, p in enumerate(parts) if p != '']
    first_i = non_empty[0] if non_empty else -1
    last_i = non_empty[-1] if non_empty else -1
    result = []
    for i, token in enumerate(parts):
        if token == '':
            result.append('')
            continue
        if '-' in token:
            comps = token.split('-')
            processed = []
            for j, comp in enumerate(comps):
                if comp == '':
                    processed.append('')
                    continue
                if _is_allcaps(comp):
                    processed.append(comp)
                elif comp.lower() in SMALL and j != 0 and j != len(comps) - 1:
                    processed.append(comp.lower())
                else:
                    processed.append(comp.capitalize())
            result.append('-'.join(processed))
        else:
            if _is_allcaps(token):
                result.append(token)
            elif token.lower() in SMALL and i != first_i and i != last_i:
                result.append(token.lower())
            else:
                result.append(token.capitalize())
    return ' '.join(result)

