def remove_stopwords(tokens, stopwords):
    stop = set(stopwords)
    return [t for t in tokens if t not in stop]
