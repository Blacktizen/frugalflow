def wrap_text(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    paragraphs = text.split('\n')
    lines = []
    for para in paragraphs:
        words = para.split(' ')
        if not words or all(w == '' for w in words):
            lines.append("")
            continue
        current = ""
        for word in words:
            if current == "":
                current = word
            elif len(current) + 1 + len(word) <= width:
                current += " " + word
            else:
                lines.append(current)
                current = word
        if current != "":
            lines.append(current)
    return lines

