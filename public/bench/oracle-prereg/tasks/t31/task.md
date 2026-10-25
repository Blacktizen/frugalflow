In this folder you will find the files listed below. Complete the work described next.

`paths.py` `normalize_path(p)` : normalise un chemin POSIX sans utiliser os.path ni pathlib : fusionne "//", retire
".", resout "..". Absolu : ".." au-dessus de la racine reste a la racine. Relatif : les ".." de tete sont conserves.
Slash final retire (sauf racine "/"). Resultat vide pour un relatif : ".". Entree "" : ".".
