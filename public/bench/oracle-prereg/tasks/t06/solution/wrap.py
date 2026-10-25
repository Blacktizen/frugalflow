def wrap_text(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    paragraphs = text.split('\n')
    lines = []
    for para in paragraphs:
        words = para.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            chunks = []
            i = 0
            while i < len(word):
                chunks.append(word[i:i + width])
                i += width
            for chunk in chunks:
                if current == "":
                    current = chunk
                elif len(current) + 1 + len(chunk) <= width:
                    current += " " + chunk
                else:
                    lines.append(current)
                    current = chunk
        if current != "":
            lines.append(current)
    return lines

