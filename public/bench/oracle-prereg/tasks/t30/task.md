In this folder you will find the files listed below. Complete the work described next.

`batching.py` `batch_by_weight(items, max_weight)` : items = liste de (nom, poids). Regroupe dans l ordre, sans
reordonner, des lots successifs dont la somme des poids est <= max_weight (glouton : on ferme le lot quand le suivant
deborderait). Un element plus lourd que max_weight forme un lot a lui seul. Poids 0 permis. Rend une liste de listes
de noms. poids negatif ou max_weight <= 0 : ValueError.
