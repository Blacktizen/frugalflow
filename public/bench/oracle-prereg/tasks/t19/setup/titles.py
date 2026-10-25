
SMALL = {'a', 'an', 'the', 'of', 'in', 'on', 'and', 'or', 'to'}

def title_case(s):
    parts = s.split(' ')
    non_empty = [i for i, p in enumerate(parts) if p != '']
    first_i = non_empty[0] if non_empty else -1
    last_i = non_empty[-1] if non_empty else -1
    result = []
    for i, word in enumerate(parts):
        if word == '':
            result.append('')
            continue
        if i == first_i or i == last_i:
            result.append(word.capitalize())
        elif word.lower() in SMALL:
            result.append(word.lower())
        else:
            result.append(word.capitalize())
    return ' '.join(result)

