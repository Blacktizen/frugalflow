In this folder you will find the files listed below. Complete the work described next.

`deepget.py` `deep_get(obj, path, default=None)` : path comme "a.b[2].c" ; cles de dict separees par des points,
indices de liste entre crochets, indices negatifs permis (-1 = dernier). Chemin absent, indice hors bornes, mauvais type
traverse : rend `default` sans lever d exception. path "" rend obj lui-meme. Une valeur presente mais None est rendue
telle quelle (pas remplacee par default).
