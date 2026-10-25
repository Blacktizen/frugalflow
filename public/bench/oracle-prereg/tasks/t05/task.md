In this folder you will find the files listed below. Complete the work described next.

`semver.py` `compare(a, b)` : rend -1, 0 ou 1 pour deux versions semver "X.Y.Z[-pre][+build]". La metadonnee build
est ignoree. Une version avec pre-release est inferieure a la meme sans. Les identifiants de pre-release, separes par
des points, se comparent un a un : numeriques compares comme entiers, alphanumeriques compares en ordre ASCII, un
identifiant numerique est inferieur a un alphanumerique, et un ensemble plus court est inferieur s il est prefixe.
