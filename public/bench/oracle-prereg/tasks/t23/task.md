In this folder you will find the files listed below. Complete the work described next.

`movavg.py` `moving_average(xs, k)` : liste des moyennes des fenetres glissantes de k elements consecutifs
(len(xs)-k+1 valeurs, floats). k > len(xs) : []. k < 1 : ValueError. Resultat precis : la somme est calculee avec
math.fsum sur chaque fenetre (pas de somme glissante cumulative).
