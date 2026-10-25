In this folder you will find the files listed below. Complete the work described next.

`chunks.py` `windows(seq, size, overlap=0)` : liste de tranches de longueur `size` avec chevauchement `overlap` entre
tranches consecutives. La derniere tranche partielle est gardee seulement si elle contient au moins un element absent de
la tranche precedente. size < 1 ou overlap < 0 ou overlap >= size : ValueError. seq vide : [].
