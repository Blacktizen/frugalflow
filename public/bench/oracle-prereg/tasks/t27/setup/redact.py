import re

def redact_emails(text):
    pattern = re.compile(r'(\w+)@(\w+(?:\.\w+)*)')
    def replacer(m):
        local = m.group(1)
        domain = m.group(2)
        stars = '*' * max(1, len(local) - 1)
        return local[0] + stars + '@' + domain
    return pattern.sub(replacer, text)

