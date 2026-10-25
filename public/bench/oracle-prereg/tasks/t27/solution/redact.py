import re

def redact_emails(text):
    pattern = re.compile(r'(\w+)@(\w+\.\w+(?:\.\w+)*)')
    def replacer(m):
        local = m.group(1)
        domain = m.group(2)
        return local[0] + '***@' + domain
    return pattern.sub(replacer, text)

