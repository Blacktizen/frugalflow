In this folder you will find the files listed below. Complete the work described next.

`flat.py` `flatten(obj, sep=".")` : aplatit dict/list imbriques en un dict de chemins. Les listes sont indexees
(`a.0.b`). Un dict ou une liste VIDE est gardee comme valeur feuille ({} ou []). Les cles non-str sont converties par
str(). Une valeur scalaire de premier niveau (ni dict ni list) : ValueError. L entree n est pas modifiee.
