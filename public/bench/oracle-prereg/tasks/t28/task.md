In this folder you will find the files listed below. Complete the work described next.

`envexp.py` `env_expand(template, env)` : remplace `${VAR}` par env[VAR] (absent : chaine vide) ; `${VAR:-def}` par
def si VAR est absent OU VIDE ; `$$` donne un `$` litteral ; un `$` isole ou `$VAR` sans accolades reste litteral. Pas
d expansion recursive : la valeur substituee n est pas re-analysee. Accolade non fermee : ValueError.
