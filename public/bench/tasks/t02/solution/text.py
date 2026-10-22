def title_case(text):
    parts = text.split(" ")
    for i in range(len(parts)):
        if parts[i]:
            parts[i] = parts[i][0].upper() + parts[i][1:].lower()
    return " ".join(parts)
