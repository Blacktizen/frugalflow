In this folder you will find the files listed below. Complete the work described next.

`wrap.py` `wrap_text(text, width)` : rend une liste de lignes. Retour a la ligne glouton sur les espaces ; les
espaces multiples sont reduits a un ; un mot plus long que width est coupe en morceaux de width caracteres ; chaque
"\n" du texte d entree marque une fin de paragraphe (les lignes d un paragraphe ne se melangent pas a celles du suivant) ;
un paragraphe vide donne une ligne vide "". width < 1 : ValueError. Aucune ligne rendue ne depasse width.
